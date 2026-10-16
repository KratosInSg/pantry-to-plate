# Data

## Sources

| Source | Used for | Type |
| --- | --- | --- |
| Food.com | Candidate recipes | Public |
| USDA FoodData Central | Nutrition per 100 g | Public (US government) |
| USDA FoodKeeper | Shelf-life estimates (min-max, with confidence) | Public (US government) |
| Synthetic pantry scenarios | Evaluation | Built in-house — a few hundred scenarios across 8 families, seeded generator, frozen validation/test split |
| Labelled pantry sentences | NLP evaluation | Built in-house — 200-500 labelled messages |
| MealRec (Li et al., 2022; Allrecipes.com reviews) | Real-taste preference evaluation: 100 users' dinner ratings (`data/evaluation/taste_v2/`, built by `src/evaluation/taste_users.py`) | Public research dataset, **no licence** (cite the paper); raw files and the derived user sets are git-ignored |

Food.com's licence and reuse terms are checked before the dataset is locked in; academic evaluation is fine, a commercial product would need licensed recipe content. The same applies to MealRec, which was scraped from Allrecipes and released for research (https://github.com/WUT-IDEA/MealRec): it holds only 4- and 5-star ratings (likes, no dislikes), its recipe ids are Allrecipes ids (bridged to ours through ingredients, cuisine tags and exact names), and its terms should be checked before the derived set is published.

## Canonical ingredient pipeline

The central challenge: "2 cups chopped baby spinach", "fresh spinach leaves" and "spinach" must all resolve to the same canonical ingredient before anything downstream can run.

1. Parse quantity, unit and modifier out of the raw text.
2. Map to a canonical ingredient via an alias dictionary, fuzzy matching and embedding similarity — each with a confidence score.
3. Hand-check low-confidence mappings for the most frequent ingredients.
4. Join nutrition (USDA FoodData Central) and shelf life (FoodKeeper) onto the canonical ingredient — never onto the raw text.
5. Recipes whose key ingredients can't be mapped are excluded, not guessed.

Two rules that don't bend:

- **Nutrition is computed, not guessed** — grams × the per-100g nutrient value, never LLM-estimated. Food.com's own per-recipe calories become a consistency check, not the source of truth (it can't reflect substitutions, scaling or partial pantry quantities).
- **Estimates stay labelled as estimates** — FoodKeeper shelf life shows its confidence level; known use-by dates are hard constraints, FoodKeeper ranges are soft and weighted by confidence.

## Synthetic scenarios

- A seeded generator builds each scenario (a user profile + starting pantry) from a documented config, across 8 families (including a "difficult/infeasible combinations" family).
- Pantry items are drawn from canonical ingredients weighted by how often they appear in Food.com recipes, with realistic quantities and FoodKeeper-sourced expiry dates.
- Split into validation and test sets; the test set is frozen before any weight tuning.

## Quality gates (before any modelling)

- Coverage — share of Food.com ingredients that map to a canonical ingredient.
- Consistency — Food.com's stated calories vs. the recomputed value, within tolerance.
- Grams conversion — every quantity resolves to grams before it's usable by the optimiser's waste/nutrition costs.

## As built (Oct 2026)

The curated dataset lives in `data/canonical/` and is rebuilt from the raw downloads with
`python src/knowledge/build/run_all.py`. Its README documents every table, column, caveat and quality-gate result.

Where the build departs from the plan above:

- **Recipe quantities are estimated, not parsed.** The Food.com corpus used here (Kaggle `shuyangli94`) has ingredient
  names only. Grams per serving are fitted per recipe from Food.com's stated nutrition and USDA per-100 g values, with
  per-ingredient priors and plausibility caps, and are labelled `grams_source = estimated`. The "Grams conversion" gate
  therefore reads: *every retained recipe ingredient has an estimated grams value, with held-out nutrient error reported*.
- **The calorie "consistency check" is fitted, not independent.** Computed kcal matches stated kcal by construction;
  the honest accuracy figures are the held-out nutrients (sat fat, sugars, sodium) in the dataset README.
- **Diet and allergy flags are derived from ingredients**, not from Food.com tags (`dairy-free` appears on 195 of 231K recipes).
- **Pool:** dinner-eligible recipes (main dish / one-dish meal / soup-stew) whose every ingredient maps to a USDA food
  and whose stated nutrition is reproducible from realistic ingredient amounts; the rest are excluded, not guessed.
