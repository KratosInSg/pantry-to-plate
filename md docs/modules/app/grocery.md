# `src/app/grocery.py`

## Purpose

Present "what to buy" for a plan. The *amounts* are not computed here: they are whatever the pantry could not cover when
the plan's dinners are replayed in order (`optimizer.inventory.account_inventory`) — the same numbers the evaluation
scores and the explainer cites. This module adds names, food group, the first day each item is needed, and a `minor`
flag for pinches.

## Public API

| Name | What |
| --- | --- |
| `build_grocery_box(report, store, start_weekday=0) -> GroceryBox` | Items sorted by when they are first needed, then largest first |
| `UNKNOWN_GROUP = "other"` | Group for an ingredient with no food group |

## Decisions

* **Staples never appear.** Salt, water and the like are `ignore_ids` in the replay, so they are not groceries — the
  recipe view shows them as `staple` lines instead.
* **Pinches are listed, not hidden.** `minor` lets a UI fold them away, but `n_items` always equals the replay's
  `n_grocery_items`, so the count a user sees matches the evaluation.
* **No units conversion.** Grams are shown as grams (the data has no purchasable pack sizes); "2 eggs" instead of
  "100 g egg" is a presentation refinement for later.

## Tests

[`tests/app/test_grocery.py`](../tests/app/test_grocery.md) — against the replay on a fake catalogue where every number
is stated by hand.

## Change log

- 2026-10-13 — Created.
