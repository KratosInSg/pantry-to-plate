# `build/matcher.py`

## Purpose

`UsdaIndex`: a transparent lexical matcher from an ingredient name to the best USDA FoodData Central food (reused to
match FoodKeeper product names). USDA descriptions look like `"Oil, olive, salad or cooking"` or `"Onions, raw"` —
category first, then qualifiers — so plain string similarity misleads; this scores with that structure in mind.

## Public API

| Name | What |
| --- | --- |
| `UsdaIndex(foods_df)` | `foods_df` columns: `fdc_id`, `description`, `data_type`, `category` |
| `UsdaIndex.match(name, topk=5)` | list of `{fdc_id, description, data_type, score}`, best first |
| `tokens(text, drop_noise)`, `singular(word)` | tokenisation helpers |

## Scoring

`score = idf-weighted token coverage + head bonus + noun bonus + raw bonus − variant penalty − extra-token penalty
+ source bonus − category penalty`

| Term | Effect |
| --- | --- |
| coverage | share of the query's (IDF-weighted) tokens present in the description |
| head bonus (+0.10; +0.30 exact head; +0.25 head+first qualifier) | `butter` → `Butter, salted`; `olive oil` → `Oil, olive, …` |
| raw bonus (+0.08) | prefer raw commodity over cooked/processed |
| variant penalty (−0.12 per word) | cooked/canned/frozen/baby-food/restaurant… unless the query asked for it |
| extra-token penalty (−0.03 each, max 10) | prefer short, generic descriptions |
| source bonus | SR Legacy +0.03, Foundation 0, FNDDS −0.20 (SR has the richest portion data) |
| category penalty | Baby Foods / Fast Foods / Restaurant / Meals / Snacks … |

## Known behaviour

It is right for specific items (`cumin`, `parmesan cheese`) and **wrong for short generic heads** (`butter`, `egg`,
`milk`, `water`: dozens of near-identical USDA rows). That is why the head of the frequency distribution is governed by
`reference/ingredient_usda_overrides.csv` and the matcher only handles the long tail (score ≥ 0.80 accepted).
Automatic stripping of descriptor words was tried and rejected (`rib eye steak` → `Ribs, NFS`).

## Change log

- 2026-10-12 — Created (docs backfilled). FNDDS penalty raised from −0.06 to −0.20; exact-head bonuses added.
