# `src/explain/` — turning a plan into plain English

## Purpose

Say, in words, what the planner did and what it did *not* manage — in a way that traces back to something real. The
project's non-negotiable is that **explanations trace to an actual solver cost term or fired rule, never a
rationalisation**; this package is built so that every sentence carries its origin (`Statement.term`,
`Statement.source`) and so that a language model can reword it only if it adds and drops nothing checkable.

## Pipeline

```
Scenario + WeekPlan + PlanningContext
  │  facts.build_facts        the replay (used / bought / wasted), hard-rule counts, the user's own targets,
  ▼                           and the optimiser's per-term costs  ->  PlanFacts (typed, immutable)
  │  render.render            deterministic templates, one Statement per fact, grouped into Sections
  ▼
Explanation (always complete and correct on its own — no LLM needed)
  │  paraphrase.paraphrase_explanation   OPTIONAL: LLM rewords overview + day sections; each answer is validated
  ▼                                      against that section's facts, else the template text is kept
Explanation (Section.source = "template" | "llm")
```

## Files

| File | Role | Doc |
| --- | --- | --- |
| `facts.py` | `PlanFacts` and `build_facts`: everything that may be said, as data | [facts.md](facts.md) |
| `render.py` | Templates, `Statement` / `Section` / `Explanation` | [render.md](render.md) |
| `paraphrase.py` | Optional LLM rewording + the validator that guards it | [paraphrase.md](paraphrase.md) |
| `explainer.py` | `explain(scenario, plan, ctx, paraphraser=None)` | [explainer.md](explainer.md) |

## Rules this package keeps

1. **Reads, never decides.** Nothing here changes, ranks or re-solves a plan (tested: the plan is bit-identical after
   `explain`).
2. **Same numbers as the app.** Used / bought / wasted come from `optimizer.inventory.account_inventory`, the replay the
   grocery box and the evaluation use — an explanation can never disagree with them.
3. **Misses are stated as misses.** Below the calorie band, protein short, over the time limit, expiring stock that
   will still go unused, stock that expires before the dinner that needs it. No health or taste claims.
4. **No LLM, no problem.** Templates are complete; the paraphrase is an optional layer and any failure leaves the
   template text untouched.
5. **Safety text is never reworded.** The `rules` and `caveats` sections do not reach the model.

## Change log

- 2026-10-13 — Package created: facts, templates, validated paraphrase, entry point. Optimiser now reports per-term
  costs (`cost_<term>`) so explanations can cite them.
