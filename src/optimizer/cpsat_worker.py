"""CP-SAT solve of a scaled :class:`LinearModel`, written to run in its **own process**.

Why a separate process
----------------------
On the development machine (Windows, conda Python) pandas -> pyarrow is loaded by the knowledge store, and conda's
pyarrow depends on ``abseil_dll.dll`` / ``libprotobuf.dll`` / ``re2.dll`` from ``Library\\bin``. OR-Tools ships *its own,
different* builds of the same three DLLs. Windows loads a DLL by name only once per process, so whichever of the two
libraries is imported second fails (``WinError 127: procedure could not be found``) - verified in both orders on
2026-10-13. They cannot coexist in one process, so the solve runs in a child process that imports only NumPy and
OR-Tools. ``backends.solve_cpsat`` is the parent-side wrapper; this file is also runnable as a script::

    python -I src/optimizer/cpsat_worker.py <model.npz> <result.npz> '<json params>'

This module must stay free of pandas / pyarrow / scipy / project imports (it is executed as a bare script, and an
import of any of those would bring the DLL clash back).

Scaling
-------
CP-SAT has no continuous variables and no float coefficients, so the model is integerised:

* an integer variable stays as it is; a continuous variable ``v`` is solved as ``I = v * scale`` (default 100, i.e. a
  resolution of 0.01 g / 0.01 kcal) and read back as ``I / scale``;
* every constraint row is multiplied by ``scale``, so a coefficient becomes ``round(a * scale / var_scale)``;
* the objective is multiplied by ``OBJECTIVE_SCALE`` the same way.

How bounds are rounded matters, and getting it wrong was a real bug (found 2026-10-13 by comparing with HiGHS: CP-SAT
"proved optimal" plans that HiGHS beat). The weekly model is *boundary-tight*: ``g[i] <= M[i]`` (``M`` = sum of the
recipe grams) next to ``g[i] >= demand - use``. Coefficients round to the **nearest** integer, so a continuous variable's
bound must round **outward** (lower bound down, upper bound up) - never inward - or the bound can end up below the
rounded coefficient it has to accommodate and the row becomes infeasible. Row bounds round inward (never loosen a
requirement). Every rounding step first adds ``ROUND_TOLERANCE`` of float noise: the catalogue stores grams as
float32, so "1.51 g" arrives as 1.5099999 and would otherwise floor to 150 instead of 151 hundredths.

Rounding is bounded (a coefficient or bound moves by at most ``0.5 / scale`` of its unit) and reported in the result
message. What must never happen silently - a non-zero coefficient or cost rounding to zero, which would delete a term
from the model - raises ``ValueError``.
"""
from __future__ import annotations

import json
import math
import sys
import time

import numpy as np

# 100 -> continuous variables resolved to 0.01 of their unit. Grams/kcal rounded to a hundredth are far below the noise
# in the estimated ingredient grams (CLAUDE.md "known limits"), and a larger value only inflates the integer domains.
SCALE = 100
# Cost coefficients become round(c * 1e8 / var_scale). The smallest real cost is ~0.003 per gram (grocery_per_100g);
# at scale 100 that is 3000 objective units, so rounding moves it by < 0.02 %. 1e8 keeps worst-case sums well inside
# int64 for the weekly model (checked by ``_check_magnitude``).
OBJECTIVE_SCALE = 1e8
# Stand-in for +/- infinity on a variable bound. Same magnitude as ``weekly.INF_KCAL``: no real quantity (grams, kcal,
# meals) in this problem gets near it.
UNBOUNDED = 1e6
# CP-SAT rejects models whose linear expressions could overflow int64; stay far below that.
_MAX_MAGNITUDE = 2.0 ** 60
# CP-SAT's own default portfolio size. More workers rarely help on a model this small.
WORKERS = 8
# Float noise, in *scaled* units (0.05 / 100 = 0.0005 g), absorbed before ceil/floor. Source: catalogue grams are
# float32 (relative error ~6e-8, i.e. ~3e-4 g on a 5 kg stock), summed over a few terms. Far below the 0.01 g resolution.
ROUND_TOLERANCE = 0.05

