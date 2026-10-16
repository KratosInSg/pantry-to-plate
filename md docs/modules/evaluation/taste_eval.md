# `src/evaluation/taste_eval.py`

## Purpose

The real-taste preference check: does a real person's rating history, turned into preferences, predict the dinners
they went on to enjoy? For each frozen real-taste user (`evaluation/taste_users.py`), it builds preferences from their
earliest 80 rated dinners, scores the whole catalogue, and looks up their later liked dinners in that ranking.

## Methods compared

| Method | Scores the catalogue with |
| --- | --- |
| `random` | Seeded random numbers: the chance level every other row is read against |
| `popularity` | Today's scorer for a user who states nothing (only the Food.com rating prior) |
| `derived_likes` | Today's scorer, unchanged, with likes from `preference.history.derive_likes` (the plug-and-play route) |
| `history_similarity` | `preference.history.history_similarity` (average liked dish, ingredients) |
| `nearest_dishes` | `preference.history.nearest_dish_scores` (nearest liked dishes, ingredients + tags) |
| `scorer_with_history` | The production path: `score_recipes` with the history in `UserProfile.rated_dinners`. Added after the single test run, so reported on **validation users only** (HR@10 0.240, AUC 0.643) |

## Metrics

* **HR@K and NDCG@K (K = 5, 10)** use the MealRec paper's protocol (Li et al. 2022, Section 5.1.1). Each held-out
  dinner is ranked against `N_NEGATIVES` = 99 recipes the user never rated, sampled with a fixed seed and shared by all
  methods for that user.
  - HR@K: the dinner is in the top K. NDCG@K: 1 / log2(rank + 1) within the top K.
  - Chance levels: HR@10 = 0.10, NDCG@10 = 0.045, HR@5 = 0.05.
  - Ties are broken at random (seeded), so an uninformative score gets chance in expectation.
  - With several held-out dinners per user, metrics are averaged per user, then over users.
* **AUC** (full ranking): probability that a held-out dinner outranks a random never-rated catalogue recipe. Ties count
  half, the user's history recipes are excluded from the negatives, and 0.5 = chance. It is reported next to the
  sampled metrics because those can flatter every method and even reorder them (Krichene & Rendle, KDD 2020).
* **recall@1 %**: share of held-out dinners in the top 1 % of the full ranking.
* `compare` gives the paired difference against `popularity` for HR@10, NDCG@10 and AUC with a 95 % bootstrap CI
  (`evaluation.metrics.paired_bootstrap`, users resampled), plus the share of users with a higher HR@10.

## Usage

```bash
python src/evaluation/taste_eval.py --split validation --save data/evaluation/taste_v2/runs/<name>.csv
python src/evaluation/taste_eval.py --split test            # once, after the method and its settings are fixed
```

## Public API

| Name | What |
| --- | --- |
| `rank_metrics(scores, positives, exclude=(), top_share=0.01) -> (auc, recall)` | Raises `ValueError` with no positives or no negatives |
| `sample_negatives(n_rows, positives, exclude, rng, n_negatives=99) -> {positive: rows}` | Raises `ValueError` if too few candidates |
| `sampled_metrics(scores, negatives, rng, ks=(5, 10)) -> {"hr_5", "ndcg_5", "hr_10", "ndcg_10"}` | The paper protocol for one user |
| `evaluate_user(user, recipes, rates, ctx, config, nearest, methods)` | One row per method |
| `run_taste_eval(split, eval_dir, ctx, config, nearest, limit, methods) -> DataFrame` | One row per (user, method): `METRICS` + `n_heldout`, `n_liked_ingredients`, `n_liked_cuisines` |
| `summary(df)`, `compare(df, baseline="popularity")`, `report(df)` | Mean table (with HR@10 × the empirical random row), paired table, printout |
| `rated_dishes_of_pool(recipes)` | Every MealRec main dish as the reference pool for base rates |
| `METHODS`, `METRICS`, `N_NEGATIVES`, `KS`, `SEED`, `TOP_SHARE`, `BASELINE` | Constants |

## Results

The test users were run once (2026-10-16). `nearest_dishes` scored HR@10 0.202 (chance 0.10) and AUC 0.622, ahead of
popularity with every CI clear of zero. Tables are in `md docs/evaluation.md` → "Real-taste preference check".

## Caveats

* Unrated is not disliked: the negatives are only "never rated by this user".
* Held-out positives are dinners whose names match the catalogue exactly, so classic dishes are over-represented.
* The empirical `random` row varies around the theoretical chance level (test: HR@10 0.083). Quote chance as 0.10 in
  reports.

## Tests

[`tests/evaluation/test_taste_eval.py`](../tests/evaluation/test_taste_eval.md)

## Logging

Logger `evaluation.taste_eval`. INFO: one line per run (users, rows).

## Change log

- 2026-10-16 — Created. Validation results recorded in `md docs/evaluation.md`.
- 2026-10-16 — Added the MealRec-paper protocol (HR@5/10, NDCG@5/10 against 99 sampled negatives), the `random` and
  `nearest_dishes` methods, `summary`, and a `methods` argument. Default set is now `taste_v2`. Test users run once.
- 2026-10-16 — `scorer_with_history` method (the integrated scorer). Validation only; the test users were not re-run.
