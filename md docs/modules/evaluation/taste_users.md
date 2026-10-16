# `src/evaluation/taste_users.py`

## Purpose

Build, freeze and load the **real-taste users**: 100 MealRec (Allrecipes) users whose ratings stand in for "we
suggested these dinners and they rated them". The planning benchmark's users have random, invented likes. These
users have real ones, so they test whether a preference method predicts what real people go on to enjoy.

Source: MealRec (Li et al., 2022, "MealRec: A Meal Recommendation Dataset", https://github.com/WUT-IDEA/MealRec),
raw files in `data/mealRecResearchpaper_Data/` (`recipe.csv`, `user_recipe.csv`; git-ignored, 706 MB). The frozen set
is small (about 1.5 MB) and lives in `data/evaluation/taste_v2/`. It is **git-ignored too**: MealRec's repository has
no licence for redistribution (it only asks to be cited), so each machine rebuilds it from the official download with
`python src/evaluation/taste_users.py`. The build is deterministic, and the result tables are in `Evaluation/04_real_taste_preferences/`.

## How the set is built

1. **Main dishes only** (`category == "main-dish"`): 2,552 dinners. Appetizers and desserts are not what we plan.
2. **Bridge to our vocabulary**, because MealRec ids are Allrecipes ids, not ours:
   - ingredient text → canonical ingredients, using the resolver on the whole text first and the pantry parser as a
     fallback (87.4 % of mentions mapped);
   - tags → catalogue cuisine names (Allrecipes uses Food.com's tag names), and (v2) every tag that is in the
     catalogue's 145-tag vocabulary (58 % of tag mentions; 2,547 of 2,552 dinners keep at least one);
   - name → the catalogue recipe with exactly that normalised name, linked only if exactly one recipe has it
     (984 dinners linked, 24 ambiguous).
3. **Users:** those with at least 100 rated dinners (111 users). Each user's ratings are sorted by date. The earliest
   80 are the *history* (the profile input) and the rest are *held out*. A user must have at least 3 held-out dinners
   that are linked to the catalogue and not already linked from their history (all 111 qualify).
4. **Sample:** 100 users with `SEED = 20261016`, then a 50/50 validation/test split. Written with SHA-256 hashes in
   `FROZEN.json` together with the raw files' hashes, thresholds and mapping statistics. Every load verifies the hashes.

## Public API

| Name | What |
| --- | --- |
| `TasteRecipe` | `recipe_id` (MealRec), `name`, `ingredient_ids`, `cuisines`, `catalogue_recipe_id` (or `None`), `tags` (v2; empty in v1) |
| `TasteUser`, `TasteRating` | `user_id`, `history`, `heldout`; each rating has `recipe_id`, `rating`, `date` |
| `load_taste_users(split, eval_dir)` / `load_taste_recipes(eval_dir)` | Verified load of the frozen set |
| `rated_dishes(ratings, recipes) -> list[RatedDish]` | Ratings in the form `preference.history` takes |
| `rated_dinners(ratings, recipes) -> tuple[RatedDinner, ...]` | Ratings as a `UserProfile` carries them (names; `recipe_id` = linked catalogue recipe or `None`) |
| `linked_heldout(user, recipes) -> set[int]` | Catalogue recipe ids of the held-out dinners, minus any their history links to (no leakage) |
| `map_ingredient_texts`, `catalogue_names`, `build_recipes`, `split_user`, `select_users`, `split_users`, `build_taste_set`, `freeze_taste_set` | The build steps (pure, apart from reading the raw CSVs) |
| `python src/evaluation/taste_users.py` | Build and freeze. Refuses if `FROZEN.json` exists; bump `TASTE_VERSION` for a new set |
| `TASTE_VERSION` | `"v2"`. v1 = dinners as ingredients + cuisines; v2 = the same plus tags. Same users and splits (tested) |

## Decisions

* **Split by date, not at random.** Judging a profile on the ratings it was built from would be circular; "the
  earliest 80 predict the later ones" is also how the feature would work for a real user.
* **A fixed-size history (80)** gives every user the same amount of evidence, close to the "100 suggested recipes"
  idea while leaving held-out dinners for everyone.
* **Fail loudly.** If fewer than 100 users qualify, the build raises instead of quietly taking fewer.

## Limits

* **A simulation:** these people chose and rated these dishes on Allrecipes; nobody rated a suggestion of ours.
* **Likes only** (every MealRec rating is 4 or 5), and the dates are when a review was last modified.
* Held-out dinners that can be checked are the ones whose names match the catalogue exactly, which favours classic dishes.
* **Licence:** the data was scraped from Allrecipes and released for research. Check MealRec's terms before
  publishing the derived set. The repository is public.

## Tests

[`tests/evaluation/test_taste_users.py`](../tests/evaluation/test_taste_users.md)

## Logging

Logger `evaluation.taste_users`. INFO: one line per build (dinners, linked dinners, users sampled / qualifying).

## Change log

- 2026-10-16 — Created; `taste_v1` frozen (100 users, 50 validation / 50 test).
- 2026-10-16 — `taste_v2`: each dinner also keeps its tags in the catalogue's tag vocabulary. Same users, history and splits as v1 (tested); v1 stays on disk for the record.
- 2026-10-16 — `rated_dinners()` for evaluating the production scorer path.
- 2026-10-16 — The frozen sets are git-ignored (MealRec carries no licence); rebuild locally.
