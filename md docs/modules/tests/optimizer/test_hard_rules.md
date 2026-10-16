# `tests/optimizer/test_hard_rules.py`

Tests [`optimizer/hard_rules.py`](../../optimizer/hard_rules.md) against the real recipe flags — so it also guards the
dataset build: a flag regression shows up here.

| Test | Pins |
| --- | --- |
| `test_default_profile_allows_everything` | no rules active, all feasible |
| `test_vegan_keeps_exactly_the_vegan_recipes` | feasible == `is_vegan` |
| `test_vegetarian_is_a_superset_of_vegan` | vegan ⊂ vegetarian, strictly more |
| `test_vegetarian_recipes_have_no_meat_fish_or_egg` | no feasible vegetarian recipe has meat, poultry, fish, shellfish or egg; dairy recipes remain |
| `test_pescatarian_has_no_meat_or_poultry` | and allows more than vegetarian |
| `test_allergen_recipes_are_never_feasible` | peanut / dairy / gluten / shellfish (parametrised) |
| `test_pork_and_alcohol_rules_are_opt_in` | off by default, effective when on |
| `test_excluded_ingredient_is_never_used` | via the inverted index |
| `test_time_cap` | every feasible recipe within the cap |
| `test_rules_combine_with_and` | diet + allergen + time = the intersection |
| `test_violated_rules_names_the_rule_and_explains_it` | rule names and a human reason for the explainer |
| `test_count_violations_counts_meal_rule_pairs` | the safety metric counts (meal, rule) pairs |

## Change log

- 2026-10-12 — Created.
- 2026-10-13 — Added `test_a_rejected_recipe_is_never_feasible_and_nothing_else_is_affected` (unknown ids ignored; exactly one recipe removed) and `test_dinner_only_removes_breakfast_dough_and_batter_dishes_and_is_off_by_default` (off by default so the benchmark is unaffected; heuristic removes a few percent, keeps crusted/glazed dinners).
- 2026-10-14 — Added `test_vegetarian_recipes_have_no_meat_fish_or_egg`.
- 2026-10-16 — Added `test_ingredient_violations_use_the_same_rule_names_as_recipes`.
