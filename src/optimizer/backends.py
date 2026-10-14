"""Solver backends for :class:`optimizer.linear_model.LinearModel`.

Two backends solve the same formulation:

* ``solve_highs``  - HiGHS through ``scipy.optimize.milp``. Always available (SciPy ships it), exact on continuous
  variables, runs in-process, deterministic. The default.
* ``solve_cpsat``  - OR-Tools CP-SAT. Integer-only, so continuous variables and float coefficients are scaled to
  integers (``cpsat_worker.py``). It runs in a **child process**: on the development machine OR-Tools and pyarrow
  cannot be loaded into one process (they need different builds of the same DLLs), and the knowledge store needs
  pyarrow. The price is ~1-2 s of process start-up per solve.

Why two? The stack in CLAUDE.md named CP-SAT, but HiGHS was built first because OR-Tools could not be loaded on the
development laptop. HiGHS proves loose gaps on the weekly model (big-M + symmetric days); CP-SAT's clause learning may
do better, which is an empirical question answered on the *validation* split (``md docs/evaluation.md``). Nothing in the
formulation changes between backends - that is the point of ``linear_model.py``.

Determinism: HiGHS is deterministic for identical inputs and options. CP-SAT with ``workers=1`` is deterministic too;
with several workers the portfolio search can return a different (equally good) plan between runs, and a wall-clock
time limit makes either backend machine-speed dependent. Use ``workers=1`` when reproducibility matters more than speed.
"""
from __future__ import annotations

import json
import logging
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp

from optimizer.cpsat_worker import SCALE as CPSAT_SCALE, WORKERS as CPSAT_WORKERS
from optimizer.linear_model import LinearModel

logger = logging.getLogger(__name__)

_WORKER_SCRIPT = Path(__file__).with_name("cpsat_worker.py")
# The solver stops itself at ``time_limit_s``; this is only a safety net for a hung child process (model build + python
# start-up are well below it).
_SUBPROCESS_GRACE_S = 60.0


class BackendUnavailableError(RuntimeError):
    """The requested solver cannot be loaded on this machine (e.g. OR-Tools blocked or missing)."""


@dataclass(frozen=True)
class SolveResult:
    """Outcome of one solve."""

    status: str                 # optimal | feasible | infeasible | error
    x: np.ndarray | None        # variable values in the model's own units (None when no solution)
    objective: float | None     # c . x in the model's own units, excluding any constant the caller adds
    seconds: float              # wall clock for the whole call (for CP-SAT: including child-process start-up)
    mip_gap: float | None       # relative gap |obj - bound| / |obj| when known, else None
    message: str = ""


# =================================================================================================== HiGHS
def solve_highs(model: LinearModel, time_limit_s: float = 20.0, mip_rel_gap: float = 1e-3) -> SolveResult:
    """Solve ``model`` with HiGHS.

    Args:
        time_limit_s: wall-clock limit. If it expires with an incumbent solution the result is ``feasible`` (a good
            plan, not proven optimal) - which is acceptable for an interactive app.
        mip_rel_gap: stop when the proven gap to the best bound is below this fraction.
    """
    c, a, row_lb, row_ub, integrality, lb, ub = model.to_arrays()
    started = time.time()
    res = milp(c=c, constraints=[LinearConstraint(a, row_lb, row_ub)] if model.n_constraints else [],
               integrality=integrality, bounds=Bounds(lb, ub),
               options={"time_limit": time_limit_s, "mip_rel_gap": mip_rel_gap, "disp": False})
    seconds = time.time() - started
    gap = getattr(res, "mip_gap", None)
    logger.debug("HiGHS: scipy status %s after %.2f s (limit %.0f s, gap target %g): %s", res.status, seconds,
                 time_limit_s, mip_rel_gap, res.message)
    if res.x is not None and res.status == 0:
        return SolveResult("optimal", res.x, float(res.fun), seconds, gap, res.message)
    if res.x is not None:                                   # time limit with an incumbent
        return SolveResult("feasible", res.x, float(res.fun), seconds, gap, res.message)
    status = "infeasible" if res.status == 2 else "error"
    return SolveResult(status, None, None, seconds, None, res.message)


