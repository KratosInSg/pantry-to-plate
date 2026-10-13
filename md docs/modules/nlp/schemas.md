# `src/nlp/schemas.py`

## Purpose

The typed objects that cross the NLP module boundary. They are what the UI renders, what the planner turns into
pantry inventory, and what the evaluation compares with hand-labelled ground truth (`result.model_dump()`).

## Public API

| Name | What |
| --- | --- |
| `Urgency` | `NONE` / `SOON` / `URGENT` |
| `MatchStatus` | `MATCHED` / `AMBIGUOUS` / `UNKNOWN` |
| `GramsSource` | How `grams` was obtained, from `EXPLICIT_MASS` (best) to `UNKNOWN` |
| `Suggestion` | `ingredient_id`, `canonical_name`, `score` — for "did you mean …?" |
| `ParsedItem` | One understood item (see field groups below) |
| `ParseResult` | `source_text`, `items`, `unparsed`; helpers `resolved_items`, `needs_attention` |

## `ParsedItem` field groups

| Group | Fields |
| --- | --- |
| what was typed | `raw_text`, `name_text` |
| which ingredient | `ingredient_id`, `canonical_name`, `match_status`, `match_method`, `match_confidence`, `suggestions` |
| how much | `quantity_value`, `quantity_unit`, `quantity_text`, `size`, `grams`, `grams_source`, `quantity_is_assumed` |
| state / urgency | `modifiers`, `storage_hint`, `urgency`, `urgency_cue`, `days_left_hint` |
| diagnostics | `confidence`, `warnings` |

## Design decisions

* **pydantic, not dicts** — validation, JSON round-trip (`model_validate(model_dump(mode="json"))` is tested) and a
  stable contract for three consumers.
* **Assumptions are first-class fields.** `grams_source` + `quantity_is_assumed` + `warnings` exist so nothing
  inferred can be mistaken for something the user said.
* **`confidence` is a ranking signal**, not a probability.

## Change log

- 2026-10-12 — Created.
- 2026-10-12 — Added `ParsedItem.days_left_explicit` (known date vs our estimate).
