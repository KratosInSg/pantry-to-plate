"""Tests for ``explain/explainer.py``: the three stages composed, and the guarantees that matter end to end - the plan is
never changed, the text works without an LLM, and a bad LLM can only ever cost style, never correctness."""
from __future__ import annotations

from explain.explainer import explain, explain_facts
from explain.facts import build_facts
from explain.paraphrase import Paraphraser, ingredient_vocabulary
from optimizer.baselines import GreedyIngredientMatchPlanner


def _facts_of(user_message: str) -> str:
    return " ".join(line[2:] for line in user_message.splitlines() if line.startswith("- "))


class _Stub:
    def __init__(self, reply):
        self.reply, self.calls = reply, 0

    def complete_text(self, messages, max_tokens=None):
        self.calls += 1
        out = self.reply(messages[-1]["content"])
        if isinstance(out, Exception):
            raise out
        return out


def test_explain_never_changes_the_plan(ctx, optimised_week):
    scenario, plan = optimised_week
    before = plan.model_dump()
    explain(scenario, plan, ctx)
    explain(scenario, plan, ctx, Paraphraser(_Stub(_facts_of), ingredient_vocabulary(ctx.store)))
    assert plan.model_dump() == before


def test_without_a_paraphraser_everything_is_template_text(ctx, optimised_week):
    scenario, plan = optimised_week
    explanation = explain(scenario, plan, ctx)
    assert explanation.sections and all(s.source == "template" and s.note == "" for s in explanation.sections)
    assert explanation.to_text() == explain_facts(build_facts(scenario, plan, ctx)).to_text()


def test_a_faithful_paraphraser_replaces_overview_and_days_only(ctx, optimised_week):
    scenario, plan = optimised_week
    p = Paraphraser(_Stub(_facts_of), ingredient_vocabulary(ctx.store))
    explanation = explain(scenario, plan, ctx, p)
    by_key = {s.key: s for s in explanation.sections}
    assert by_key["overview"].source == "llm"
    assert all(by_key[f"day:{d}"].source == "llm" for d in range(7))
    assert all(s.source == "template" for k, s in by_key.items() if k in ("rules", "caveats"))


def test_a_misbehaving_model_leaves_exactly_the_template_text(ctx, optimised_week):
    scenario, plan = optimised_week
    template = explain(scenario, plan, ctx).to_text()
    for reply in (lambda u: _facts_of(u) + " It has 999 g of sugar.",       # invented number
                  lambda u: "Healthy, delicious dinners await.",            # drops everything, makes claims
                  lambda u: RuntimeError("model crashed")):                 # transport failure
        p = Paraphraser(_Stub(reply), ingredient_vocabulary(ctx.store))
        assert explain(scenario, plan, ctx, p).to_text() == template


def test_baseline_plans_can_be_explained_too(ctx, optimised_week):
    scenario, _ = optimised_week
    plan = GreedyIngredientMatchPlanner(ctx).plan(scenario)
    explanation = explain(scenario, plan, ctx)
    assert explanation.facts.solver is None
    assert len([s for s in explanation.sections if s.key.startswith("day:")]) == scenario.horizon_days
    assert "planner's own scoring" not in explanation.to_text()
