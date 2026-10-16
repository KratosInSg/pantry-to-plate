# 04 · Real-taste preferences: do preferences learned from past ratings predict what people choose next?

The planning benchmark's users are synthetic: their likes are drawn at random, so its preference metric only shows
that the planner *follows* likes. This check uses **real people's ratings** from **MealRec** (Li et al., 2022), a
research dataset built from Allrecipes.com reviews.

For each of 100 users:

- their **earliest 80 rated dinners** play the part of "dinners we suggested and they rated" (the preference input);
- their **later** rated dinners that exist in our recipe catalogue are held out (about 24 per test user and 28 per
  validation user);
- preferences built only from the earlier ratings must rank the later ones high.

No model is trained. The users were frozen and split 50 validation / 50 test before anything was tuned. The method
and its settings were chosen on validation users, then the **test users were run once**.

| | |
| --- | --- |
| Data | 100 MealRec users with ≥ 100 rated main dishes (seeded sample of 111) · 50 validation / 50 test |
| Protocol | The MealRec paper's own (Section 5.1.1): each held-out dinner ranked against **99 sampled never-rated recipes** (seeded, same for all methods). HR@K = in the top K of those 100. NDCG@K also rewards a higher place. AUC = full-ranking counterpart (0.5 = chance) |
| Chance level | HR@10 = 0.100 · NDCG@10 = 0.045 · HR@5 = 0.050 · AUC = 0.500 |
| Date / code | 2026-10-16 · `src/preference/history.py`, `src/evaluation/taste_users.py`, `src/evaluation/taste_eval.py` |
| Commands | `python src/evaluation/taste_eval.py --split validation` and, once, `--split test` |
| Rows | [`test_users.csv`](test_users.csv), [`validation_users.csv`](validation_users.csv), [`validation_users_with_integrated_scorer.csv`](validation_users_with_integrated_scorer.csv): one row per user × method |

## Methods (none is trained)

| Method | Scores our 54,000 recipes by |
| --- | --- |
| `popularity` | Today's scorer for a user who states nothing (Food.com rating prior only) |
| `derived_likes` | Liked ingredients / cuisines derived from the ratings, put into the existing scorer ("plug and play") |
| `history_similarity` | Ingredient similarity to the user's *average* liked dinner |
| **`nearest_dishes`** | Mean similarity to the user's **10 most similar** liked dinners, over ingredients and tags (dish type, protein, cuisine), mixed 50/50 |
| `scorer_with_history` | The integrated production scorer (`nearest_dishes` as its rating-history term, next to the popularity prior); validation only |

## Results: test users, single run (50 users, 1,175 held-out dinners)

| Method | HR@5 | NDCG@5 | HR@10 | NDCG@10 | AUC |
| --- | --- | --- | --- | --- | --- |
| Chance level | 0.050 | 0.030 | 0.100 | 0.045 | 0.500 |
| Popularity (today) | 0.055 | 0.032 | 0.119 | 0.052 | 0.518 |
| Likes in the profile | 0.074 | 0.047 | 0.140 | 0.069 | 0.549 |
| Average-dish similarity | 0.087 | 0.058 | 0.174 | 0.085 | 0.587 |
| **Nearest dishes + tags** | **0.107** | **0.062** | **0.202** | **0.092** | **0.622** |

Paired difference vs popularity (95 % bootstrap CI over users):

| Method | HR@10 | NDCG@10 | AUC | Users better on HR@10 |
| --- | --- | --- | --- | --- |
| Likes in the profile | +0.021 [−0.010, +0.056] | +0.016 [+0.001, +0.035] | +0.031 [+0.009, +0.053] | 40 % |
| Average-dish similarity | +0.055 [+0.020, +0.092] | +0.033 [+0.014, +0.052] | +0.070 [+0.039, +0.099] | 58 % |
| **Nearest dishes + tags** | **+0.083 [+0.040, +0.127]** | **+0.040 [+0.020, +0.061]** | **+0.105 [+0.075, +0.134]** | **64 %** |

`taste_eval` also prints an empirical `random` row (test: HR@10 0.083, AUC 0.499). It varies around the chance levels
above, which are the ones to quote.

## Results: validation users (where the method was chosen; 50 users, 1,424 held-out dinners)

| Method | HR@10 | NDCG@10 | AUC | Paired HR@10 vs popularity | Users better |
| --- | --- | --- | --- | --- | --- |
| Popularity (today) | 0.115 | 0.058 | 0.531 | — | — |
| Likes in the profile | 0.137 | 0.071 | 0.539 | +0.022 [−0.004, +0.046] | 48 % |
| Average-dish similarity | 0.204 | 0.089 | 0.598 | +0.089 [+0.054, +0.121] | 72 % |
| Nearest dishes + tags | 0.235 | 0.116 | 0.643 | +0.120 [+0.087, +0.157] | 76 % |
| **Integrated scorer** (`scorer_with_history`) | **0.240** | **0.123** | **0.643** | **+0.125 [+0.093, +0.159]** | **82 %** |

The integrated scorer is what the planner uses (the "Loved it" mark in the app feeds it). It was added after the
single test run, so it is reported on validation users only. Wiring the method in did not cost ranking quality.

## How to read it

- **Preferences learned from a person's past ratings pick the dinners they choose later at about twice the chance
  rate** (HR@10 0.20 vs 0.10), and beat today's popularity prior, with every CI clear of zero on the held-out test users.
- **Plugging likes into the existing profile fields gives only part of the gain** (AUC yes, HR@10 not significant).
  Keeping the whole history as nearest dishes with tags gives the largest gain.
- **The MealRec paper reports HR@10 0.42–0.69.** That is not a difference of metric: those models are trained on the
  same site's own interaction data and rank whole meals, while ours is content-only and cross-site (Allrecipes ratings,
  Food.com recipes) with no training. In an exploratory diagnostic on validation users (scratch scripts, not in the
  repository), simple same-site popularity reached HR@10 ≈ 0.45 and item-to-item collaborative filtering ≈ 0.46, while
  ingredient-only content stayed at ≈ 0.19 even inside MealRec. The limit is the missing behaviour data from our own
  users, which is the proposal's "collaborative filtering once multi-user data exists".

## Caveats

- **Offline and positive-only:** MealRec keeps only 4- and 5-star ratings, and "never rated" is not "disliked". This is
  a check on real ratings, not a study of people eating our plans.
- Held-out dinners are those whose names match a catalogue recipe exactly, which favours classic dishes.
- Sampled metrics flatter every method and can reorder them (Krichene & Rendle, KDD 2020), hence AUC alongside.
- **Data licence:** MealRec's repository (https://github.com/WUT-IDEA/MealRec) carries no licence and asks to be cited.
  The derived user sets are therefore **not** in this repository. Rebuild them from the official download with
  `python src/evaluation/taste_users.py`.

## Citation

Ming Li, Lin Li, Qing Xie, Jingling Yuan, Xiaohui Tao. *MealRec: A Meal Recommendation Dataset.* arXiv:2205.12133, 2022.
