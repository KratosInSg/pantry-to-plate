# `tests/nlp/test_quantities.py`

Tests [`nlp/quantities.py`](../../nlp/quantities.md). Almost entirely pure logic.

| Test | Pins |
| --- | --- |
| `test_numbers_and_units` | digits, fractions, mixed numbers, glued/spaced units, `fl oz`, "a bag of", "a handful of" |
| `test_fraction_and_dozen_words` | half / quarter / three quarters / dozen / half a dozen |
| `test_range_uses_lower_bound` | `2-3` → 2 and `is_range` |
| `test_explicit_mass_is_converted` | g / kg / lb / "about 200g" → grams |
| `test_pack_multiplier_and_container_words` | `2 x 400g tins` → 800 g, "tins" dropped |
| `test_bracketed_weight_belongs_to_the_container` | `1 can (400g)` keeps unit `can` + explicit 400 |
| `test_vague_words_are_reported_not_resolved` | some / a little / a few (=3) / a couple of (=2) / leftover |
| `test_trailing_quantities` | `eggs x4`, `milk 1l`, `spinach - 3`, `6 pcs` |
| `test_no_quantity_when_digits_are_part_of_the_name` | `5 spice powder`, `2% milk`, `7 up` |
| `test_size_words_are_extracted` | `2 medium potatoes`, `large onion` |
| `test_parse_number_token` | token-level number parsing, `1/0` rejected |
| `test_physical_units_match_the_reference_csv` | parser vocabulary ↔ `unit_conversion.csv` cannot drift (needs the dataset) |

## Change log

- 2026-10-12 — Created.
