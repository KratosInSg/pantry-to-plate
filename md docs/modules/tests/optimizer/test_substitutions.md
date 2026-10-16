# `tests/optimizer/test_substitutions.py`

Tests [`src/optimizer/substitutions.py`](../../optimizer/substitutions.md).

## What it checks

| Area | Tests |
| --- | --- |
| Mechanics (fake catalogue, hand-written rules) | a rule fires when the dinner buys the food and spare stock covers it; grams move from groceries to pantry use; the input replay is unchanged |
| Never costs another dinner | stock a later dinner needs is not spare; two swaps compete for the same spare stock in day order |
| Rule conditions | a substitute past its deadline blocks the rule; a disallowed substitute blocks the rule and the next is tried; rules are tried in order; no partial swap; pinches are ignored |
| Accounting | own stock of the food is used first and only the shortfall is swapped; swapping in expiring stock lowers waste; a staple substitute is available but not accounted |
| Rule table (real dataset) | every rule resolves, keys are unique, ratios are positive, buttermilk → milk 0.92 + lemon juice 0.06; an unknown ingredient or unit raises |
| Safety (real dataset) | vegan blocks butter; dairy allergy, "never" and dislike each block milk |
| Integration | a real buttermilk recipe with milk + lemon juice in the pantry fires `buttermilk_milk_lemon`; with a dairy allergy nothing fires |

## Change log

- 2026-10-16 — Created.
