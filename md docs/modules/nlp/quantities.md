# `src/nlp/quantities.py`

## Purpose

Peel the **amount** off a pantry fragment and return it with the remaining words. Pure text processing: no dataset,
no I/O.

## Public API

| Name | What |
| --- | --- |
| `extract_quantity(fragment) -> (Quantity \| None, remainder)` | Main function. `None` when no amount is stated |
| `Quantity` | `value`, `unit`, `explicit_grams`, `vague_word`, `is_range`, `size`, `text` |
| `parse_number_token(token) -> (value, is_range) \| None` | One token as a number (`2`, `1.5`, `1/2`, `2-3`) |
| `UNIT_ALIASES`, `PHYSICAL_UNITS`, `MASS_UNITS` | Unit vocabulary (alias → canonical name) |

## What it understands

| Kind | Examples |
| --- | --- |
| digits / decimals / fractions / mixed | `2`, `1.5`, `1/2`, `1 1/2` |
| ranges (lower bound) | `2-3 carrots` → 2 |
| number & fraction words | `four eggs`, `half a cabbage`, `a quarter of an onion`, `three quarters`, `a dozen`, `half a dozen` |
| units glued or spaced | `500g`, `2 tbsp`, `1 lb`, `10 fl oz`, `3 cloves` |
| pack multipliers | `2 x 400g tins tomatoes` → 800 g |
| bracketed weight | `1 can (400g) chickpeas` → 1 can, explicit 400 g |
| trailing forms | `eggs x4`, `milk 1l`, `spinach - 3`, `6 pcs sausages` |
| vague words | `some`, `a few` (=3), `a couple of` (=2), `a little`, `leftover` |
| size words | `large onion`, `2 medium potatoes` |

## Decisions

1. **Ranges use the lower bound.** For supply planning it is safer to assume the user has what they are sure of.
2. **Vague words are reported as words**, except count words (`a few`, `a couple of`, `several`) which carry a
   number. What "some" means depends on the ingredient, so the parser decides (see `defaults.py`).
3. **"a"/"an" means 1** at the start of a fragment.
4. **Digits that belong to a name are not quantities**: `5 spice powder`, `7 up`, `2% milk`.
5. **Brackets with other words keep their words** (`(going bad)`), only a mass in brackets is consumed.
6. **Physical unit names must match `data/canonical/reference/unit_conversion.csv`** — enforced by a test, because the
   knowledge store converts them using that file.

## Limits

* Single-letter units (`c`, `t`, `T`) are not accepted except `l` glued to a number — too ambiguous.
* Compound number words above 20 ("twenty-five") are not parsed; digits are.
* A bare trailing number reads as a count (`tomatoes 4`); a name that legitimately ends in a number would be
  misread (none known in the dataset).

## Tests

[`tests/nlp/test_quantities.py`](../tests/nlp/test_quantities.md)

## Change log

- 2026-10-12 — Created. `explicit_grams` is rounded to 2 dp to avoid float noise (680.3879999 → 680.39).
- 2026-10-12 — Added public read-only `NUMBER_WORDS` / `FRACTION_WORDS` (aliases of the private tables) so the LLM
  fallback can check that a number it reports occurs in the user's text. No behaviour change.
- 2026-10-12 — Cleanup (no behaviour change): removed a redundant condition in `_number_phrase`; documented why
  `b`/`v` + digit (vitamin b12, v8) are not split in `_tokenise`.
