# `src/optimizer/cpsat_worker.py`

## Purpose

Turn a [`LinearModel`](linear_model.md) (as raw arrays) into an integer CP-SAT model, solve it, and return the
solution in the model's own units. It runs **in its own process** — [`backends.solve_cpsat`](backends.md) is the
parent-side wrapper and the only normal caller.

## Where it sits

```
weekly.WeeklyPlanner ── backends.solve_cpsat ──(model.npz)──▶ cpsat_worker.py  (NumPy + OR-Tools only)
                                              ◀─(result.npz)──
```

It is executed as a bare script (`python -I cpsat_worker.py in.npz out.npz '<json>'`), so it **must not import
pandas, pyarrow, SciPy or any project module**: any of those brings back the DLL clash that is the reason it is a
separate process (see `backends.md`).

## Public API

| Name | What |
| --- | --- |
| `solve_arrays(c, indptr, indices, data, row_lb, row_ub, integrality, lb, ub, *, time_limit_s, mip_rel_gap, workers=8, scale=100, seed=0) -> dict` | Scale + solve; returns `{status, x, gap, message}` |
| `main(argv) -> int` | Script entry: reads `.npz`, writes `.npz`. Reports `unavailable` / `value_error` *in the result* |
| `SCALE`, `OBJECTIVE_SCALE`, `UNBOUNDED`, `ROUND_TOLERANCE`, `WORKERS` | Named constants, each commented with its source |

## How it works — the scaling rules

CP-SAT has no continuous variables and no float coefficients.

| Thing | Rule |
| --- | --- |
| integer variable | unchanged |
| continuous variable `v` | solved as `I = v·scale`, read back as `I / scale` (default `scale = 100`: 0.01 g / 0.01 kcal) |
| row coefficient `a` on variable `j` | `round(a · scale / var_scale[j])` (nearest) |
| row bounds | round **inward** (lower up, upper down): never loosen a requirement |
| *continuous* variable bounds | round **outward** (lower down, upper up) |
| integer variable bounds | inward |
| objective | `round(c · 1e8 / var_scale[j])` |
| infinite bound | clipped to ±1e6 (same stand-in as `weekly.INF_KCAL`) |

**Why continuous bounds round outward.** The weekly model is boundary-tight: `buy[i] ≤ M[i]` (M = the recipes' own
grams) sits next to `buy[i] ≥ demand − use`. Coefficients round to nearest, so a bound that rounds *inward* can land
below the rounded coefficient it has to hold, and the row becomes infeasible. CP-SAT then proves "optimal" for a model
that excludes valid plans. This happened (2026-10-13) and was caught only because HiGHS found a better objective on the
same model.

**Float noise.** Catalogue grams are `float32` (1.51 g arrives as 1.5099999). Every rounding adds
`ROUND_TOLERANCE = 0.05` scaled units (0.0005 g) before `ceil`/`floor`, so noise cannot flip a value across a grid
line.

**Nothing is dropped silently.** A non-zero coefficient or cost that rounds to 0 raises `ValueError`; a possible
int64 overflow raises `ValueError`. The largest coefficient rounding is returned in `message`.

## Decisions

* **Child process, not a workaround of the loader.** The clash is two legitimate builds of the same DLL names; the
  solution is isolation, not renaming, patching or changing OS settings.
* **Result reporting over exceptions across the process boundary.** An unloadable OR-Tools or a bad scale is written
  to the result file so the parent can raise a precise `BackendUnavailableError` / `ValueError` instead of parsing
  a traceback.
* **Uniform `scale` for every row** (not per-row adaptive scaling): simple, predictable, and the checks above turn any
  precision problem into a loud error instead of a wrong plan.

## Limits

* Resolution is 0.01 unit; constraints hold to within ~0.005 unit (reported). Evaluation replays plans independently,
  so this cannot flatter a result.
* Per-solve process start-up (~1–2 s).
* Multi-worker search is not deterministic (use `workers=1`).
* Needs `numpy` and `ortools` importable by the same interpreter as the parent (`sys.executable`).

## Tests

[`tests/optimizer/test_linear_model_and_backends.py`](../tests/optimizer/test_linear_model_and_backends.md): the
worker is exercised through `solve_cpsat` (as in production), plus `main` directly for the unloadable case.

## Change log

- 2026-10-13 — Created. Includes the fix for boundary-tight rows (continuous bounds round outward, float32 tolerance).
