# `src/preference/scorer.py`

## Purpose

Per-recipe preference score for one user, vectorised over the whole catalogue.

## Formula

```
score = clip( 0.5
              + 0.20 * cuisine_match            (+1 liked cuisine, −1 disliked, 0 otherwise)
              + 0.25 * min(1, liked_hits / 2)   (liked ingredients present, saturating at 2)
              − 0.35 * min(1, disliked_hits)    (any disliked ingredient is a strong negative)
              + 0.10 * (2 * popularity − 1)
              + 0.25 * confidence * (2 * nearest − 1),   0, 1 )
```

`nearest` is the rating-history term (`preference.history.nearest_dish_scores` over `UserProfile.rated_dinners`): a
rank in (0, 1] of how close the recipe is to the user's 10 nearest liked dinners, ingredients and tags, with 0.5 =
typical. `confidence` = min(1, liked dinners / 10), so one loved dinner nudges and ten count fully. Without rated
dinners the term is 0, which leaves new users and the planning benchmark scored exactly as before (tested).

`popularity` is the Bayesian-smoothed Food.com **train** rating mapped from [3.5, 5] to [0, 1]; unrated recipes are a
neutral 0.5. Its weight is small on purpose: Food.com ratings are heavily skewed (≈72 % are 5 stars), so they say
little beyond "not terrible". All weights live in `PreferenceWeights` so they can be tuned on **validation** scenarios.

## Public API

| Name | What |
| --- | --- |
| `score_recipes(catalog, profile, ignore_for_likes=(), weights=DEFAULT_WEIGHTS) -> float32[n]` | The score. Pass staples (salt, pepper) in `ignore_for_likes` so liking salt does not boost every recipe |
| `popularity(catalog, weights) -> float32[n]` | User-independent rating signal in [0, 1] |
| `disliked_mask(catalog, profile) -> bool[n]` | Recipes with a disliked ingredient or in a disliked cuisine (evaluation's "disliked-meal rate") |
| `history_term(catalog, profile, ignore_for_likes=(), weights) -> float32[n]` | The rating-history term alone, in [-1, 1]; all zeros without a usable liked dinner |
| `PreferenceWeights`, `DEFAULT_WEIGHTS` | The formula's constants, including `history = 0.25` and `history_full_at = 10` |

## Decisions

* **Cold-start first.** No collaborative filtering: the MVP user has no history and a hand-set content-based score is
  honest and explainable. The ratings in the dataset are used only as a weak prior.
* **Learning from the user's own ratings, without training.** When the profile carries rated dinners (the app's
  "Loved it" mark), the history term ranks recipes by closeness to them. It is the method that best predicted real
  people's later choices (`md docs/evaluation.md`, real-taste check), and the integrated scorer keeps that quality
  on validation users (HR@10 0.240 vs popularity 0.115).
* **The history weight is hand-set** to the liked-ingredient bonus's scale (0.25): a dinner like ones you loved
  counts about as much as one with foods you say you like. The planning benchmark cannot tune it (no histories).
* **Saturation** (two liked ingredients earn the whole bonus) stops a long likes list from dominating the objective.
* **Leakage-safe.** Only train-split ratings enter; the validation/test interactions are never used.

## Limits

* No seasonality and no "had it last week" memory (variety is handled in the optimiser). The history term learns
  from likes only: a dinner rated 1–3 changes nothing (a rejected dinner is excluded by a hard rule instead).
* Cuisine labels are sparse in Food.com; most recipes have none, so the cuisine term affects a minority of recipes.

## Tests

[`tests/preference/test_scorer.py`](../tests/preference/test_scorer.md)

## Change log

- 2026-10-12 — Created.
- 2026-10-16 — No code change. `preference/history.py` now derives `liked_ingredient_ids` / `liked_cuisines` from rating histories; on real-taste validation users this route adds little over popularity (see history.md).
- 2026-10-16 — Rating-history term (`history_term`, `PreferenceWeights.history` / `history_full_at`): dinners like the ones in `UserProfile.rated_dinners` score higher. Zero without history.
