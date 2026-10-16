# `src/preference/` — how much would this user like each recipe?

## Purpose

Turn the user's stated likes and dislikes into one number per recipe in `[0, 1]`. The optimiser minimises
`1 − score`. It is **content-based** (cuisine, ingredients), so it works for a new user with no history and every score
is explainable ("matches your liking for Italian food").

## What it must never do

**Score, not filter.** Safety (allergy, diet) belongs to `optimizer.hard_rules`. A disliked ingredient lowers the score
but keeps the recipe eligible; use `UserProfile.excluded_ingredient_ids` for a true "never".

## Files

| File | Role | Doc |
| --- | --- | --- |
| `scorer.py` | `score_recipes`, `popularity`, `disliked_mask`, `PreferenceWeights` | [scorer.md](scorer.md) |
| `history.py` | Preferences from a rating history: lift-based likes into the existing profile fields, and graded scores (average-dish similarity; nearest liked dishes + tags, the best on real users). Evaluation only so far | [history.md](history.md) |

## Change log

- 2026-10-12 — Package created.
- 2026-10-16 — Added `history.py` (preferences learned from meal ratings, no trained model).
- 2026-10-16 — `history.py` gained `nearest_dish_scores` (nearest liked dishes, ingredients + tags).
