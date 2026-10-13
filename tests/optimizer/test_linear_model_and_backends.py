"""Tests for ``optimizer/linear_model.py`` and ``optimizer/backends.py`` on problems small enough to solve by hand.

Every solver behaviour is checked on *both* backends: the formulation must mean the same thing to HiGHS and to CP-SAT.
CP-SAT tests are skipped (not failed) on a machine where OR-Tools cannot be loaded.
"""
from __future__ import annotations

import builtins
import subprocess
import sys

import numpy as np
import pytest

from optimizer import backends, cpsat_worker
from optimizer.backends import BACKENDS, BackendUnavailableError, solve_cpsat, solve_highs
from optimizer.linear_model import LinearModel


def _cpsat_loads() -> bool:
    """Probe in a child process, exactly as the backend runs it: in *this* process pandas/pyarrow are already loaded,
    and OR-Tools cannot be imported next to them (see ``cpsat_worker.py``), so an in-process probe would always fail."""
    probe = subprocess.run([sys.executable, "-I", "-c", "from ortools.sat.python import cp_model"],
                           capture_output=True)
    return probe.returncode == 0


needs_cpsat = pytest.mark.skipif(not _cpsat_loads(), reason="OR-Tools CP-SAT cannot be loaded on this machine")

#: (id, solver) pairs; CP-SAT is run single-worker so the tests are deterministic.
SOLVERS = [
    pytest.param(solve_highs, id="highs"),
    pytest.param(lambda m, **kw: solve_cpsat(m, workers=1, **kw), id="cpsat", marks=needs_cpsat),
]


def test_builder_bookkeeping():
    m = LinearModel()
    a = m.add_binary(cost=2.0, name="a")
    b = m.add_var(0, 10, cost=1.0, name="b")
    m.add_to_cost(b, 0.5)
    m.add_constraint({a: 1.0, b: 1.0}, ub=5.0)
    assert (m.n_vars, m.n_integer, m.n_constraints) == (2, 1, 1)
    c, A, row_lb, row_ub, integrality, lb, ub = m.to_arrays()
    assert c.tolist() == [2.0, 1.5] and integrality.tolist() == [1, 0]
    assert A.shape == (1, 2) and row_ub.tolist() == [5.0]
    assert m.objective_value(np.array([1.0, 2.0])) == pytest.approx(5.0)


def test_repeated_variables_in_a_row_are_summed_and_zeros_dropped():
    m = LinearModel()
    a, b = m.add_var(0, 1), m.add_var(0, 1)
    m.add_constraint([(a, 1.0), (a, 2.0), (b, 0.0)], ub=3.0)
    _, A, *_ = m.to_arrays()
    assert A.toarray().tolist() == [[3.0, 0.0]]


@pytest.mark.parametrize("solve", SOLVERS)
def test_knapsack_is_solved_to_optimality(solve):
    # values 6/5/4, weights 3/3/2, capacity 5: the best choice is items 0 and 2 (value 10)
    m = LinearModel()
    xs = [m.add_binary(cost=-v) for v in (6.0, 5.0, 4.0)]
    m.add_constraint({x: w for x, w in zip(xs, (3.0, 3.0, 2.0))}, ub=5.0)
    res = solve(m, time_limit_s=10)
    assert res.status == "optimal"
    assert [round(float(res.x[x])) for x in xs] == [1, 0, 1]
    assert res.objective == pytest.approx(-10.0)


@pytest.mark.parametrize("solve", SOLVERS)
def test_continuous_variables(solve):
    # min 0.4x + y  s.t.  x + 2y >= 4, x <= 1.  x is the cheaper way to cover the row but is capped at 1, so the rest
    # comes from y: x = 1, y = 1.5, cost 1.9 (covering it all with y alone would cost 2.0).
    m = LinearModel()
    x, y = m.add_var(0, 1, cost=0.4), m.add_var(0, 100, cost=1.0)
    m.add_constraint({x: 1.0, y: 2.0}, lb=4.0)
    res = solve(m)
    assert res.status == "optimal"
    assert res.x[x] == pytest.approx(1.0) and res.x[y] == pytest.approx(1.5)
    assert res.objective == pytest.approx(1.9)


