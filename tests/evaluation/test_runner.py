"""Tests for ``evaluation/runner.py``: the benchmark harness wires planners, scenarios and metrics together."""
from __future__ import annotations

import pytest

from evaluation.runner import build_planner, per_family_comparison, report, run
from evaluation.scenarios import FAMILIES


def test_build_planner_registry(ctx):
    assert build_planner("random", ctx).name == "random"
    assert build_planner("greedy", ctx).name == "greedy"
    assert build_planner("optimiser", ctx).name == "optimiser"
    assert build_planner("opt_no_preference", ctx).name == "opt_no_preference"
    with pytest.raises(ValueError):
        build_planner("telepathy", ctx)


def test_run_covers_every_family_for_every_planner(ctx):
    df = run("validation", ["random", "greedy"], limit=len(FAMILIES), ctx=ctx, verbose=False)
    assert set(df.planner) == {"random", "greedy"}
    assert set(df.family) == set(FAMILIES)
    assert len(df) == 2 * len(FAMILIES)
    assert (df.violations == 0).all()                              # baselines respect the hard rules
    assert set(df.attrs["seconds_per_plan"]) == {"random", "greedy"}


def test_report_prints_the_comparison(ctx, capsys):
    df = run("validation", ["random", "greedy"], limit=len(FAMILIES), ctx=ctx, verbose=False)
    report(df, baseline="greedy")
    out = capsys.readouterr().out
    assert "overall" in out and "paired comparison vs 'greedy'" in out and "random" in out
    assert "PER FAMILY" in out


def test_per_family_comparison_has_one_row_per_family(ctx):
    df = run("validation", ["random", "greedy"], limit=2 * len(FAMILIES), ctx=ctx, verbose=False)
    table = per_family_comparison(df, "random", "greedy")
    assert set(table.index) == set(FAMILIES)
    assert (table.n == 2).all()
    assert all("[" in cell for cell in table.waste_g)              # "mean [low, high]"
