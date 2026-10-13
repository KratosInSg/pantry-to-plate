# `src/nlp/defaults.py`

## Purpose

Every *assumption* the NLP layer makes when the user is vague, as named constants with a stated rationale. They are
planning assumptions, not data, so they live in one reviewable file rather than scattered through the parser.

Guiding rule: **be modest.** Over-estimating the pantry produces plans the user cannot cook; under-estimating only
costs an extra grocery item.

## Contents

| Constant | Used when | Example |
| --- | --- | --- |
| `ASSUMED_GRAMS_BY_GROUP` | no quantity at all (`paneer`) or a vague word (`some spinach`) | vegetable 250 g, egg 300 g (six), meat 400 g |
| `ASSUMED_ITEM_GRAMS_BY_GROUP` | "3 carrots" but no per-item weight on file | vegetable 100 g, fruit 130 g |
| `ASSUMED_GRAMS_BY_CONTAINER` | "1 can", "a bag", "3 cloves" with no ingredient-specific weight | can 400 g, clove 3 g |
| `ASSUMED_DENSITY_G_PER_ML` | a volume with no weight data | 1.0 (water-like; flagged `volume_density_assumed`) |
| `VAGUE_COUNT` | count words | a couple of = 2, a few = 3, several = 4 |
| `VAGUE_AMOUNT_FACTOR` | amount words scale the group default | a little = 0.3×, lots of = 1.5× |
| `PREFERRED_ITEM_SIZE` | which size "one X" means when none is given | egg → large (50 g, not medium 44 g) |

## How to change a value

1. Edit the constant and its comment (say *why*).
2. Run `python -m pytest tests/nlp` — tests that pin an assumed value derive it from these constants or from the
   dataset, so they should still pass; update any that encode the old number on purpose.
3. Add a line to the change log below.

## Change log

- 2026-10-12 — Created. Added `PREFERRED_ITEM_SIZE` (eggs → large). Removed "a handful of" / "half a bag of" from the
  vague factors: they are expressed as units (`handful`, `bag`) and handled by the container table.