@pytest.mark.parametrize("solve", SOLVERS)
def test_a_model_without_constraints_still_solves(solve):
    m = LinearModel()
    v = m.add_var(2.0, 9.0, cost=1.0)
    res = solve(m)
    assert res.status == "optimal" and res.x[v] == pytest.approx(2.0)


@pytest.mark.parametrize("solve", SOLVERS)
def test_infeasible_model_is_reported_not_raised(solve):
    m = LinearModel()
    x = m.add_binary()
    m.add_constraint({x: 1.0}, lb=2.0)
    res = solve(m)
    assert res.status == "infeasible" and res.x is None and res.objective is None


@pytest.mark.parametrize("solve", SOLVERS)
def test_negative_costs_and_equality_rows(solve):
    """The weekly model has negative costs (waste avoided) and ``== 1`` rows (one dinner per day)."""
    m = LinearModel()
    pick = [m.add_binary(cost=c) for c in (0.5, -0.25, 0.1)]
    m.add_constraint({v: 1.0 for v in pick}, lb=1.0, ub=1.0)
    res = solve(m)
    assert res.status == "optimal"
    assert [round(float(res.x[v])) for v in pick] == [0, 1, 0]
    assert res.objective == pytest.approx(-0.25)


# ------------------------------------------------------------------------------------------------ CP-SAT scaling
@needs_cpsat
def test_cpsat_matches_highs_on_a_mixed_model():
    """Binary choice + continuous flow + big-M link: the shape of the weekly model in miniature."""
    m = LinearModel()
    use = m.add_var(0, 500, cost=-0.01)               # grams of stock used (waste avoided)
    buy = m.add_var(0, 1000, cost=0.003)              # grams bought
    on = m.add_binary(cost=1.0)                       # shopping-list item
    meal = m.add_binary(cost=0.2)
    m.add_constraint({use: 1.0, meal: -123.4}, ub=0.0)           # can only use what the meal needs
    m.add_constraint({buy: 1.0, use: 1.0, meal: -250.0}, lb=0.0)  # the rest is bought
    m.add_constraint({buy: 1.0, on: -1000.0}, ub=0.0)
    m.add_constraint({meal: 1.0}, lb=1.0)
    a, b = solve_highs(m), solve_cpsat(m, workers=1)
    assert a.status == b.status == "optimal"
    assert b.objective == pytest.approx(a.objective, abs=1e-2)
    assert b.x[use] == pytest.approx(a.x[use], abs=0.05)


@needs_cpsat
@pytest.mark.parametrize("grams", [np.float32(1.51), np.float32(10.53), 1.5097, 123.456], ids=str)
def test_cpsat_is_not_made_infeasible_by_a_boundary_tight_buy_bound(grams):
    """Regression (2026-10-13). The weekly model bounds ``buy <= M`` where ``M`` is the recipe's own grams, and also
    requires ``buy >= grams * cooked``. Catalogue grams are float32 (1.51 -> 1.5099999) and coefficients round to
    nearest, so a bound that floored inward made ``buy >= 151`` hundredths impossible against ``buy <= 150``.
    CP-SAT then reported 'optimal' for a model that excluded valid plans."""
    g = float(grams)
    m = LinearModel()
    cooked = m.add_binary(cost=0.0)
    buy = m.add_var(0.0, g, cost=0.003)               # M = the recipe's own grams: the bound is exactly the demand
    m.add_constraint({cooked: 1.0}, lb=1.0, ub=1.0)   # the meal is cooked
    m.add_constraint({buy: 1.0, cooked: -g}, lb=0.0)  # buy >= demand
    a, b = solve_highs(m), solve_cpsat(m, workers=1)
    assert a.status == "optimal"
    assert b.status == "optimal", b.message
    assert b.x[buy] == pytest.approx(g, abs=0.01)


@needs_cpsat
def test_cpsat_reads_back_continuous_values_at_model_scale():
    m = LinearModel()
    v = m.add_var(0, 10, cost=-1.0)
    m.add_constraint({v: 1.0}, ub=3.37)               # a bound that is not a whole number
    res = solve_cpsat(m, workers=1)
    assert res.x[v] == pytest.approx(3.37, abs=0.01)


