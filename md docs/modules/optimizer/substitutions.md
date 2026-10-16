# `src/optimizer/substitutions.py`

## Purpose

Ingredient substitution rules: the slide's rule *"IF buttermilk unavailable AND milk + lemon available → allow
substitution"* and the explanation type *"Buttermilk replaced with milk + lemon using available ingredients"*. For each
thing a plan would buy, it checks whether a known swap can be made entirely from spare pantry stock. If so, the item
comes off the grocery list, the substitutes are used instead, and the fired rule is recorded so the explainer can cite it.

## Where it sits

After the weekly optimiser has chosen the dinners and the inventory replay (`optimizer/inventory.py`) has worked out
what each dinner takes from the pantry and what it buys. `replay_with_substitutions` is the one call that the
explainer (`explain/facts.py`), the app (`app/service.py`: ingredient lines and grocery box) and re-planning
(`optimizer/replan.py`) all use, so they always agree on which swaps were made.

## Public API

| Name | What |
| --- | --- |
| `SubstitutionRule` | A rule as a kitchen chart writes it: `key`, `replaces`, `amount`, `unit`, `uses` (name, amount, unit), `note` |
| `SUBSTITUTION_RULES` | The rule table (15 rules; per replaced food, the first that fits wins) |
| `resolve_rules(store, rules) -> tuple[ResolvedRule, ...]` | Converts to grams of each substitute per gram replaced, using the dataset's unit weights. Raises `ValueError` for an unknown ingredient or a unit with no weight |
| `default_rules(store)` | `SUBSTITUTION_RULES` resolved, cached per store |
| `allowed_substitutes(store, profile, rules) -> frozenset[int]` | Substitutes this user may be given: passes every hard rule (`hard_rules.ingredient_violations`) and is not disliked |
| `apply_substitutions(report, last_use_day, rules, allowed_ids, ignore_ids) -> SubstitutedInventory` | Fires every rule that fits on a replay (the input is not modified) |
| `replay_with_substitutions(recipe_indices, scenario, ctx, last_use_day, horizon_days=None, rules=None)` | `account_inventory` + `apply_substitutions` for the scenario's user |
| `SubstitutedInventory` | `report` (the updated `InventoryReport`), `substitutions`, `on_day(day)` |
| `Substitution` | `day`, `rule_key`, `replaced_id`, `replaced_g`, `uses` ((ingredient id, grams); 0 g for an assumed staple), `note` |
| `MIN_SUBSTITUTION_G` | 1 g: a smaller need is a pinch and is never swapped |

## When a rule fires (all must hold)

1. The dinner on that day **buys** the replaced food. Pantry stock of the food itself is used first, as usual, so only
   the shortfall is swapped.
2. **Every** substitute is *spare*, meaning still left at the end of the replayed plan. The replay serves days in
   order and stock only goes down, so stock left at the end was never needed by a later dinner. Taking it therefore
   cannot starve another dinner (tested).
3. Every substitute is still usable that day (`day <= last_use_day`).
4. Every substitute passes the user's hard rules (diet, allergens, excluded food groups, pork, alcohol, "never"
   foods) and is not disliked. A vegan's margarine is never swapped for butter, and a dairy allergy blocks milk.
5. The **whole** shortfall is covered. A partial swap would still mean buying the food, so it saves no grocery item.

Staples assumed in every kitchen are available without being accounted, exactly as in the replay. Two dinners
compete for the same spare stock in day order.

## Where the numbers come from

Each rule is written as common household substitution charts (cookbooks, university-extension handouts) state it,
in kitchen units, e.g. 1 cup buttermilk = 15 tbsp milk + 1 tbsp lemon juice. `resolve_rules` converts both sides with
`KnowledgeStore.unit_weight` (USDA portions where available), so the grams-per-gram ratios are *derived*, not typed in
(buttermilk → milk 0.92, lemon juice 0.06).

## Decisions

* **A rule step on the replay, not a change to the optimiser.** The optimiser does not know about swaps, so it never
  chooses a recipe *because* a swap makes it cheap. Swaps can only shrink the grocery box and the waste of a plan
  chosen without them. Folding them into the MILP (a substitute-use variable per rule and day) is possible future work.
* **The benchmark scores plans without substitutions** (`evaluation/metrics.py` still calls `account_inventory`).
  That keeps runs comparable with earlier ones and with the optimiser's own objective. Since swaps only lower
  groceries and waste, the benchmark is the conservative figure.
* **Errors, not silent skips:** the rule table is code, so a rule that cannot be resolved is a bug. A test resolves
  every rule against the real dataset.
* **Dislikes block a substitute** even though they are only soft for recipes: a swap should never put something the
  user said they dislike into a dinner they did not choose for it.

## Limits

* Nutrition of a swapped dinner is not recomputed; it stays the recipe's computed value.
* Rules are one-directional and context-free. "Heavy cream → milk + butter" is fine in a sauce, but not for whipping
  (the note says so); the system cannot tell how the recipe uses the ingredient.
* The table is small and hand-curated (dairy, flour, citrus, shallot, brown sugar, wine, margarine, ricotta).

## Tests

[`tests/optimizer/test_substitutions.py`](../tests/optimizer/test_substitutions.md)

## Logging

Logger `optimizer.substitutions`. DEBUG: one line per fired rule (day, rule, grams, replaced ingredient id).

## Change log

- 2026-10-16 — Created: rule table, gram conversion, hard-rule-checked substitutes, spare-stock-only application,
  shared `replay_with_substitutions` used by the explainer, the app and re-planning.
