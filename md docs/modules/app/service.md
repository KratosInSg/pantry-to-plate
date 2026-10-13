# `src/app/service.py`

## Purpose

`PantryToPlateService`: the one object a UI talks to. It is the *order* in which the backend's packages are called,
written once and tested, so a frontend is only layout. It decides nothing.

```python
service = PantryToPlateService(llm=LlmClient())            # llm optional; omit for a fully rules-based app
review  = service.review_pantry("spinach going off, 500g chicken, 6 eggs, a tub of kimchi")
# the UI shows review.entries; the user fixes rows (choose_ingredient / with_grams / with_days_left / add_pantry_entry)
pantry  = service.pantry_items(review.entries)
profile = service.build_profile(diet="vegetarian", allergens=["peanut"], liked_cuisines=["italian"]).profile
week    = service.plan_week(service.make_scenario(profile, pantry))
week    = service.replan(week, cooked=[week.days[0].recipe_id, None], rejected=[week.days[3].recipe_id])
```

## Public API

| Method | What |
| --- | --- |
| `cuisines()` | Sorted cuisine names for a dropdown |
| `search_ingredients(query, limit=8)` | Autocomplete: prefix matches first, then fuzzy; one hit per ingredient |
| `resolve_names(names) -> NameResolution` | Typed food names → ids; `unresolved` and `ambiguous` (with candidates) are reported, never guessed |
| `build_profile(...) -> ProfileBuild` | Validated `UserProfile` from plain form values; `dinner_only=True` by default; raises `ValueError` naming the valid options for an unknown diet / allergen / cuisine |
| `review_pantry(text, today=None)` | Free text → `PantryReview` (rows with honest statuses and suggestions) |
| `add_pantry_entry(ingredient_id, grams, days_left=None, urgent=False)` | A row added by hand |
| `choose_ingredient(entry, ingredient_id)` | Resolve a "did you mean?" row; keeps the amount, re-derives the deadline |
| `pantry_items(entries)` | Usable rows → merged `PantryItem`s (staticmethod) |
| `make_scenario(profile, pantry, today=None, horizon_days=7)` | The planning problem; weekday names start from `today` |
| `plan_week(scenario, paraphrase=False)` | Plan → explain → present (`PlannedWeek`) |
| `reword(planned)` | Validated LLM rewording of the reasons; returns `planned` unchanged if no model is reachable |
| `replan(planned, cooked=(), rejected=(), paraphrase=False)` | Re-plan the remaining days from the current pantry |
| `llm_available()` | A model is configured and reachable right now |

## How re-planning works

`replan` is a *roll forward* (`optimizer/replan.py`), not a new optimiser feature: the dinners that were actually
cooked (`None` = skipped) are replayed, what they used leaves the pantry, stock that went off is dropped (and reported
by name in `PlannedWeek.expired`), deadlines shift, and the new problem has fewer days and a later start weekday.
Rejected recipe ids are added to the scenario profile's `excluded_recipe_ids`, so they stay excluded through later
re-plans. Food a skipped or rejected dinner would have used is still in the pantry, closer to its deadline — which is
exactly what the waste term chases.

## Decisions

* **Parse via the planner's own deadline ladder.** Each review row is built with `pantry_from_parse`, so what the user
  sees ("use by Thursday, estimated") is what the planner will be told.
* **An unresolved row blocks nothing but is never planned with.** `pantry_items` keeps usable rows only.
* **`build_profile` never turns an unknown name into a different food.** Unmatched names are listed in
  `resolution`/`notes` and left out.
* **The LLM is injected, probed lazily and used in two places only:** re-reading pantry text the rules could not
  understand, and rewording explanations (validated; template text kept on any rejection).

## Limits

* One user, one household, dinners only; no persistence (a UI keeps the `PlannedWeek` / `PantryReview` in session
  state).
* A re-plan re-optimises *all* remaining days jointly (as specified in `systemflow.md`); there is no "keep Thursday,
  change only Wednesday" yet, and no alternatives-with-trade-offs or counterfactual diff.
* ~4–6 s per full plan (HiGHS); a short re-plan is faster. Run it off the UI thread / behind a spinner.

## Tests

[`tests/app/test_service.py`](../tests/app/test_service.md) — real dataset and optimiser (small shortlist).

## Change log

- 2026-10-13 — Created.
