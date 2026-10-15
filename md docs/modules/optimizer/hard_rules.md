# `src/optimizer/hard_rules.py`

## Purpose

Decide which recipes are **allowed at all** for this user. Runs before scoring and before the solver. Everything it
removes is gone for good: no cost term can buy a violation back. This is the *constraint safety* metric of the
evaluation ("must be zero"), so the logic is small, explicit and explainable.

## Rules (a recipe must pass all of them)

| Rule name | Passes when |
| --- | --- |
| `diet:<d>` | omnivore: always · pescatarian: no meat, no poultry · vegetarian: `is_vegetarian` (no meat, poultry, fish, shellfish, gelatin or **egg**; dairy fine) · vegan: `is_vegan` |
| `allergen:<name>` | `contains_<name>` is False, for every allergen in the profile |
| `pork` | `avoid_pork` off, or no pork product |
| `alcohol` | `avoid_alcohol` off, or no alcohol |
| `excluded` | none of `excluded_ingredient_ids` is an ingredient |
| `excluded_recipe` | the recipe is not in `excluded_recipe_ids` (a dinner the user rejected; unknown ids are ignored) |
| `time` | `max_total_minutes` unset, or not longer |
| `not_dinner` | `dinner_only` off, or the recipe is not breakfast / brunch / dough / batter / icing-like (`RecipeCatalog.non_dinner_like`, a tag-and-name **heuristic**) |

**Not** hard rules here: known use-by dates (a scheduling constraint — enforced in the optimiser model and the
inventory replay) and the weekday cooking-time limit / dislikes (soft: costs, not filters).

## Public API

| Name | What |
| --- | --- |
| `feasible_mask(catalog, profile) -> bool[n]` | True = passes every rule |
| `violation_masks(catalog, profile) -> dict[rule, bool[n]]` | One "violates" mask per *active* rule |
| `violated_rules(catalog, profile, idx) -> list[Rule]` | Which rules recipe `idx` breaks, each with a human-readable reason (for the explainer) |
| `count_violations(catalog, profile, indices) -> int` | (meal, rule) violations in a plan — the safety metric |
| `Rule(name, reason)` | Named rule + why |

## Honesty about coverage

Flags come from conservative keyword rules over canonical ingredients (`data/canonical/README.md`). They do not know
about hidden allergens inside branded products, so "zero violations" is **relative to the knowledge base**. This is
stated in `md docs/evaluation.md` and must stay stated in any report.

## Why `not_dinner` is a rule and not a cleaner pool

Food.com's "main-dish" tag lets through things nobody plans as dinner ("Easy pasta dough", "Breakfast egg soup"; about
4–9 % of the pool depending on how strictly it is read). Dropping them in the data build would change the pool the
frozen benchmark was generated from. As an opt-in hard rule (`UserProfile.dinner_only`, off by default, on in the app)
the benchmark is untouched, and the explanation can say *how many* dinners were removed and why — a silent filter
would be the kind of rationalisation the project forbids. The heuristic is deliberately conservative: "crusted",
"glazed" and "pancakes" are not matched (crusted salmon is a dinner).

## Tests

[`tests/optimizer/test_hard_rules.py`](../tests/optimizer/test_hard_rules.md)

## Change log

- 2026-10-12 — Created.
- 2026-10-13 — Added `excluded_recipe` (rejected dinners, for re-planning) and the opt-in `not_dinner` rule.
- 2026-10-14 — Vegetarian now excludes eggs (through the rebuilt `is_vegetarian` flag; no code change to the rule itself).

- 2026-10-15 — `food_group:<group>` applies the existing recipe flags as hard exclusions with traceable reasons; no packaged-food safety guarantee.
