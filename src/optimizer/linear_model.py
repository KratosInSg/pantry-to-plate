"""A tiny, solver-agnostic mixed-integer *linear* model builder.

Why this file exists
--------------------
The weekly planning problem is linear: 0/1 choices of recipe per day and continuous gram flows between pantry, meals and
shopping list. That means it can be handed to any MILP/CP solver. The project uses two: SciPy's HiGHS (in-process) and
OR-Tools CP-SAT (which needs integer scaling and, on the development machine, its own process - see ``backends.py``).
Rather than tie the formulation to one solver, the formulation (``weekly.py``) is written against this small builder,
and ``backends.py`` turns the result into whatever a solver needs. Swapping the solver is then a change in one place,
and the model itself is unit-testable without any solver.

What it models
--------------
    minimise   c . x
    subject to row_lb <= A x <= row_ub,   lb <= x <= ub,   x_j integer for j in integer_set

Variables and constraints are added one at a time and referred to by integer handles, so the formulation code reads like
the maths.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy import sparse

INF = float("inf")


@dataclass
class LinearModel:
    """Mutable builder; call :meth:`to_arrays` when finished."""

    _lb: list[float] = field(default_factory=list)
    _ub: list[float] = field(default_factory=list)
    _int: list[bool] = field(default_factory=list)
    _cost: list[float] = field(default_factory=list)
    _names: list[str] = field(default_factory=list)
    _row_idx: list[int] = field(default_factory=list)
    _col_idx: list[int] = field(default_factory=list)
    _val: list[float] = field(default_factory=list)
    _row_lb: list[float] = field(default_factory=list)
    _row_ub: list[float] = field(default_factory=list)

    # ------------------------------------------------------------------------------------------------ building
    def add_var(self, lb: float = 0.0, ub: float = INF, integer: bool = False, cost: float = 0.0, name: str = "") -> int:
        """Add a variable and return its handle (column index)."""
        self._lb.append(lb)
        self._ub.append(ub)
        self._int.append(integer)
        self._cost.append(cost)
        self._names.append(name)
        return len(self._lb) - 1

    def add_binary(self, cost: float = 0.0, name: str = "") -> int:
        return self.add_var(0.0, 1.0, True, cost, name)

    def add_to_cost(self, var: int, cost: float) -> None:
        """Increase a variable's objective coefficient (terms are often accumulated from several places)."""
        self._cost[var] += cost

    def add_constraint(self, coeffs: dict[int, float] | list[tuple[int, float]], lb: float = -INF, ub: float = INF) -> int:
        """Add ``lb <= sum(coef * var) <= ub``. Repeated variables are summed. Returns the row index."""
        row = len(self._row_lb)
        items = coeffs.items() if isinstance(coeffs, dict) else coeffs
        merged: dict[int, float] = {}
        for var, coef in items:
            merged[var] = merged.get(var, 0.0) + coef
        for var, coef in merged.items():
            if coef != 0.0:
                self._row_idx.append(row)
                self._col_idx.append(var)
                self._val.append(coef)
        self._row_lb.append(lb)
        self._row_ub.append(ub)
        return row

    # ------------------------------------------------------------------------------------------------ reading
    @property
    def n_vars(self) -> int:
        return len(self._lb)

    @property
    def n_constraints(self) -> int:
        return len(self._row_lb)

    @property
    def n_integer(self) -> int:
        return sum(self._int)

    def objective_value(self, x: np.ndarray) -> float:
        return float(np.dot(self._cost, x))

    def to_arrays(self):
        """``(c, A_csr, row_lb, row_ub, integrality, var_lb, var_ub)`` as numpy / scipy objects."""
        a = sparse.csr_matrix((self._val, (self._row_idx, self._col_idx)), shape=(self.n_constraints, self.n_vars))
        return (np.asarray(self._cost, dtype=float), a, np.asarray(self._row_lb, dtype=float),
                np.asarray(self._row_ub, dtype=float), np.asarray(self._int, dtype=int),
                np.asarray(self._lb, dtype=float), np.asarray(self._ub, dtype=float))
