# Pantry-to-Plate - canonical dataset

*Built 2026-10-14 by `src/knowledge/build/run_all.py`. Everything the application uses lives here; raw downloads under `data/` are inputs only and can be ignored or deleted after a build.*

## At a glance

- **54,179 dinner recipes** with per-serving ingredient grams and USDA-computed nutrition, 3,314 canonical ingredients (2,252 used by those recipes), 202,323 ratings from 20,350 users in frozen train/validation/test splits.
- Sources: Food.com recipes & interactions (Kaggle `shuyangli94`), USDA FoodData Central (2026-04-30 CSV; SR Legacy, Foundation, FNDDS), USDA FoodKeeper (v128). Branded USDA foods and review text are deliberately excluded.
- Size on disk: 23 MB in 27 files (zstd Parquet + small CSVs).

## Read this before using the data

1. **Ingredient quantities are estimated.** Food.com publishes ingredient *names* only. Grams per serving come from a bounded least-squares fit of each recipe's stated nutrition against USDA per-100 g values, with per-ingredient priors and plausibility caps (`grams_source = estimated`). Treat them as plausible amounts, not measurements.
   - Held-out check (nutrients *not* used in the fit): median absolute % error sat fat 12%, sugars 29%, sodium 36%.
   - `kcal_computed` matches `kcal_stated` *by construction* (it was fitted); use the held-out figures above for honest accuracy.
   - Only calorie-bearing ingredients are constrained by the data (`grams_basis = fitted`). Accents - fresh herbs, spices, garlic, citrus juice, condiments - carry too little nutrient signal, so their grams are calibrated defaults (`grams_basis = prior_default`): realistic, but identical across recipes.
