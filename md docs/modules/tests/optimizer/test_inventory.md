# `tests/optimizer/test_inventory.py`

Tests [`optimizer/inventory.py`](../../optimizer/inventory.md) with a tiny fake catalogue so each test states its
numbers by hand: a failure reads as a broken rule, not a changed dataset.

| Test | Pins |
| --- | --- |
| `test_pantry_is_used_first_then_the_rest_is_bought` | 100 g stock, 2 × 60 g demand → consume 100, buy 20 |
| `test_stock_that_expires_unused_is_waste` | deadline inside the horizon → waste, and it is in `expiring_ids` |
| `test_stock_with_a_deadline_beyond_the_horizon_is_unused_not_waste` | keeps → `unused_g` |
| `test_demand_after_the_deadline_is_bought_and_reported` | expired stock is never used; demand bought; diagnostic recorded |
| `test_deadline_day_is_inclusive` | day == `last_use_day` is still usable |
| `test_ignored_staples_never_count` | salt-like ids absent from every total |
| `test_duplicate_stocks_are_summed` | |
| `test_uses_by_day_records_where_stock_went` | per-day usage for the explainer |
| `test_mass_balance` | pantry = consumed + waste + unused |
| `test_deadlines_from_pantry_earliest_wins_and_none_means_never` | duplicate-stock deadline rule |

## Change log

- 2026-10-12 — Created.
- 2026-10-13 — Added `test_groceries_by_day_records_where_the_shortfall_arises_and_sums_to_the_total` and `test_a_skipped_day_uses_nothing_but_still_counts_down_deadlines`.
