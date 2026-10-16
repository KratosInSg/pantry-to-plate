# `src/preference/history.py`

## Purpose

Learn preferences from a **rating history** without training a model: the slide's preference model "learns from meal
ratings". Given the dishes a user rated, expressed as canonical ingredients, cuisine labels and tags, it provides:

* **likes** in the *existing* `UserProfile` fields (`liked_ingredient_ids`, `liked_cuisines`), so the scorer,
  optimiser and explainer use them unchanged ("plug and play"), each with recorded evidence; and
* two **graded content scores** of every catalogue recipe against the dishes the user liked:
  - `history_similarity`: closeness to the *average* liked dish, ingredients only;
  - `nearest_dish_scores`: closeness to the user's *nearest* liked dishes, ingredients and tags, which keeps mixed
    tastes apart. This is the best method in the evaluation.

`preference.scorer` uses `nearest_dish_scores` for a profile's `rated_dinners`, and the explainer names the
closest liked dinners with `nearest_rated`.

Today's rating source is the frozen MealRec real-taste users (`evaluation/taste_users.py`). The same functions can
take the app's own "how did it go?" marks later.

## Public API

| Name | What |
| --- | --- |
| `RatedDish(ingredient_ids, cuisines, rating, tags=frozenset())` | One rated dish in our vocabulary (rating 1–5; tags from the catalogue's tag vocabulary) |
| `base_rates(pool) -> BaseRates` | Share of a reference pool of dishes containing each ingredient / cuisine ("people in general") |
| `derive_likes(history, rates, ignore_ids=(), cuisine_vocabulary=None, config=DEFAULT_CONFIG) -> DerivedLikes` | Liked ingredients and cuisines plus `evidence` (support, base rate, lift) and `n_liked_dishes` |
| `as_profile_fields(likes)` | `{"liked_ingredient_ids": ..., "liked_cuisines": ...}` to build or update a `UserProfile` |
| `history_similarity(catalog, history, ignore_ids=()) -> float32[n]` | Cosine in [0, 1] between each recipe and the mean of the liked dishes (binary ingredients × catalogue IDF, staples dropped). All zeros when no liked dish has a known ingredient |
| `nearest_dish_scores(catalog, history, ignore_ids=(), config=DEFAULT_NEAREST) -> float32[n]` | Per recipe: mean cosine to its `k` most similar liked dishes, over ingredients and over tags (IDF-weighted). The two parts are put on one scale by percentile rank and mixed by `tag_weight`. Values are ranks in (0, 1], so only their order matters. All zeros with no known evidence; one kind of evidence alone when the other is missing |
| `HistoryConfig`, `DEFAULT_CONFIG`, `LIKE_MIN_RATING` | Like-derivation thresholds; 4 and 5 stars count as liked |
| `NearestConfig(k=10, tag_weight=0.5)`, `DEFAULT_NEAREST` | Chosen on the validation real-taste users, then fixed before the single test run |
| `nearest_rated(catalog, history, recipe_idx, ignore_ids=(), config, n=2) -> ((position, similarity), ...)` | The liked dishes closest to one recipe (same two cosines the score ranks by) — what an explanation names |
| `Rated` | Protocol: anything with `ingredient_ids`, `cuisines`, `rating`, `tags` (`RatedDish`, `domain.models.RatedDinner`) |

## How a like is derived

Only dishes rated 4 or 5 count. For each ingredient:

- *support* = share of the user's liked dishes containing it;
- *base rate* = share of the reference pool containing it;
- *lift* = support ÷ base rate.

An ingredient is liked when support ≥ 15 % **and** lift ≥ 1.5, keeping at most 10, strongest support first. Cuisines
work the same way (support ≥ 10 %, lift ≥ 1.5, at most 3) and are restricted to the catalogue's cuisine vocabulary.
Fewer than 10 liked dishes derives nothing. The lift condition is what stops garlic and onion becoming everyone's likes.

## How the graded scores work

* **Vectors:** each catalogue recipe is a binary vector over ingredients (staples dropped) or over the catalogue's 145
  tags, weighted by inverse document frequency (rare items say more about taste) and scaled to length 1. These are
  built once per catalogue and cached.
* **Unknown items still count:** a liked dish is scaled by its *full* length, including ingredients or tags no
  catalogue recipe has. So a dish mostly made of unknown ingredients is not mistaken for a close match. (This keeps
  `history_similarity` numerically identical to its first version, which was checked when refactoring.)
* **Nearest, not average:** the average of 80 dinners blurs someone who likes both Mexican and Italian food. Taking
  the mean of the 10 most similar liked dishes keeps both tastes visible.

## Evaluation (real-taste users, 2026-10-16)

On the 50 **test** users, run once after the settings were fixed on validation (`evaluation/taste_eval.py`; MealRec
paper protocol, chance HR@10 = 0.10):

| Method | HR@10 | AUC |
| --- | --- | --- |
| Popularity only (today) | 0.119 | 0.518 |
| `derive_likes` into the existing scorer | 0.140 | 0.549 |
| `history_similarity` | 0.174 | 0.587 |
| `nearest_dish_scores` | **0.202** | **0.622** |

Against popularity, `nearest_dish_scores` adds +0.083 HR@10 [+0.040, +0.127] and +0.105 AUC [+0.075, +0.134]. Full
tables and caveats are in `md docs/evaluation.md` → "Real-taste preference check".

## Limits

* **Likes only.** No dislikes are derived: the MealRec ratings are all 4 or 5, and low ratings are ignored.
* Ingredients that never appear in the reference pool have no base rate and cannot be likes.
* The graded scores compare ingredient and tag sets only: no quantities, cooking method or nutrition.
* Content-only scores have a ceiling. On the same site, behaviour-based signals (popularity, collaborative filtering)
  predict far better (`md docs/evaluation.md`); those need our own users' interaction data.

## Tests

[`tests/preference/test_history.py`](../tests/preference/test_history.md)

## Change log

- 2026-10-16 — Created: base rates, lift-based like derivation with evidence, IDF-cosine history similarity.
- 2026-10-16 — Added `nearest_dish_scores` / `NearestConfig` and `RatedDish.tags`. Catalogue vectors are now cached
  and shared (`history_similarity` output unchanged, verified to 0.0 difference on real users).
- 2026-10-16 — `nearest_rated` (for explanations) and the `Rated` protocol, so a profile's `RatedDinner`s work directly; `nearest_dish_scores` now drives the scorer's history term.
