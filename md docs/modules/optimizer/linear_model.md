# `src/optimizer/linear_model.py`

## Purpose

A tiny, solver-agnostic mixed-integer **linear** model builder:

```
minimise  c · x     subject to   row_lb ≤ A x ≤ row_ub,   lb ≤ x ≤ ub,   x_j integer for j in the integer set
```

The weekly problem is linear (0/1 recipe choices, continuous gram flows). Writing the formulation against this builder
instead of a solver API means the model is unit-testable without a solver and the solver can be swapped in one place
(`backends.py`).

## Public API

| Method | What |
| --- | --- |
| `add_var(lb, ub, integer, cost, name) -> handle` | Add a variable; returns its column index |
| `add_binary(cost, name)` | `add_var(0, 1, integer=True, …)` |
| `add_to_cost(var, cost)` | Accumulate objective coefficients from several places |
| `add_constraint(coeffs, lb, ub) -> row` | `lb ≤ Σ coef·var ≤ ub`; repeated variables are summed, zero coefficients dropped |
| `n_vars`, `n_integer`, `n_constraints`, `objective_value(x)` | Introspection |
| `to_arrays()` | `(c, A_csr, row_lb, row_ub, integrality, var_lb, var_ub)` as NumPy / SciPy objects |

## Why handles are plain ints

The formulation code in `weekly.py` reads like the maths (`x[k, d]`, `u[i, d]`); integers keep rows cheap to build
(thousands of constraints) and trivially serialisable for debugging.

## Tests

[`tests/optimizer/test_linear_model_and_backends.py`](../tests/optimizer/test_linear_model_and_backends.md)

## Change log

- 2026-10-12 — Created.
- 2026-10-13 — Module docstring updated: two backends (HiGHS, CP-SAT) now consume this model. No behaviour change.