2. **Nutrition is per Food.com serving** and Food.com does not publish the number of servings. One planned dinner = one serving.
3. **Missing USDA nutrient values are NaN**, and sums treat them as 0 (so micronutrients and fibre can be slightly low).
4. **Diet/allergen flags are conservative keyword rules** over canonical ingredients (a false alarm costs a recipe; a miss costs a user's safety). They do not see hidden allergens inside branded products. Food.com's own tags are *not* trusted for diet/allergy (e.g. `dairy-free` appears on only 195 of 231K recipes).
5. **Shelf life is an estimate** (FoodKeeper ranges with a confidence label), never a known use-by date.
6. **Licence:** Food.com's reuse terms were not verified in this build; treat the recipe corpus as academic-use only until confirmed.

## Folder layout and naming

```
data/canonical/
  recipes/        recipe, recipe_ingredient, recipe_step
  ingredients/    ingredient, ingredient_alias, ingredient_unit_weight
  nutrition/      ingredient_nutrition_per100g, usda_food_nutrient_per100g, usda_food_portion_weight
  shelf_life/     foodkeeper_product, foodkeeper_shelf_life, ingredient_shelf_life
  interactions/   interaction_train | validation | test
  reference/      small curated CSVs (inputs to the build, also used at run time)
  _meta/          quality_gates.json, build reports, review lists (not needed at run time)
  MANIFEST.json   file list with row counts and SHA-256
```

Conventions: `snake_case`; folder = domain, file = `<entity>[_<variant>]`; ids are `recipe_id` (Food.com), `ingredient_id` (project), `fdc_id` (USDA), `product_id` (FoodKeeper), `user_id` (Food.com). Units are in the column name (`_g`, `_mg`, `_kcal`, `_ug`, `_days`). `*_stated` = published by Food.com, `*_computed` = grams x USDA. `contains_*` / `is_*` are booleans. Parquet for tables, CSV only for small hand-editable references.

## Tables

### `recipes/recipe.parquet`  (54,179 rows x 48 cols)

One row per dinner-eligible Food.com recipe that passed every quality gate. Per-serving nutrition appears twice: `*_stated` (Food.com's own numbers) and `*_computed` (grams x USDA per 100 g).  Key: `recipe_id`.

| column | type | meaning |
| --- | --- | --- |
| `recipe_id` | int64 | Food.com recipe id (stable across the dataset) |
| `name` | string | recipe title (whitespace-normalised) |
| `minutes_total` | int32 | total time in minutes (valid 5-1440) |
| `n_steps` | int32 | number of instruction steps |
| `n_ingredients` | int32 | number of food ingredients after canonicalisation (equipment such as skewers removed) |
| `cuisine` | string | primary cuisine tag, most specific first (null when untagged) |
| `tags` | list<string> | curated subset of Food.com tags |
| `is_vegetarian` | bool | derived from ingredients (not the Food.com tag); no meat/poultry/fish/shellfish/gelatin/egg |
| `is_vegan` | bool | vegetarian and no dairy/egg/honey |
| `contains_dairy` | bool | any ingredient flagged dairy |
| `contains_egg` | bool | any ingredient flagged egg |
| `contains_gluten` | bool | any ingredient flagged gluten (wheat, barley, rye ...) |
| `contains_peanut` | bool | peanut |
| `contains_tree_nut` | bool | tree nut (coconut excluded) |
| `contains_soy` | bool | soy |
| `contains_sesame` | bool | sesame |
| `contains_fish` | bool | fish incl. fish sauce / anchovy / Worcestershire |
| `contains_shellfish` | bool | crustacean or mollusc |
| `contains_meat` | bool | mammal meat incl. bacon/sausage |
| `contains_poultry` | bool | poultry incl. chicken broth |
| `contains_pork` | bool | pork products (halal/kosher use) |
| `contains_alcohol` | bool | wine/beer/spirits/liqueur |
| `kcal_stated` | float | Food.com stated kcal per serving |
| `protein_g_stated` | float | protein_g per serving as stated by Food.com (converted from %DV) |
| `fat_g_stated` | float | fat_g per serving as stated by Food.com (converted from %DV) |
| `sat_fat_g_stated` | float | sat_fat_g per serving as stated by Food.com (converted from %DV) |
| `carbohydrate_g_stated` | float | carbohydrate_g per serving as stated by Food.com (converted from %DV) |
| `sugars_g_stated` | float | sugars_g per serving as stated by Food.com (converted from %DV) |
| `sodium_mg_stated` | float | sodium_mg per serving as stated by Food.com (converted from %DV) |
| `rating_mean_train` | float | mean rating over rated train interactions (leakage-safe) |
| `n_ratings_train` | int32 | count of those ratings |
| `kcal_computed` | float | kcal per serving = sum(grams x USDA kcal per g) |
| `protein_g_computed` | float | protein_g per serving computed from estimated grams x USDA per 100 g |
| `fat_g_computed` | float | fat_g per serving computed from estimated grams x USDA per 100 g |
| `sat_fat_g_computed` | float | sat_fat_g per serving computed from estimated grams x USDA per 100 g |
| `carbohydrate_g_computed` | float | carbohydrate_g per serving computed from estimated grams x USDA per 100 g |
| `sugars_g_computed` | float | sugars_g per serving computed from estimated grams x USDA per 100 g |
| `fiber_g_computed` | float | fiber_g per serving computed from estimated grams x USDA per 100 g |
| `sodium_mg_computed` | float | sodium_mg per serving computed from estimated grams x USDA per 100 g |
| `cholesterol_mg_computed` | float | cholesterol_mg per serving computed from estimated grams x USDA per 100 g |
| `calcium_mg_computed` | float | calcium_mg per serving computed from estimated grams x USDA per 100 g |
| `iron_mg_computed` | float | iron_mg per serving computed from estimated grams x USDA per 100 g |
| `potassium_mg_computed` | float | potassium_mg per serving computed from estimated grams x USDA per 100 g |
| `vitamin_c_mg_computed` | float | vitamin_c_mg per serving computed from estimated grams x USDA per 100 g |
| `vitamin_a_rae_ug_computed` | float | vitamin_a_rae_ug per serving computed from estimated grams x USDA per 100 g |
| `water_g_computed` | float | water_g per serving computed from estimated grams x USDA per 100 g |
| `total_grams_per_serving` | float | sum of estimated ingredient grams per serving (includes water) |
| `fit_kcal_rel_error` | float | abs(computed - stated) / stated kcal after the grams fit (quality gate <= 0.15) |

### `recipes/recipe_ingredient.parquet`  (573,725 rows x 8 cols)

Recipe -> canonical ingredient with **estimated** grams per serving. `raw_text` keeps the original Food.com string.  Key: `recipe_id + ingredient_id`.

| column | type | meaning |
| --- | --- | --- |
| `recipe_id` | int64 | Food.com recipe id (stable across the dataset) |
| `position` | int16 | order in the original ingredient list |
| `ingredient_id` | int32 | canonical ingredient id (project-assigned, stable per build) |
| `raw_text` | string | original Food.com ingredient string |
| `grams_per_serving` | float | estimated grams of this ingredient per serving |
| `grams_source` | string | `estimated` = fitted from Food.com nutrition + USDA per 100 g + priors; `parsed` reserved for measured quantities |
| `kcal_share` | float | this ingredient's share of the recipe's computed kcal (0-1) |
| `grams_basis` | string | `fitted` = ingredient carries >=5% of the recipe's kcal so the stated nutrition constrains it; `prior_default` = accent ingredient (herb, spice, aromatic) whose grams are a calibrated default |

### `recipes/recipe_step.parquet`  (54,179 rows x 2 cols)

Instruction steps (list of strings) - display only, never used for decisions.  Key: `recipe_id`.

| column | type | meaning |
| --- | --- | --- |
| `recipe_id` | int64 | Food.com recipe id (stable across the dataset) |
| `steps` | list<string> | list of instruction strings |

### `interactions/interaction_train.parquet`  (197,297 rows x 5 cols)

Food.com ratings restricted to retained recipes; Food.com's own train split (frozen - do not re-split).  Key: `user_id + recipe_id + date`.

| column | type | meaning |
| --- | --- | --- |
| `user_id` | int64 | Food.com user id |
| `recipe_id` | int64 | Food.com recipe id (stable across the dataset) |
| `date` | timestamp[us] | interaction date |
| `rating` | int8 | 1-5 stars; 0 = no rating |
| `is_rated` | bool | rating > 0 |

### `interactions/interaction_validation.parquet`  (1,809 rows x 5 cols)

Validation split (frozen).  Key: `user_id + recipe_id + date`.

| column | type | meaning |
| --- | --- | --- |
| `user_id` | int64 | Food.com user id |
| `recipe_id` | int64 | Food.com recipe id (stable across the dataset) |
| `date` | timestamp[us] | interaction date |
| `rating` | int8 | 1-5 stars; 0 = no rating |
| `is_rated` | bool | rating > 0 |

### `interactions/interaction_test.parquet`  (3,217 rows x 5 cols)

Test split (frozen). Never tune on it.  Key: `user_id + recipe_id + date`.

| column | type | meaning |
| --- | --- | --- |
| `user_id` | int64 | Food.com user id |
| `recipe_id` | int64 | Food.com recipe id (stable across the dataset) |
| `date` | timestamp[us] | interaction date |
| `rating` | int8 | 1-5 stars; 0 = no rating |
| `is_rated` | bool | rating > 0 |

### `ingredients/ingredient.parquet`  (3,314 rows x 30 cols)

The canonical ingredient master: USDA match, food group, allergen/diet flags, frequency counts.  Key: `ingredient_id`.

| column | type | meaning |
| --- | --- | --- |
| `ingredient_id` | int32 | canonical ingredient id (project-assigned, stable per build) |
| `canonical_name` | string | canonical ingredient name (lowercase) |
| `food_group` | string | coarse group: dairy, meat, vegetable, herb_spice ... |
| `fdc_id` | int64 | USDA FoodData Central id |
| `usda_description` | string | USDA food description matched |
| `usda_data_type` | string | sr_legacy | foundation | survey_fndds |
| `match_method` | string | curated | auto | none (shelf life: + category_fallback) |
| `match_score` | float | lexical match score (auto only) |
| `match_confidence` | float | 1.0 curated; 0.85/0.75/0.55 auto tiers |
| `n_occurrences_foodcom` | int64 | mentions across all 231,637 Food.com recipes |
| `n_recipes_foodcom` | int64 | recipes mentioning it (Food.com) |
| `is_assumed_available` | bool | water / salt / black pepper: assumed in every kitchen (configurable) |
| `contains_dairy` | bool | any ingredient flagged dairy |
| `contains_egg` | bool | any ingredient flagged egg |
| `contains_gluten` | bool | any ingredient flagged gluten (wheat, barley, rye ...) |
| `contains_peanut` | bool | peanut |
| `contains_tree_nut` | bool | tree nut (coconut excluded) |
| `contains_soy` | bool | soy |
| `contains_sesame` | bool | sesame |
| `contains_fish` | bool | fish incl. fish sauce / anchovy / Worcestershire |
| `contains_shellfish` | bool | crustacean or mollusc |
| `contains_meat` | bool | mammal meat incl. bacon/sausage |
| `contains_poultry` | bool | poultry incl. chicken broth |
| `contains_pork` | bool | pork products (halal/kosher use) |
| `contains_alcohol` | bool | wine/beer/spirits/liqueur |
| `contains_honey` | bool | honey |
| `contains_gelatin` | bool | gelatin / marshmallow |
| `is_vegetarian` | bool | derived from ingredients (not the Food.com tag); no meat/poultry/fish/shellfish/gelatin/egg |
| `is_vegan` | bool | vegetarian and no dairy/egg/honey |
| `n_recipes_pool` | int32 | recipes in this dataset using it |

### `ingredients/ingredient_alias.parquet`  (12,409 rows x 5 cols)

Every spelling seen -> ingredient_id. This is what the NLP layer looks names up in.  Key: `alias + ingredient_id`.

| column | type | meaning |
| --- | --- | --- |
| `alias` | string | normalised spelling |
| `ingredient_id` | int32 | canonical ingredient id (project-assigned, stable per build) |
| `alias_source` | string | foodcom_raw | foodcom_canonical | synonym | canonical |
| `n_occurrences` | int64 | times seen in Food.com |
| `is_split` | bool | alias expands to more than one ingredient |

### `ingredients/ingredient_unit_weight.parquet`  (12,223 rows x 6 cols)

Grams per cup / tbsp / tsp / each / slice ... for converting pantry text to grams.  Key: `ingredient_id + unit + size`.

| column | type | meaning |
| --- | --- | --- |
| `ingredient_id` | int64 | canonical ingredient id (project-assigned, stable per build) |
| `unit` | string | cup | tbsp | tsp | fl_oz | each | slice | clove | can ... |
| `size` | string | small | medium | large ... (for unit=each) |
| `grams_per_unit` | float | grams in one unit |
| `prep_basis` | string | preparation the weight refers to (e.g. chopped) |
| `source` | string | usda_portion | derived_volume | group_median (or provenance string for nutrition) |

### `nutrition/ingredient_nutrition_per100g.parquet`  (3,314 rows x 21 cols)

USDA nutrients per 100 g for each canonical ingredient.  Key: `ingredient_id`.

| column | type | meaning |
| --- | --- | --- |
| `ingredient_id` | int32 | canonical ingredient id (project-assigned, stable per build) |
| `fdc_id` | int64 | USDA FoodData Central id |
| `match_confidence` | double | 1.0 curated; 0.85/0.75/0.55 auto tiers |
| `energy_kcal` | float | kcal per 100 g |
| `protein_g` | float | g per 100 g |
| `fat_g` | float | g per 100 g |
| `sat_fat_g` | float | g per 100 g |
| `carbohydrate_g` | float | g per 100 g |
| `sugars_g` | float | g per 100 g (total sugars) |
| `fiber_g` | float | g per 100 g |
| `sodium_mg` | float | mg per 100 g |
| `cholesterol_mg` | float | mg per 100 g |
| `calcium_mg` | float | mg per 100 g |
| `iron_mg` | float | mg per 100 g |
| `potassium_mg` | float | mg per 100 g |
| `vitamin_c_mg` | float | mg per 100 g |
| `vitamin_a_rae_ug` | float | ug RAE per 100 g |
| `water_g` | float | g per 100 g |
| `energy_source` | string | usda_energy | usda_atwater_general | computed_atwater_* |
| `basis` | string | per_100g (nutrition) / date_of_purchase | package_date | after_opening | after_thawing (shelf life) |
| `source` | string | usda_portion | derived_volume | group_median (or provenance string for nutrition) |

### `nutrition/usda_food_nutrient_per100g.parquet`  (13,694 rows x 21 cols)

All 13,694 non-branded USDA foods (SR Legacy, Foundation, FNDDS) with the planner's 15 nutrients - the pool a pantry item can be re-mapped from.  Key: `fdc_id`.

| column | type | meaning |
| --- | --- | --- |
| `fdc_id` | int64 | USDA FoodData Central id |
| `data_type` | string | sr_legacy | foundation | survey_fndds |
| `description` | string |  |
| `category` | string | USDA food category |
| `energy_kcal` | float | kcal per 100 g |
| `protein_g` | float | g per 100 g |
| `fat_g` | float | g per 100 g |
| `sat_fat_g` | float | g per 100 g |
| `carbohydrate_g` | float | g per 100 g |
| `sugars_g` | float | g per 100 g (total sugars) |
| `fiber_g` | float | g per 100 g |
| `sodium_mg` | float | mg per 100 g |
| `cholesterol_mg` | float | mg per 100 g |
| `calcium_mg` | float | mg per 100 g |
| `iron_mg` | float | mg per 100 g |
| `potassium_mg` | float | mg per 100 g |
| `vitamin_c_mg` | float | mg per 100 g |
| `vitamin_a_rae_ug` | float | ug RAE per 100 g |
| `water_g` | float | g per 100 g |
| `energy_source` | string | usda_energy | usda_atwater_general | computed_atwater_* |
| `qc_flag` | string | ok | no_energy | energy_out_of_range |

### `nutrition/usda_food_portion_weight.parquet`  (21,249 rows x 9 cols)

Cleaned household-unit weights for those USDA foods.  Key: `fdc_id + unit + size + prep`.

| column | type | meaning |
| --- | --- | --- |
| `fdc_id` | int64 | USDA FoodData Central id |
| `seq_num` | int64 | USDA portion sequence (1 = primary) |
| `unit` | string | cup | tbsp | tsp | fl_oz | each | slice | clove | can ... |
| `size` | string | small | medium | large ... (for unit=each) |
| `prep` | string |  |
| `amount` | float | quantity the label refers to |
| `gram_weight` | float | grams for `amount` |
| `grams_per_unit` | float | grams in one unit |
| `label_raw` | string | original USDA portion text |

### `shelf_life/foodkeeper_product.parquet`  (661 rows x 6 cols)

USDA FoodKeeper product catalogue (data version 128).  Key: `product_id`.

| column | type | meaning |
| --- | --- | --- |
| `product_id` | int64 | FoodKeeper product id |
| `name` | string | recipe title (whitespace-normalised) |
| `subtitle` | string | FoodKeeper name subtitle |
| `category` | string | USDA food category |
| `subcategory` | string |  |
| `keywords` | string | FoodKeeper keywords |

### `shelf_life/foodkeeper_shelf_life.parquet`  (1,341 rows x 15 cols)

FoodKeeper storage guidance flattened to days: product x storage x state x basis.  Key: `product_id + storage + state + basis`.

| column | type | meaning |
| --- | --- | --- |
| `product_id` | int64 | FoodKeeper product id |
| `storage` | string | pantry | refrigerator | freezer |
| `state` | string | unopened | opened | thawed |
| `basis` | string | per_100g (nutrition) / date_of_purchase | package_date | after_opening | after_thawing (shelf life) |
| `min_days` | float | FoodKeeper minimum shelf life in days (null if not numeric) |
| `max_days` | float | FoodKeeper maximum, days |
| `is_indefinite` | bool | FoodKeeper says indefinitely |
| `is_when_ripe` | bool | ripening-dependent |
| `is_not_recommended` | bool | storage method not recommended |
| `is_package_date_only` | bool | follow the package date |
| `metric_raw` | string | unit text in the source |
| `tips` | string | FoodKeeper storage tip |
| `min_days_effective` | float | numeric usable minimum (see effective_source) |
| `max_days_effective` | float | numeric usable maximum |
| `effective_source` | string | foodkeeper | foodkeeper_tip | indefinite_cap (3650 d) | category_median | not_recommended |

### `shelf_life/ingredient_shelf_life.parquet`  (13,719 rows x 19 cols)

FoodKeeper joined to canonical ingredients with a confidence label and one `is_default` row per ingredient. **Estimates, never known use-by dates.**  Key: `ingredient_id + storage + state + basis`.

| column | type | meaning |
| --- | --- | --- |
| `ingredient_id` | int32 | canonical ingredient id (project-assigned, stable per build) |
| `foodkeeper_product_id` | int64 | linked FoodKeeper product |
| `match_method` | string | curated | auto | none (shelf life: + category_fallback) |
| `match_score` | float | lexical match score (auto only) |
| `confidence` | string | high (curated product) | medium (lexical) | low (category fallback) |
| `storage` | string | pantry | refrigerator | freezer |
| `state` | string | unopened | opened | thawed |
| `basis` | string | per_100g (nutrition) / date_of_purchase | package_date | after_opening | after_thawing (shelf life) |
| `min_days` | float | FoodKeeper minimum shelf life in days (null if not numeric) |
| `max_days` | float | FoodKeeper maximum, days |
| `min_days_effective` | float | numeric usable minimum (see effective_source) |
| `max_days_effective` | float | numeric usable maximum |
| `effective_source` | string | foodkeeper | foodkeeper_tip | indefinite_cap (3650 d) | category_median | not_recommended |
| `is_indefinite` | bool | FoodKeeper says indefinitely |
| `is_when_ripe` | bool | ripening-dependent |
| `is_package_date_only` | bool | follow the package date |
| `is_not_recommended` | bool | storage method not recommended |
| `tips` | string | FoodKeeper storage tip |
| `is_default` | bool | row the planner uses by default |

### `reference/ingredient_synonyms.csv`  (661 rows x 3 cols)

Curated: spelling/synonym -> canonical name (a `+` means split into two ingredients).  Key: `name`.

| column | type | meaning |
| --- | --- | --- |
| `name` | text/number | recipe title (whitespace-normalised) |
| `canonical_name` | text/number | canonical ingredient name (lowercase) |
| `note` | text/number |  |

### `reference/ingredient_usda_overrides.csv`  (385 rows x 3 cols)

Curated: canonical ingredient -> exact USDA description.  Key: `canonical_name`.

| column | type | meaning |
| --- | --- | --- |
| `canonical_name` | text/number | canonical ingredient name (lowercase) |
| `usda_description` | text/number | USDA food description matched |
| `note` | text/number |  |

### `reference/ingredient_foodkeeper_overrides.csv`  (339 rows x 3 cols)

Curated: canonical ingredient -> FoodKeeper product id.  Key: `canonical_name`.

| column | type | meaning |
| --- | --- | --- |
| `canonical_name` | text/number | canonical ingredient name (lowercase) |
| `foodkeeper_product_id` | text/number | linked FoodKeeper product |
| `note` | text/number |  |

### `reference/unit_conversion.csv`  (16 rows x 6 cols)

Physical unit constants (mass in g, volume in ml).  Key: `unit`.

| column | type | meaning |
| --- | --- | --- |
| `unit` | text/number | cup | tbsp | tsp | fl_oz | each | slice | clove | can ... |
| `aliases` | text/number |  |
| `kind` | text/number |  |
| `to_base` | text/number |  |
| `base_unit` | text/number |  |
| `note` | text/number |  |

### `reference/nutrient_daily_value.csv`  (6 rows x 5 cols)

Daily values behind Food.com's %DV columns (calibrated).  Key: `nutrient_column`.

| column | type | meaning |
| --- | --- | --- |
| `nutrient_column` | text/number |  |
| `daily_value` | text/number |  |
| `unit` | text/number | cup | tbsp | tsp | fl_oz | each | slice | clove | can ... |
| `used_for` | text/number |  |
| `source_note` | text/number |  |

### `reference/nutrition_reference_ranges.csv`  (20 rows x 7 cols)

Published planning ranges (FDA DV, Dietary Guidelines AMDR) with sources.  Key: `nutrient + basis`.

| column | type | meaning |
| --- | --- | --- |
| `nutrient` | text/number |  |
| `basis` | text/number | per_100g (nutrition) / date_of_purchase | package_date | after_opening | after_thawing (shelf life) |
| `min` | text/number |  |
| `max` | text/number |  |
| `unit` | text/number | cup | tbsp | tsp | fl_oz | each | slice | clove | can ... |
| `source` | text/number | usda_portion | derived_volume | group_median (or provenance string for nutrition) |
| `note` | text/number |  |

## Quality gates (from docs/data.md)

| gate | result |
| --- | --- |
| Ingredient mapping coverage (Food.com mentions mapped to USDA) | 96.8% of 14,942 distinct raw strings' occurrences; 86.7% via curated matches |
| Recipes kept only if every ingredient mapped | 100% of the 54,179 retained recipes |
| Quantity -> grams | 100% estimated (573,725 rows), 0% parsed - see caveat 1 |
| Nutrition field coverage (pool ingredients) | energy_kcal 100%, protein_g 100%, fat_g 100%, carbohydrate_g 100%, fiber_g 93%, sodium_mg 99% |
| Shelf-life coverage (pool ingredients with a default row) | 99.9% ; by usage: high 93.2%, medium 2.1%, low 4.7% |
| Nutrition consistency (computed vs stated, median abs error) | kcal 7.72, protein 0.97 g, fat 0.78 g, carbs 1.29 g (fitted targets) |
| Held-out nutrition error (median APE, not fitted) | sat_fat_g 12%, sugars_g 29%, sodium_mg 36% |

### Pool composition

Vegetarian 6,990 | vegan 2,654 | pescatarian-compatible 14,584 | gluten-free 23,177 | dairy-free 22,112 | nut-free 51,139. Cooking time p10/p50/p90 = 20/45/155 min; kcal per serving p10/p50/p90 = 189/391/740.

## Rebuild

```bash
python src/knowledge/build/run_all.py      # raw downloads -> data/canonical  (~6 min)
```

To improve ingredient matching, edit the three curated CSVs in `reference/` (a synonym, a forced USDA description, a FoodKeeper product id) and re-run. `_meta/review_unmapped_or_low_confidence.csv` lists the most frequent names still worth reviewing.

## Load

```python
import pandas as pd
recipe = pd.read_parquet('data/canonical/recipes/recipe.parquet')
lines  = pd.read_parquet('data/canonical/recipes/recipe_ingredient.parquet')
ing    = pd.read_parquet('data/canonical/ingredients/ingredient.parquet')
```
