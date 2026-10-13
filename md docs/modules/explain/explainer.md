# `src/explain/explainer.py`

## Purpose

The single entry point: a plan in, an `Explanation` out.

```python
from explain.explainer import explain
from explain.paraphrase import build_paraphraser
from llm.client import LlmClient

text = explain(scenario, plan, ctx).to_text()                       # templates only: instant, always works

p = build_paraphraser(LlmClient(), ctx.store)                       # None if the model is not reachable
text = explain(scenario, plan, ctx, p).to_text()                    # reworded where the validator allows
```

## Public API

| Name | What |
| --- | --- |
| `explain(scenario, plan, ctx, paraphraser=None) -> Explanation` | `build_facts` → `render` → optional `paraphrase_explanation` |
| `explain_facts(facts) -> Explanation` | Render facts the caller already built (no paraphrase) |

## Decisions

* **The paraphraser is injected**, so the planner/UI decides whether to pay ~20 s of LLM time; nothing here reaches
  for a model by itself.
* **The plan is never mutated** (tested).
* **Explanations of baseline plans work** (greedy, random): they simply have no solver cost-term sentences.

## Tests

[`tests/explain/test_explainer.py`](../tests/explain/test_explainer.md)

## Change log

- 2026-10-13 — Created.
