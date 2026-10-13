# Architecture

Five stages, left to right: input, understand, enrich, decide, output. The only design rule that matters: **rules and the optimiser decide the plan; the LLM only parses input and writes explanations.**

```
[Input] -> [Understand] -> [Enrich] -> [Decide] -> [Output]
```

## 1. Input

- User profile: diet, allergies, tastes, nutrition targets.
- Free-text pantry list (e.g. "half a cabbage, paneer, four eggs, spinach going bad").
- Owner: `src/nlp/` (intake).

## 2. Understand

- Parses quantity, unit and modifiers out of the free text.
- Maps every item to a canonical ingredient (handles "2 cups chopped baby spinach", "fresh spinach leaves", "spinach" → the same canonical ingredient).
- Flags urgency cues ("going bad", "half a cabbage" → 0.5 × a typical unit weight).
- Owner: `src/nlp/`.

## 3. Enrich

- Joins each canonical ingredient to:
  - Nutrition per 100 g — USDA FoodData Central.
  - Shelf-life estimate (with confidence) — USDA FoodKeeper.
  - Candidate recipes — Food.com.
- Nutrition is always computed from grams × the per-100g value — never estimated by the LLM.
- Owner: `src/knowledge/`. See [data.md](data.md) for the join and confidence scoring.

## 4. Decide

- **Hard-rule filter** — removes anything unsafe: allergy conflicts, diet conflicts, known use-by dates. Never relaxed.
- **Preference scorer** — content-based: similarity between the recipe (ingredients, cuisine, nutrition, cooking time) and the user's stated likes/dislikes, minus a penalty for disliked ingredients.
- **Weekly optimiser** — a mixed-integer linear model solved with HiGHS (SciPy). Picks the 7-day combination of meals that minimises a weighted sum of: waste, extra groceries, nutrition deviation, and preference/repetition/cook-time penalties, subject to the hard rules.
- Owner: `src/preference/`, `src/optimizer/`.

## 5. Output

- Seven dinners, a grocery box (whatever the plan needs that isn't already in the pantry), and a plain-English reason per meal.
- The explainer reads the solver's own cost terms and the rules that fired — it never invents a reason the solver didn't produce.
- Owner: `src/explain/`.

## Out of scope (MVP)

- More than one user, more than one week, breakfast/lunch planning.
- Medical or diagnostic nutrition advice — targets are planning support against reference ranges the user selects, not medical guidance.
- Hidden allergens in packaged/branded products (e.g. wheat in soy sauce) — the allergen table covers canonical ingredients, not branded products, until Open Food Facts is added.

## Stack

Python; the optimiser's model is solver-agnostic and has two backends — HiGHS (via SciPy, default) and OR-Tools CP-SAT (run in a child process, because it cannot share a process with pyarrow on the Windows/conda dev machine). See [CLAUDE.md](../CLAUDE.md) for repo conventions.
