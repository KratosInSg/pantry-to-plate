# `src/optimizer/inventory.py`

## Purpose

Replay a week of dinners against a pantry and report what was **used, bought and wasted**. One definition, three users:

* the application shows the **grocery box** from it,
* the evaluation replays *every* method's plan through the same function so metrics are comparable,
* the optimiser's own objective mirrors these definitions (a test cross-checks them).

## Rules of the replay

1. Days are processed in order; each dinner needs `grams_per_serving` of each ingredient.
2. Demand is served from the pantry **if the stock is still usable that day** (`day <= last_use_day`, or no deadline).
   Whatever the pantry cannot serve is a **grocery**.
3. Assumed-available staples (`ignore_ids`: salt, pepper, water) are ignored entirely.
4. After the last dinner, stock that is left is **waste** if its deadline fell inside the horizon (it spoiled), else
   **unused** (it keeps).
5. If a plan wants stock already past its deadline, that demand is bought instead — the user is never told to cook
   with expired stock — and the grams are reported in `expired_demand_g`. That is a *diagnostic* (stock stranded, the
   ingredient bought a second time), **not** a constraint breach.

Which deadline? The caller chooses: planner-visible `last_use_day` values answer "what do we tell the user"; the
scenario's hidden `true_last_use_day` measures what *really* happens.

## Public API

| Name | What |
| --- | --- |
| `account_inventory(recipe_indices, pantry, catalog, last_use_day, ignore_ids=(), horizon_days=None) -> InventoryReport` | The replay. A `None` entry in `recipe_indices` is a skipped day: nothing used or bought, deadlines still count down |
| `deadlines_from_pantry(pantry) -> {ingredient_id: day \| None}` | Planner-visible deadlines; the earliest finite deadline wins for duplicate stocks |
| `visible_deadlines(pantry, horizon_days)` | The same, with deadlines at/after the horizon read as "no deadline" — the one definition shared by the explainer and the app |
| `InventoryReport` | `consumed_g`, `groceries_g`, `waste_g`, `unused_g`, `expired_demand_g`, `pantry_g`, `uses_by_day`, `groceries_by_day`, `expiring_ids` + totals (`total_waste_g`, `n_grocery_items`, `expiring_pantry_g`, …) |

## Invariant

Everything that entered the kitchen is accounted for: `total_pantry_g = consumed + waste + unused` (tested).

## Limits

* Greedy allocation: pantry stock is used on the first day that wants it. For one ingredient that is optimal; the
  optimiser's model chooses the same total, which is why their cost terms agree.
* Whole-ingredient granularity (no partial packs, no "buy a 500 g pack for 120 g of need").

## Tests

[`tests/optimizer/test_inventory.py`](../tests/optimizer/test_inventory.md)

## Change log

- 2026-10-12 — Created. `expired_demand_g` documented as a diagnostic, not a violation: the metric
  `known_expiry_violation_g` that was first built on it was removed because the replay can never schedule expired
  stock; the real guarantee is structural (no pantry-use variable after a deadline in the model).
- 2026-10-13 — Added `groceries_by_day` (so the grocery box and the explainer share one source), support for `None`
  (skipped) days, and `visible_deadlines`.
