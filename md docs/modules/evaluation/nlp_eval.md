# `src/evaluation/nlp_eval.py`

## Purpose

Evaluation measure 7: **ingredient NLP precision, recall and F1**, plus quantity and urgency accuracy, on the frozen
synthetic pantry messages (`evaluation.pantry_messages`). Optionally, **parse-then-plan**: what reading the user's words
(instead of a structured pantry) costs the week's plan.

## How items are scored

1. Each message is parsed as the app parses user text (`nlp.PantryParser`, rules only unless `--llm`), with the
   message's own `today`.
2. Alignment by ingredient: a gold item is **found** when a *confidently* resolved parsed item has its canonical id.
   Misses are classified from what the parser did with the item's own phrase: `wrong_ingredient` (confident, different
   id - also a false positive), `asked_user` (ambiguous), `not_recognised`, `no_item`. Confident parsed items with no
   gold partner are `spurious` (false positives).
3. On found items: **quantity** (metric mass within 1 %, metric volume within 2 %, counts/containers by value and unit,
   "no amount" recognised), **urgency** (none/soon/urgent) and **stated dates** (day index).
4. Micro P/R/F1 over items; 95 % bootstrap CIs resampling whole messages; breakdowns by name variant, amount form and
   cue kind; urgency confusion matrix; message exact match.

Parse-then-plan (`--plan <planner>`): each v3 kitchen is planned from its frozen pantry and from
`domain.pantry.pantry_from_parse(parse)`; **both plans are judged on the same frozen kitchen** with
`evaluation.metrics.evaluate_plan`; paired differences with bootstrap CIs.

## Public API

| Name | What |
| --- | --- |
| `score_message(message, parse, store) -> list[ItemRow]` | Alignment + per-item scores |
| `quantity_correct`, `days_correct` | The per-field rules above |
| `prf(df)`, `summary(df)`, `breakdown(df, by)`, `urgency_confusion(df)`, `message_exact(df)`, `bootstrap_cis(df)` | Aggregates |
| `run_parse(eval_dir, store, use_llm)` | Parse and score every message |
| `run_parse_then_plan(eval_dir, planner, messages, results, store)`, `compare_sources(df)` | The planning check |

CLI:

```bash
python src/evaluation/nlp_eval.py --eval-dir data/evaluation/v3 --save
python src/evaluation/nlp_eval.py --eval-dir data/evaluation/v3 --plan optimiser --save
```

## Results

`Evaluation/08_ingredient_nlp/` (run 2026-10-21, rules only).

## Limits

* Synthetic labels (see `pantry_messages.md`); the LLM fallback was not run (no model in the evaluation environment).
* Strict canonical matching: a near-synonym entry (e.g. *green bell pepper* for *green pepper*) counts as wrong.

## Tests

[`tests/evaluation/test_nlp_eval.py`](../tests/evaluation/test_nlp_eval.md)

## Logging

Logger `evaluation.nlp_eval`. INFO: parse time and planning progress. Only `main()` configures logging.

## Change log

- 2026-10-21 — Created: alignment, miss taxonomy, P/R/F1 with message-level bootstrap, breakdowns, parse-then-plan.
