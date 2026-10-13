# `src/domain/pantry.py`

## Purpose

Turn *what the user typed* (`ParseResult`) into *what the planner is told*: `PantryItem`s with grams and a deadline.
This is the one place that decides **how much to believe about expiry**, so the app and the benchmark generator tell
the planner exactly the same thing for the same situation.

## Public API

| Name | What |
| --- | --- |
| `pantry_from_parse(result, store, horizon_days=7) -> PantryBuild` | Convert a parse. `PantryBuild.items` are usable; `PantryBuild.skipped` lists `(ParsedItem, reason)` |
| `estimate_last_use_day(shelf, horizon_days=7) -> (day \| None, confidence)` | Deadline estimate for an item of *unknown age* from its FoodKeeper default |
| `make_pantry_item(ingredient_id, grams, store, days_left=None, urgency=NONE, horizon_days=7, days_left_explicit=True)` | An item built without text (the UI's "add item", or a corrected ingredient): a stated `days_left` is a known hard deadline; a vague cue is an estimate; none = the FoodKeeper estimate |
| `merge_pantry_items(items)` | The duplicate-merge rule below, exposed so a UI that edits rows can re-apply it |
| `SKIP_UNKNOWN`, `SKIP_AMBIGUOUS`, `SKIP_NO_AMOUNT`, `SKIP_UNSAFE` | Reason codes in `PantryBuild.skipped`, so a UI branches on constants, not on text |
| `UNKNOWN_AGE_REMAINING_FRACTION = 0.5`, `LEFTOVER_DAYS = 3` | The two planning assumptions |

## How the deadline is chosen (in this order)

| # | Situation | `last_use_day` | `expiry_known` | confidence |
| --- | --- | --- | --- | --- |
| 1 | User stated a date/duration ("expires tomorrow") | that day (`None` if beyond the horizon) | **True** | 1.0 |
| 2 | User used a qualitative cue ("going bad" = 1 d, "getting old" = 3 d) | the assumed days | False | 0.6 |
| 3 | Leftover / cooked food | 3 days (food-safety rule of thumb) | False | 0.6 |
| 4 | Frozen | `None` | False | 0.7 |
| 5 | Nothing said | half of FoodKeeper's typical (min+max)/2, minus one (index) | False | 0.7 / 0.5 / 0.3 by how the shelf-life link was made |

Shelf lives that reach past the horizon become `None`, so long-life staples never create waste.

## Skipped items (with a reason, never silently dropped)

unrecognised ingredient · ambiguous match ("ask the user") · no amount · flagged as possibly unsafe (mouldy …).

## Merging duplicates

Same ingredient twice → grams add up, the **earliest** deadline wins, a known date beats an estimate, the most urgent
urgency level is kept, and `quantity_assumed` is true if *any* part of the stock was an assumed amount.

## Why "half the typical shelf life"?

We do not know how old a pantry item is. Assuming it is brand new would hide waste; assuming it is about to expire
would force silly plans. Half is a neutral planning assumption — **labelled as an estimate with low confidence**, never
presented as a date. It is a named constant so it can be tuned on validation scenarios.

## Limits

* The estimate ignores storage conditions (fridge vs counter) beyond what the FoodKeeper default encodes.
* A merged stock keeps only one deadline: 100 g expiring tomorrow + 100 g keeping all week becomes 200 g expiring
  tomorrow (conservative; splitting stocks is a possible refinement).

## Tests

[`tests/domain/test_pantry.py`](../tests/domain/test_pantry.md)

## Change log

- 2026-10-12 — Created. `estimate_last_use_day` is shared with the benchmark generator.
- 2026-10-13 — `PantryItem.quantity_assumed` is carried from the parse (so the explainer can say "we assumed 250 g");
  added `make_pantry_item`, `merge_pantry_items` and the `SKIP_*` reason constants for the app layer.
