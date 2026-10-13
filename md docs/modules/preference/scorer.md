# `src/preference/scorer.py`

## Purpose

Per-recipe preference score for one user, vectorised over the whole catalogue.

## Formula

```
score = clip( 0.5
              + 0.20 * cuisine_match            (+1 liked cuisine, −1 disliked, 0 otherwise)
              + 0.25 * min(1, liked_hits / 2)   (liked ingredients present, saturating at 2)
              − 0.35 * min(1, disliked_hits)    (any disliked ingredient is a strong negative)
              + 0.10 * (2 * popularity − 1),    0, 1 )
```

`popularity` is the Bayesian-smoothed Food.com **train** rating mapped from [3.5, 5] to [0, 1]; unrated recipes are a
neutral 0.5. Its weight is small on purpose: Food.com ratings are heavily skewed (≈72 % are 5 stars), so they say
little beyond "not terrible". All weights live in `PreferenceWeights` so they can be tuned on **validation** scenarios.

## Public API

| Name | What |
| --- | --- |
| `score_recipes(catalog, profile, ignore_for_likes=(), weights=DEFAULT_WEIGHTS) -> float32[n]` | The score. Pass staples (salt, pepper) in `ignore_for_likes` so liking salt does not boost every recipe |
| `popularity(catalog, weights) -> float32[n]` | User-independent rating signal in [0, 1] |
| `disliked_mask(catalog, profile) -> bool[n]` | Recipes with a disliked ingredient or in a disliked cuisine (evaluation's "disliked-meal rate") |
| `PreferenceWeights`, `DEFAULT_WEIGHTS` | The formula's constants |

## Decisions

* **Cold-start first.** No collaborative filtering: the MVP user has no history and a hand-set content-based score is
  honest and explainable. The ratings in the dataset are used only as a weak prior.
* **Saturation** (two liked ingredients earn the whole bonus) stops a long likes list from dominating the objective.
* **Leakage-safe.** Only train-split ratings enter; the validation/test interactions are never used.

## Limits

* No learned taste model, no seasonality, no "had it last week" memory (variety is handled in the optimiser).
* Cuisine labels are sparse in Food.com; most recipes have none, so the cuisine term affects a minority of recipes.

## Tests

[`tests/preference/test_scorer.py`](../tests/preference/test_scorer.md)

## Change log

- 2026-10-12 — Created.