# =================================================================================================== CP-SAT
def solve_cpsat(model: LinearModel, time_limit_s: float = 20.0, mip_rel_gap: float = 1e-3, *,
                workers: int = CPSAT_WORKERS, scale: int = CPSAT_SCALE, seed: int = 0) -> SolveResult:
    """Solve ``model`` with OR-Tools CP-SAT in a child process (scaling rules: ``cpsat_worker.py``).

    Args:
        time_limit_s, mip_rel_gap: as for :func:`solve_highs`. ``time_limit_s`` bounds the *search*; process start-up
            (~1-2 s) comes on top and is included in ``SolveResult.seconds``.
        workers: parallel search workers. ``1`` is deterministic; more is faster but may return a different plan
            between runs.
        scale: resolution of continuous variables (``1 / scale`` of a unit).
        seed: random seed handed to the solver (only fully effective with ``workers=1``).

    Raises:
        BackendUnavailableError: OR-Tools cannot be loaded in the child process, or the child crashed.
        ValueError: a non-zero coefficient or cost would round to zero at this scale, or the scaled model could
            overflow int64 (the model is wrong for this scale; no plan is better than a silently altered model).
    """
    started = time.time()
    c, a, row_lb, row_ub, integrality, lb, ub = model.to_arrays()
    params = {"time_limit_s": float(time_limit_s), "mip_rel_gap": float(mip_rel_gap), "workers": int(workers),
              "scale": int(scale), "seed": int(seed)}
    with tempfile.TemporaryDirectory(prefix="p2p_cpsat_") as tmp:
        in_path, out_path = Path(tmp) / "model.npz", Path(tmp) / "result.npz"
        np.savez(in_path, c=c, indptr=a.indptr, indices=a.indices, data=a.data, row_lb=row_lb, row_ub=row_ub,
                 integrality=integrality, lb=lb, ub=ub)
        # -I: no PYTHONPATH / user site / cwd on sys.path, so the child imports exactly NumPy + OR-Tools
        cmd = [sys.executable, "-I", str(_WORKER_SCRIPT), str(in_path), str(out_path), json.dumps(params)]
        logger.debug("CP-SAT: starting worker process (%d vars, %d constraints, %s)", model.n_vars,
                     model.n_constraints, params)
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=time_limit_s + _SUBPROCESS_GRACE_S)
        except subprocess.TimeoutExpired:
            logger.warning("CP-SAT worker did not finish within %.0f s; no plan from this backend",
                           time_limit_s + _SUBPROCESS_GRACE_S)
            return SolveResult("error", None, None, time.time() - started, None, "CP-SAT worker timed out")
        if proc.returncode != 0 or not out_path.exists():
            tail = (proc.stderr or "").strip().splitlines()[-1:] or ["no output"]
            logger.debug("CP-SAT worker stderr (exit %s):\n%s", proc.returncode, proc.stderr)
            raise BackendUnavailableError(f"CP-SAT worker failed (exit {proc.returncode}): {tail[0]}")
        with np.load(out_path) as z:
            status, message = str(z["status"]), str(z["message"])
            x = z["x"].astype(float) if bool(z["has_x"]) else None
            gap = float(z["gap"])

    if status == "unavailable":
        raise BackendUnavailableError(f"OR-Tools CP-SAT cannot be loaded here ({message})")
    if status == "value_error":
        raise ValueError(message)
    seconds = time.time() - started
    logger.debug("CP-SAT: %s after %.2f s (including process start-up): %s", status, seconds, message)
    if x is None:
        return SolveResult(status, None, None, seconds, None, message)
    return SolveResult(status, x, model.objective_value(x), seconds, None if np.isnan(gap) else gap, message)


#: Backend registry used by ``weekly.WeeklyPlanner(backend=...)``.
BACKENDS = {"highs": solve_highs, "cpsat": solve_cpsat}
