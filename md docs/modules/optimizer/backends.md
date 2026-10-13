# `src/optimizer/backends.py`

## Purpose

Solve a [`LinearModel`](linear_model.md). Two backends solve the *same* formulation:

| Backend | How | Runs | Default |
| --- | --- | --- | --- |
| `solve_highs` | HiGHS through `scipy.optimize.milp` | in-process | **yes** |
| `solve_cpsat` | OR-Tools CP-SAT after integer scaling ([`cpsat_worker.py`](cpsat_worker.md)) | **child process** | no — `optimiser_cpsat` |

`BACKENDS = {"highs": solve_highs, "cpsat": solve_cpsat}` is what `WeeklyPlanner(backend=...)` looks up.

## Why a child process for CP-SAT

On the Windows/conda development machine, OR-Tools and pyarrow **cannot be loaded into one process**: conda's pyarrow
needs `abseil_dll.dll`, `libprotobuf.dll` and `re2.dll` from `Library\bin`, and OR-Tools ships *different builds* of
the same three names. Windows loads a DLL by name once per process, so whichever library is imported second fails with
`WinError 127`. Verified in both orders on 2026-10-13 (OR-Tools first breaks `import pyarrow`; pyarrow first breaks
`ortools`). The knowledge store needs pyarrow, so the planner process always has it. The solve therefore runs in a child
process that imports only NumPy and OR-Tools; the model goes in and the solution comes out as `.npz` files.

Cost: ~1–2 s of process start-up per solve, included in `SolveResult.seconds`. A persistent worker would amortise it;
not done because the one-shot design cannot leave stale state behind and a crash cannot wedge the planner.

> History: on 2026-10-12 OR-Tools could not be loaded at all on this laptop (recorded then as Windows Smart App
> Control, `WinError 4551`), which is why HiGHS was built first. On 2026-10-13 `ortools 9.15` loaded and solved with
> Smart App Control still reporting enforced; the cause of the change was not investigated. Nothing in this repo
> bypasses any OS security feature.

## Public API

| Name | What |
| --- | --- |
| `solve_highs(model, time_limit_s=20, mip_rel_gap=1e-3) -> SolveResult` | Solve; never raises for infeasibility |
| `solve_cpsat(model, time_limit_s=20, mip_rel_gap=1e-3, *, workers=8, scale=100, seed=0) -> SolveResult` | Same contract; see below |
| `SolveResult` | `status` (`optimal` / `feasible` / `infeasible` / `error`), `x`, `objective`, `seconds`, `mip_gap`, `message` |
| `BackendUnavailableError` | OR-Tools cannot be loaded in the child, or the child crashed |
| `BACKENDS` | name → function registry |

`feasible` means a time limit expired with an incumbent: a good plan, not proven optimal — acceptable for an
interactive app, and the gap is reported in the plan's diagnostics.

### CP-SAT specifics

* `mip_gap` is `|objective − bound| / max(|objective|, 1)` in CP-SAT's scaled integer units — the same meaning as
  HiGHS's gap, so the two are comparable in diagnostics.
* `workers=1` is deterministic; the default 8 can return a different (equally good) plan between runs. A wall-clock
  time limit makes *either* backend depend on machine speed.
* `ValueError` (not a silent change) if a non-zero coefficient or cost rounds to zero at the chosen `scale`, or the
  scaled model could overflow int64. `SolveResult.message` reports the largest coefficient rounding.
* `objective` is recomputed from the returned `x` with the model's *original* float costs, so HiGHS and CP-SAT
  objectives are directly comparable.

## Measured

Numbers live in [`md docs/evaluation.md`](../../evaluation.md#solver-backends-highs-vs-cp-sat-same-model-same-weights)
with the date and command, so they cannot drift from this file. Headline (48 validation scenarios, 8 s limit): HiGHS and
8-worker CP-SAT are a tie on plan quality (same objective on 34/48, no distinguishable difference in waste, groceries or
nutrition); single-worker CP-SAT is much worse. **HiGHS stays the default.** Summary of what was learned the hard way:

* CP-SAT's integer scaling had a real bug on first implementation: the weekly model is boundary-tight (`buy ≤ M` next
  to `buy ≥ demand`, with `M` the recipe's own grams), and flooring a float32 bound below its rounded coefficient made
  valid plans infeasible, so CP-SAT *proved optimal* for an altered model. It was found because HiGHS returned a
  better objective than CP-SAT's "optimal"; **always cross-check a new backend against another on identical models.**
  The regression test is `test_cpsat_is_not_made_infeasible_by_a_boundary_tight_buy_bound`.

## Known limits

* CP-SAT start-up (~1–2 s) is paid on every solve; a persistent worker would remove it but was not built because no
  measured benefit justifies the extra moving part.
* The CP-SAT backend needs `ortools` importable by `sys.executable`; without it `solve_cpsat` raises
  `BackendUnavailableError` and HiGHS is unaffected.
* HiGHS gaps are loose proven bounds (plans are within ~0.4 % of best found); tightening the model (symmetry breaking,
  per-day demand bounds) would make them honest but was not needed for plan quality.

## Tests

[`tests/optimizer/test_linear_model_and_backends.py`](../tests/optimizer/test_linear_model_and_backends.md) — every
solver behaviour is parametrised over both backends; CP-SAT tests skip where OR-Tools cannot be loaded.

## Change log

- 2026-10-12 — Created. Records the OR-Tools → HiGHS deviation and its reason.
- 2026-10-13 — Added `solve_cpsat` (child process, integer scaling), `BackendUnavailableError`, `BACKENDS`. Replaced
  the "Smart App Control blocks OR-Tools" explanation with the verified pyarrow DLL clash.
