# `src/domain/models.py`

## Purpose

The shared, validated data shapes of the planning path. Pydantic models, so they validate on construction, serialise
with `model_dump_json()` (the benchmark is stored that way) and fail loudly on nonsense.

## Where it sits

```
nlp.ParseResult ──pantry_from_parse──▶ list[PantryItem] ─┐
UI / benchmark generator ───────────▶ UserProfile ───────┼─▶ Scenario ──▶ planner ──▶ WeekPlan ──▶ evaluator / explainer
```

## Public API

| Name | What |
| --- | --- |
| `Diet` | `omnivore`, `pescatarian`, `vegetarian` (no meat, fish or eggs; dairy fine), `vegan` — each a hard rule |
| `ALLERGENS` | The nine allergen names; each maps to a `contains_<name>` flag on ingredients and recipes |
| `UserProfile` | Hard constraints (diet, allergens, pork, alcohol, excluded ingredients, **excluded recipes** (rejected dinners), optional time cap, **`dinner_only`**), soft preferences (likes/dislikes, cuisines, weekday time limit, **`rated_dinners`** — the rating history) and nutrition targets |
| `RatedDinner` | A dinner the user rated (frozen): `rating` 1–5 (4–5 = liked), `name`, `recipe_id` (our Food.com id, or `None` for a dish from elsewhere), `ingredient_ids`, `tags`, `cuisines`. Soft evidence for `preference.history`; never allows or forbids anything |
| `PantryItem` | `ingredient_id`, `grams`, `last_use_day`, `expiry_known`, `expiry_confidence`, `urgency`, `quantity_assumed` |
| `Scenario` | One planning problem: profile + pantry + horizon + start weekday (+ hidden truth for benchmarks). `is_weekday(day)` |
| `WeekPlan` | `planner`, `recipe_ids` (index = day), `status`, `diagnostics`. `is_complete` |
| `HORIZON_DAYS = 7`, `WEEKDAYS_PER_WEEK = 5` | Plan length; Monday–Friday are indices 0–4 |

## Decisions

* **Hard vs soft is visible in the field list.** The first block of `UserProfile` forbids; the second block only
  scores. A reader can see what can never be traded off.
* **Nutrition targets are planning support, not medical advice.** `dinner_kcal_range` is a band; no penalty applies
  inside it.
* **`WeekPlan.status`** is one of `ok | optimal | feasible | partial | infeasible | no_candidates`. `is_complete` is
  true only for the first three *and* a non-empty plan, so an "infeasible user" is never mistaken for a plan.
* **Unknown allergens are rejected** at construction: a typo ("peanuts") must not silently disable a safety rule.

## Limits

* One person, one serving per dinner (MVP scope).
* No dates: days are offsets from today; the UI is responsible for mapping calendar dates to offsets.

## Tests

[`tests/domain/test_models.py`](../tests/domain/test_models.md)

## Change log

- 2026-10-12 — Created.
- 2026-10-13 — `UserProfile.excluded_recipe_ids` (a rejected dinner) and `dinner_only` (opt-in, default off so the
  frozen benchmark is unchanged); `PantryItem.quantity_assumed`. All additions have defaults, so stored scenarios
  still load.
- 2026-10-14 — `Diet.VEGETARIAN` documented as no meat, fish or eggs.

- 2026-10-15 — New `RESTRICTABLE_FOOD_FLAGS` and validated `UserProfile.excluded_food_groups` opt-in exclusions.
- 2026-10-16 — `RatedDinner` and `UserProfile.rated_dinners` (default empty, so stored scenarios and the frozen benchmark load unchanged, tested).
