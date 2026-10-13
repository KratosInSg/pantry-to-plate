# `src/app/` — what a UI calls

## Purpose

One object, `PantryToPlateService`, that turns the backend's eight packages into the handful of operations a frontend
needs: *understand the pantry, build a profile, plan the week, show the reasons and the grocery box, and re-plan when
life happens*. It decides nothing — planning is `optimizer`, reasons are `explain` — so a UI built on it is layout only.

## The flow a UI follows

```
text ──review_pantry──▶ PantryReview (rows: ok / assumed_quantity / needs_choice / unrecognised / no_amount)
        │  user fixes rows:  choose_ingredient · with_grams · with_days_left · add_pantry_entry
        ▼
   pantry_items(rows) ─┐
build_profile(form) ───┼─▶ make_scenario ──▶ plan_week ──▶ PlannedWeek (days, grocery_box, explanation)
                       │                                      │
                       │      reword(week)  (optional, LLM)   │
                       └──────── replan(week, cooked, rejected) ◀─ day skipped / dinner rejected
```

## Files

| File | Role | Doc |
| --- | --- | --- |
| `models.py` | `PantryEntry` / `PantryReview` (editable inputs) and `PlannedWeek`, `DayPlan`, `GroceryBox` (results) | [models.md](models.md) |
| `grocery.py` | `build_grocery_box`: the replay, presented as a shopping list | [grocery.md](grocery.md) |
| `service.py` | `PantryToPlateService`: the facade | [service.md](service.md) |

## Rules

1. **Nothing here is a new source of truth.** Quantities come from the inventory replay, reasons from `explain`, the
   plan from `optimizer`. A test checks that the grocery box equals the sum of what each dinner needs to buy.
2. **The LLM is optional everywhere.** `PantryToPlateService(llm=None)` is a complete application.
3. **Nothing is guessed silently.** An unrecognised or ambiguous pantry row is *not* planned with until the user
   resolves it; an assumed amount is flagged on the row and again in the explanation.
4. **Inputs are editable pydantic models; results are frozen dataclasses**, so a plan that has been explained cannot be
   changed under the explanation.

## Change log

- 2026-10-13 — Package created (service facade, models, grocery box).