_ARRAY_KEYS = ("c", "indptr", "indices", "data", "row_lb", "row_ub", "integrality", "lb", "ub")


def _bound_to_int(value: float, scale: float, round_up: bool) -> int | None:
    """Scale a bound and round it to an integer; ``round_up`` picks ceil (else floor). ``None`` = unbounded.

    The caller chooses the direction so that every bound is rounded the *safe* way (see the module docstring):
    row lower bounds and integer-variable lower bounds up, row/integer upper bounds down, continuous-variable bounds
    outward.
    """
    if not math.isfinite(value):
        return None
    scaled = value * scale
    return math.ceil(scaled - ROUND_TOLERANCE) if round_up else math.floor(scaled + ROUND_TOLERANCE)


def _check_magnitude(max_activity: float, what: str) -> None:
    if max_activity > _MAX_MAGNITUDE:
        raise ValueError(f"CP-SAT scaling would overflow int64 in the {what} (worst case {max_activity:.3g}); "
                         "lower the scale / OBJECTIVE_SCALE or tighten the variable bounds")


def solve_arrays(c: np.ndarray, indptr: np.ndarray, indices: np.ndarray, data: np.ndarray, row_lb: np.ndarray,
                 row_ub: np.ndarray, integrality: np.ndarray, lb: np.ndarray, ub: np.ndarray, *,
                 time_limit_s: float, mip_rel_gap: float, workers: int = WORKERS, scale: int = SCALE,
                 seed: int = 0) -> dict:
    """Scale and solve ``min c.x  s.t. row_lb <= A x <= row_ub`` (A in CSR form) with CP-SAT.

    Returns ``{"status", "x", "gap", "message"}`` where ``status`` is ``optimal`` / ``feasible`` / ``infeasible`` /
    ``error`` and ``x`` is in the model's own units (``None`` unless a solution was found).

    Raises:
        ImportError, OSError: OR-Tools cannot be loaded.
        ValueError: a non-zero coefficient or cost rounds to zero at this scale, or the scaled model could overflow.
    """
    from ortools.sat.python import cp_model

    n = len(c)
    var_scale = np.where(integrality == 1, 1, scale).astype(np.int64)

    # --- variables ---------------------------------------------------------------------------------------------
    cp = cp_model.CpModel()
    ivars = []
    max_abs_value = np.empty(n)
    for j in range(n):
        s = float(var_scale[j])
        is_int = bool(integrality[j] == 1)
        # an integer variable can only take whole values, so its bounds round inward; a continuous variable's bounds
        # round outward (<= 0.01 unit looser) so they can never fall below a rounded coefficient they must hold
        lo = _bound_to_int(max(lb[j], -UNBOUNDED), s, round_up=is_int)
        hi = _bound_to_int(min(ub[j], UNBOUNDED), s, round_up=not is_int)
        if lo > hi:                                       # e.g. an integer variable bounded to [0.2, 0.8]
            return {"status": "infeasible", "x": None, "gap": None, "message": f"variable {j} has an empty domain"}
        max_abs_value[j] = max(abs(lo), abs(hi))
        ivars.append(cp.NewIntVar(lo, hi, f"v{j}"))

    # --- constraint rows ---------------------------------------------------------------------------------------
    max_err = 0.0
    for i in range(len(row_lb)):
        start, stop = indptr[i], indptr[i + 1]
        idx, vals = indices[start:stop], data[start:stop]
        lo = _bound_to_int(row_lb[i], scale, round_up=True)
        hi = _bound_to_int(row_ub[i], scale, round_up=False)
        if len(idx) == 0:                                 # an empty row only matters if it cannot hold at 0
            if (lo is not None and lo > 0) or (hi is not None and hi < 0):
                return {"status": "infeasible", "x": None, "gap": None, "message": f"row {i} is empty and violated"}
            continue
        coefs = np.rint(vals * scale / var_scale[idx]).astype(np.int64)
        if np.any(coefs == 0):
            raise ValueError(f"row {i}: a non-zero coefficient rounds to 0 at scale={scale}; raise the scale")
        # error of the *unscaled* coefficient: how far the integer version is from the real one, in model units
        max_err = max(max_err, float(np.max(np.abs(vals - coefs * var_scale[idx] / scale))))
        _check_magnitude(float(np.sum(np.abs(coefs) * max_abs_value[idx])), f"row {i}")
        expr = cp_model.LinearExpr.WeightedSum([ivars[j] for j in idx.tolist()], coefs.tolist())
        if lo is not None and hi is not None:
            cp.AddLinearConstraint(expr, lo, hi)
        elif lo is not None:
            cp.Add(expr >= lo)
        elif hi is not None:
            cp.Add(expr <= hi)

    # --- objective ---------------------------------------------------------------------------------------------
    obj = np.rint(c * OBJECTIVE_SCALE / var_scale).astype(np.int64)
    if np.any((c != 0) & (obj == 0)):
        raise ValueError("a non-zero cost rounds to 0; raise OBJECTIVE_SCALE")
    _check_magnitude(float(np.sum(np.abs(obj) * max_abs_value)), "objective")
    cp.Minimize(cp_model.LinearExpr.WeightedSum(ivars, obj.tolist()))

    # --- solve -------------------------------------------------------------------------------------------------
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(time_limit_s)
    solver.parameters.relative_gap_limit = float(mip_rel_gap)
    solver.parameters.num_workers = int(workers)
    solver.parameters.random_seed = int(seed)
    status = solver.Solve(cp)
    note = f"CP-SAT {solver.StatusName(status)}; scale={scale}; max coefficient rounding {max_err:.4f}"

    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        x = np.array([solver.Value(v) for v in ivars], dtype=float) / var_scale
        best, bound = solver.ObjectiveValue(), solver.BestObjectiveBound()
        gap = abs(best - bound) / max(abs(best), 1.0)     # both in objective-scaled integer units
        return {"status": "optimal" if status == cp_model.OPTIMAL else "feasible", "x": x, "gap": gap, "message": note}
    if status == cp_model.INFEASIBLE:
        return {"status": "infeasible", "x": None, "gap": None, "message": note}
    detail = cp.Validate() if status == cp_model.MODEL_INVALID else ""
    return {"status": "error", "x": None, "gap": None, "message": f"{note} {detail}".strip()}


def main(argv: list[str]) -> int:
    """Script entry: read the model arrays from ``argv[0]``, write the result to ``argv[1]``, params JSON in ``argv[2]``.

    A recoverable problem is reported *in the result file* (``status`` = ``unavailable`` or ``value_error``) so the
    parent can raise a precise exception; the exit code is non-zero only for a crash.
    """
    in_path, out_path, params_json = argv
    params = json.loads(params_json)
    started = time.time()
    try:
        with np.load(in_path) as z:
            arrays = {k: z[k] for k in _ARRAY_KEYS}
        out = solve_arrays(**arrays, **params)
    except (ImportError, OSError) as exc:                # OSError: the loader refuses a DLL
        out = {"status": "unavailable", "x": None, "gap": None, "message": f"{type(exc).__name__}: {exc}"}
    except ValueError as exc:
        out = {"status": "value_error", "x": None, "gap": None, "message": str(exc)}
    np.savez(out_path, status=out["status"], message=out["message"],
             x=np.empty(0) if out["x"] is None else out["x"], has_x=out["x"] is not None,
             gap=np.nan if out["gap"] is None else out["gap"], seconds=time.time() - started)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
