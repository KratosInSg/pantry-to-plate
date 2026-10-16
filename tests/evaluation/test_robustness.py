"""Tests for ``evaluation/robustness.py``: perturbed realities change only the hidden truth, and degradation is signed
so that positive always means worse."""
from __future__ import annotations

from dataclasses import asdict

import pandas as pd
import pytest

from domain.models import PantryItem, Scenario
from evaluation.metrics import evaluate_plan
from evaluation.robustness import (NOMINAL, PERTURBATIONS, ROBUSTNESS_METRICS, Perturbation, compare_degradation,
                                   degradation, perturb_reality, report, run_robustness, summarise_degradation)
from evaluation.scenarios import FAMILIES, load_split
from optimizer.baselines import GreedyIngredientMatchPlanner
from optimizer.planning import plan_from_indices


def _scenario() -> Scenario:
    pantry = [
        PantryItem(ingredient_id=1, grams=100, last_use_day=3, expiry_confidence=0.6),     # estimated, spoils day 3
        PantryItem(ingredient_id=2, grams=200, last_use_day=2, expiry_known=True),          # a stated use-by date
        PantryItem(ingredient_id=3, grams=300),                                             # keeps all week
        PantryItem(ingredient_id=4, grams=50, last_use_day=1, expiry_confidence=0.5),      # estimated, nearly off
        PantryItem(ingredient_id=5, grams=80, last_use_day=6, expiry_confidence=0.5),      # visible estimate only
    ]
    return Scenario(scenario_id="robust-1", pantry=pantry, true_last_use_day={1: 3, 2: 2, 3: None, 4: 1, 5: 9})


def test_nominal_is_the_scenario_itself():
    sc = _scenario()
    assert perturb_reality(sc, NOMINAL) is sc
    assert NOMINAL in PERTURBATIONS and PERTURBATIONS[0].is_nominal


def test_earlier_expiry_moves_only_estimated_deadlines_inside_the_week():
    sc = _scenario()
    real = perturb_reality(sc, Perturbation("x", expiry_shift_days=2))
    assert real.true_last_use_day == {1: 1, 2: 2, 3: None, 4: 0, 5: 9}     # known, none, beyond-week untouched;
    assert real.pantry == sc.pantry                                         # clamped at 0; grams unchanged
    assert sc.true_last_use_day == {1: 3, 2: 2, 3: None, 4: 1, 5: 9}       # the input is not modified


def test_quantity_perturbation_changes_grams_but_nothing_the_planner_saw():
    sc = _scenario()
    real = perturb_reality(sc, Perturbation("x", quantity_scale=0.7))
    assert [p.grams for p in real.pantry] == pytest.approx([0.7 * p.grams for p in sc.pantry])
    for before, after in zip(sc.pantry, real.pantry):
        assert (before.last_use_day, before.expiry_known, before.expiry_confidence, before.urgency) == \
               (after.last_use_day, after.expiry_known, after.expiry_confidence, after.urgency)
    assert real.profile == sc.profile and real.true_last_use_day == sc.true_last_use_day


def test_random_perturbations_are_reproducible_and_seeded():
    sc = _scenario()
    noisy = Perturbation("noise", expiry_jitter_days=2, quantity_sigma=0.3)
    a, b, c = (perturb_reality(sc, noisy, seed=s) for s in (0, 0, 1))
    assert a == b
    assert [p.grams for p in a.pantry] != [p.grams for p in c.pantry]
    assert a.true_last_use_day[2] == 2 and a.true_last_use_day[3] is None   # jitter never touches known / no deadline


def test_spoiling_earlier_costs_a_plan_that_relied_on_the_stock(ctx):
    """A real recipe cooked on day 2 from stock whose real deadline moves to day 0: bought instead, and wasted."""
    idx = 500
    ids, grams = ctx.catalog.ingredients(idx)
    main = max((int(i), float(g)) for i, g in zip(ids, grams) if int(i) not in ctx.ignore_ids)[0]
    sc = Scenario(scenario_id="robust-2", pantry=[PantryItem(ingredient_id=main, grams=1000, last_use_day=3,
                                                             expiry_confidence=0.5)],
                  true_last_use_day={main: 3})
    plan = plan_from_indices("manual", ctx, [0, 1, idx], 3)          # the stock is needed on day 2
    nominal = evaluate_plan(sc, plan, ctx)
    real = evaluate_plan(perturb_reality(sc, Perturbation("x", expiry_shift_days=3)), plan, ctx)
    assert real.grocery_g > nominal.grocery_g
    assert real.waste_g > nominal.waste_g


def test_degradation_is_positive_when_worse_whichever_way_the_metric_points():
    rows = []
    for pert, waste, util in (("nominal", 100.0, 50.0), ("p", 130.0, 40.0)):
        rows.append({"scenario_id": "s", "family": "f", "planner": "a", "perturbation": pert,
                     **{m: 0.0 for m in ROBUSTNESS_METRICS}, "waste_g": waste, "pantry_utilisation_pct": util})
    deg = degradation(pd.DataFrame(rows))
    assert list(deg.perturbation) == ["p"]
    assert deg.deg_waste_g.iloc[0] == pytest.approx(30.0)                   # more waste: worse
    assert deg.deg_pantry_utilisation_pct.iloc[0] == pytest.approx(10.0)    # less utilisation: also worse
    assert deg.deg_grocery_items.iloc[0] == 0.0


def test_run_robustness_end_to_end(ctx, capsys):
    perts = (NOMINAL, Perturbation("expiry_2d_early", expiry_shift_days=2), Perturbation("less", quantity_scale=0.7))
    df = run_robustness("validation", ["random", "greedy"], perts, limit=len(FAMILIES), ctx=ctx)
    assert len(df) == 2 * len(FAMILIES) * len(perts)
    assert set(df.perturbation) == {p.name for p in perts}

    # the nominal rows are exactly the ordinary benchmark metrics of the same plan
    sc = next(s for s in load_split("validation") if s.scenario_id == df.scenario_id.iloc[0])
    expected = asdict(evaluate_plan(sc, GreedyIngredientMatchPlanner(ctx).plan(sc), ctx))
    got = df[(df.scenario_id == sc.scenario_id) & (df.planner == "greedy") & (df.perturbation == "nominal")].iloc[0]
    assert got.waste_g == pytest.approx(expected["waste_g"]) and got.grocery_g == pytest.approx(expected["grocery_g"])

    deg = degradation(df)
    assert len(deg) == 2 * len(FAMILIES) * (len(perts) - 1)
    assert (deg[deg.perturbation == "less"].deg_grocery_g >= -1e-6).all()   # less stock never means less to buy
    assert set(summarise_degradation(deg).index.get_level_values("perturbation")) == {"expiry_2d_early", "less"}
    table = compare_degradation(deg, "greedy", "random")
    assert list(table.index) == ["expiry_2d_early", "less"] and (table.n == len(FAMILIES)).all()
    report(df, baseline="random")
    assert "degradation" in capsys.readouterr().out


def test_a_run_without_the_nominal_kitchen_is_refused(ctx):
    with pytest.raises(ValueError, match="nominal"):
        run_robustness("validation", ["random"], (Perturbation("x", quantity_scale=0.5),), limit=1, ctx=ctx)