@needs_cpsat
def test_cpsat_rounds_row_bounds_inwards_never_loosening_them():
    m = LinearModel()
    v = m.add_var(0, 10, cost=-1.0)
    m.add_constraint({v: 1.0}, ub=2.999)              # scale 100 -> 299.9 -> must floor to 299, not round to 300
    res = solve_cpsat(m, workers=1, scale=100)
    assert res.x[v] <= 2.999 + 1e-9


@needs_cpsat
def test_cpsat_refuses_to_silently_drop_a_tiny_coefficient():
    m = LinearModel()
    v = m.add_var(0, 10, cost=-1.0)
    m.add_constraint({v: 0.001}, ub=1.0)              # at scale 100 this rounds to 0 -> would delete the row
    with pytest.raises(ValueError, match="rounds to 0"):
        solve_cpsat(m, workers=1, scale=100)


@needs_cpsat
def test_cpsat_refuses_a_cost_that_scales_to_zero():
    m = LinearModel()
    m.add_var(0, 10, cost=1e-12)
    with pytest.raises(ValueError, match="cost rounds to 0"):
        solve_cpsat(m, workers=1)


@needs_cpsat
def test_cpsat_reports_rounding_and_status_in_the_message():
    m = LinearModel()
    m.add_var(0, 1, cost=1.0)
    assert "scale=100" in solve_cpsat(m, workers=1).message


# ------------------------------------------------------------------------------------------------ availability
def test_worker_reports_unloadable_ortools_in_its_result_file(monkeypatch, tmp_path):
    """The child must turn a refused DLL into ``status=unavailable`` rather than crash with a traceback."""
    real_import = builtins.__import__

    def blocked(name, *args, **kwargs):
        if name.startswith("ortools"):
            raise OSError("[WinError 4551] blocked by policy")
        return real_import(name, *args, **kwargs)

    m = LinearModel()
    m.add_var(0, 1)
    c, a, row_lb, row_ub, integrality, lb, ub = m.to_arrays()
    in_path, out_path = tmp_path / "in.npz", tmp_path / "out.npz"
    np.savez(in_path, c=c, indptr=a.indptr, indices=a.indices, data=a.data, row_lb=row_lb, row_ub=row_ub,
             integrality=integrality, lb=lb, ub=ub)
    monkeypatch.setattr(builtins, "__import__", blocked)
    assert cpsat_worker.main([str(in_path), str(out_path), '{"time_limit_s": 1, "mip_rel_gap": 0.1}']) == 0
    monkeypatch.undo()
    with np.load(out_path) as z:
        assert str(z["status"]) == "unavailable" and "WinError 4551" in str(z["message"])


def test_unavailable_worker_becomes_a_clear_error_and_highs_still_works(monkeypatch, tmp_path):
    """Parent side: an ``unavailable`` result raises ``BackendUnavailableError``; HiGHS is unaffected."""
    fake = tmp_path / "fake_worker.py"
    fake.write_text(
        "import sys, numpy as np\n"
        "np.savez(sys.argv[2], status='unavailable', message='OSError: blocked', x=np.empty(0), has_x=False,\n"
        "         gap=np.nan, seconds=0.0)\n")
    monkeypatch.setattr(backends, "_WORKER_SCRIPT", fake)
    m = LinearModel()
    m.add_var(0, 1)
    with pytest.raises(BackendUnavailableError, match="cannot be loaded"):
        solve_cpsat(m)
    assert solve_highs(m).status == "optimal"


def test_a_crashing_worker_is_reported_not_swallowed(monkeypatch, tmp_path):
    crash = tmp_path / "crash_worker.py"
    crash.write_text("raise SystemExit('segfault stand-in')\n")
    monkeypatch.setattr(backends, "_WORKER_SCRIPT", crash)
    m = LinearModel()
    m.add_var(0, 1)
    with pytest.raises(BackendUnavailableError, match="worker failed"):
        solve_cpsat(m)


def test_backend_registry_names():
    assert set(BACKENDS) == {"highs", "cpsat"}
