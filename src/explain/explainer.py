"""The explainer's single entry point: a plan in, a sectioned plain-English explanation out.

    facts = build_facts(scenario, plan, ctx)        # what can honestly be said            (facts.py)
    text  = render(facts)                           # deterministic sentences, always works (render.py)
    text  = paraphrase_explanation(text, p)         # optional, validated LLM rewording     (paraphrase.py)

``explain`` runs the three in order. Without a paraphraser the result is the template text, which is complete and
correct on its own: every feature must work without the LLM (CLAUDE.md).
"""
from __future__ import annotations

from domain.models import Scenario, WeekPlan
from explain.facts import PlanFacts, build_facts
from explain.paraphrase import Paraphraser, paraphrase_explanation
from explain.render import Explanation, render
from optimizer.planning import PlanningContext


def explain(scenario: Scenario, plan: WeekPlan, ctx: PlanningContext,
            paraphraser: Paraphraser | None = None) -> Explanation:
    """Explain ``plan`` for ``scenario``.

    Args:
        scenario: the user, pantry and horizon the plan was made for.
        plan: any planner's plan. Optimiser plans additionally get the solver's cost-term summary.
        ctx: planning context (catalogue + knowledge store).
        paraphraser: optional validated LLM rewording of the overview and per-day sections; ``None`` keeps templates.
    """
    explanation = render(build_facts(scenario, plan, ctx))
    return paraphrase_explanation(explanation, paraphraser) if paraphraser is not None else explanation


def explain_facts(facts: PlanFacts) -> Explanation:
    """Render already-built facts (no paraphrase). Useful when the caller also needs the facts themselves."""
    return render(facts)
