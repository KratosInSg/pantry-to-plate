# `src/app/models.py`

## Purpose

The types that cross the backend ↔ UI boundary. Two kinds on purpose:

* **Inputs the user edits** — `PantryEntry`, `PantryReview`, `IngredientChoice`: pydantic, mutable, validated,
  JSON-serialisable (a UI can keep them in session state; a future HTTP API can accept them as they are).
* **Results to show** — `PlannedWeek`, `DayPlan`, `IngredientLine`, `GroceryBox`, `GroceryItem`: frozen dataclasses.

## Public API

| Name | What |
| --- | --- |
| `PantryEntry` | One review row: `raw_text`, `ingredient_id`, `name`, `food_group`, `grams`, `quantity_assumed`, deadline fields, `status`, `problem`, `suggestions`, `warnings`. `usable`, `to_pantry_item()`, `with_grams(g)`, `with_days_left(d)` |
| `PantryReview` | `source_text`, `entries`, `unparsed`; `usable_entries`, `needs_attention` |
| `IngredientChoice` | `ingredient_id`, `name`, `score` — an autocomplete hit or a "did you mean" |
| `ENTRY_OK` / `ENTRY_ASSUMED` / `ENTRY_CHOOSE` / `ENTRY_UNKNOWN` / `ENTRY_NO_AMOUNT` / `ENTRY_UNSAFE` | What the UI should do with a row; `USABLE_STATUSES` = ok + assumed |
| `PlannedWeek` | `scenario`, `plan`, `days`, `grocery_box`, `explanation`, `status`, `complete`, `solve_seconds`, `day_offset`, `expired`; `overview`, `rules`, `caveats`, `recipe_ids` |
| `DayPlan` | `day`, `weekday`, `recipe_id`, `name`, `minutes`, `cuisine`, nutrition, `ingredients`, `steps`, `explanation` (a `Section`) |
| `IngredientLine` | `name`, `grams`, `from_pantry_g`, `to_buy_g`, `staple`, `use_by_day`, `deadline_known`, `substituted_by` ("milk (25 g) and lemon juice (1.7 g)" when a substitution rule replaced buying it, else "") |
| `GroceryBox` / `GroceryItem` | `items`, `n_items`, `total_g`, `by_group()`; item has `food_group`, `first_needed_day`, `weekday`, `minor` |
| `MINOR_GROCERY_G = 5.0` | Below this an item is a pinch (`minor`): listed, but a UI may fold it away |

## Decisions

* **A row that is not usable is never planned with** (`usable` is false for unrecognised / ambiguous / no-amount /
  unsafe). The UI must resolve it or leave it out; the planner never sees a guess.
* **Editing the amount clears the assumption** (`with_grams`): once the user says "120 g", it is no longer "assumed".
* **A stated use-by is a known, hard deadline** (`with_days_left`), exactly as if they had typed "expires tomorrow".
* **`PlannedWeek` carries its `scenario`**, which is what makes re-planning a pure function of the week the user is
  looking at.

## Limits

* `PantryEntry` re-derives a deadline from the cue it kept (`days_left_hint`, `days_left_explicit`) when the user
  picks a different ingredient; it does **not** keep "leftover" / "frozen" modifiers, so those fall back to the
  FoodKeeper estimate for the chosen ingredient.

## Tests

Exercised through [`tests/app/test_service.py`](../tests/app/test_service.md).

## Change log

- 2026-10-13 — Created.
- 2026-10-16 — `IngredientLine.substituted_by`.
- 2026-10-17 — `PantryEntry.food_group` (the ingredient's dataset food group; presentation only, picks the row's icon; `None` while the row has no ingredient).
