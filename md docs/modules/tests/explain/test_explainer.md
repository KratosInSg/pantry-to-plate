# `tests/explain/test_explainer.py`

Tests [`explain/explainer.py`](../../explain/explainer.md): the three stages composed, and the guarantees that matter end
to end.

| Test | Pins |
| --- | --- |
| `test_explain_never_changes_the_plan` | `plan.model_dump()` identical before and after, with and without a paraphraser |
| `test_without_a_paraphraser_everything_is_template_text` | every section `template`, no notes; equals `explain_facts(build_facts(...))` |
| `test_a_faithful_paraphraser_replaces_overview_and_days_only` | overview and 7 days `llm`; rules / caveats stay `template` |
| `test_a_misbehaving_model_leaves_exactly_the_template_text` | invented number, claims-and-dropped-everything, and a transport error each yield *exactly* the template text |
| `test_baseline_plans_can_be_explained_too` | greedy plan: 7 day sections, no solver-score sentence |

## Change log

- 2026-10-13 — Created.
