# `src/nlp/segmenter.py`

## Purpose

First stage of the NLP pipeline: normalise the raw message and split it into **one fragment per pantry item**.

## Public API

| Name | What |
| --- | --- |
| `split_items(text, protected_phrases=()) -> list[str]` | Normalise, strip lead-ins, split; returns lower-case fragments |
| `normalise_input(text) -> str` | Unicode, quotes, vulgar fractions, case, whitespace. Reusable on its own |

`protected_phrases` should be `KnowledgeStore.connector_phrases` (aliases that contain "and"/"&").

## Why this is the hard part

The words that separate items also live *inside* names and quantities. The module protects those spans with
placeholder characters before splitting and restores them after:

| Looks like a separator | Is actually | Handled by |
| --- | --- | --- |
| `salt **and** pepper`, `half and half` | an ingredient name | protected phrases from the alias table (longest first) |
| `one **and** a half cups` | a quantity | rewritten to `1 1/2` before splitting |
| `1,000 g`, `1.5 kg` | a number | thousands/decimal placeholders |
| `(going bad, a bit slimy)` | one note | bracket protection |
| `1½` | a number | fractions replaced **before** Unicode NFKC (NFKC would turn it into `11⁄2`) |

## Separators and lead-ins

Split on: `,` `;` newline, ` & `, `and`, `plus`, `also`, `as well as`, `. ` and ` / `. **Not** on `with` ("chicken
with skin"). Bullets (`-`, `*`, `•`, `1.`) are removed. Lead-ins are stripped at the start of the message, of each
line and after each separator: "I have", "we've got", "there is", "in my fridge:", "also", "oh and" …

## Limits

* "mac and cheese" splits into "mac" and "cheese" unless that exact phrase is an alias.
* Numbered lists "1. eggs" are handled as bullets; a quantity that starts a line with a dot ("1. egg") is ambiguous.
* A list item that itself contains a comma without brackets ("eggs, large") becomes two fragments.

## Tests

[`tests/nlp/test_segmenter.py`](../tests/nlp/test_segmenter.md)

## Change log

- 2026-10-12 — Created. Fixed fraction handling order (vulgar fractions before NFKC).
