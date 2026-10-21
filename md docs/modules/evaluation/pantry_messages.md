# `src/evaluation/pantry_messages.py`

## Purpose

Builds the **synthetic pantry-message set** for evaluation measure 7 (ingredient NLP): every kitchen of the fresh v3
benchmark (`data/evaluation/v3`) written the way a person might type it, with an answer key (which ingredient, the
amount the text states, the urgency cue). The proposal planned a manually written and labelled set; this is the
synthetic substitute, and it says so in `MESSAGES_FROZEN.json` (`"labels": "synthetic ..."`). The same messages are
realistic demo input: paste one into the app and it plans that kitchen's week.

## What varies, and why

| Dimension | Values (answer-key field) | Why |
| --- | --- | --- |
| Name | `top` (most common alias), `variant` (another real alias seen ≥ 20 times), `regional` (Singapore/British usage: prawns, courgette, minced beef, capsicum …), `descriptor` ("fresh", "organic", "local"), `typo` (one swapped / dropped / doubled letter) — `name_variant` | so the score says *where* the parser fails |
| Amount | metric mass, whole items ("2 onions", "half a cabbage", "a head of lettuce"), volume ("300 ml milk", "2 cups of rice"), container ("a can of", "a tray of", "a bunch of"), none ("some spinach") — `quantity.form` | how people actually state amounts; eggs and most fruit/veg are counted, liquids measured by volume |
| Urgency | stated dates for items whose use-by date is known ("expires tomorrow", "use by Friday"), qualitative cues for estimated items due within a day ("going bad", "getting old", "needs using soon"), none — `cue_kind`, `urgency`, `days_left` | the kitchen's own deadlines, said in words |
| Layout | comma list with "and", comma list, one item per line, semicolons, " + "; sometimes an opening ("I have", "Pantry:") or a closing ("and that's it") — `separator` | real messages are not tidy lists |

## Independence from the parser

The phrasing lists were written from how people describe food, not from the parser's vocabulary; nothing here imports
`nlp`. The set is frozen (SHA-256 in `MESSAGES_FROZEN.json`) before the parser sees it. A cue or name the parser does not
know counts against it. **Do not tune the parser on this set**: an improved parser needs a new message set (new seed,
new version) to be measured fairly.

## Public API

| Name | What |
| --- | --- |
| `render_message(scenario, store, seed)` | One kitchen → `{"scenario_id", "family", "today", "separator", "text", "items": [answer key]}`. Pure function of `(scenario, seed)` and the dataset |
| `build_messages(scenarios, store, seed)` | All of them |
| `freeze_messages(messages, eval_dir, seed)` / `load_messages(eval_dir)` | Write + `MESSAGES_FROZEN.json` (refuses to overwrite); load verifying the hash |
| `message_today(scenario)` | Day 0 of the kitchen's week: the date in the week of `REFERENCE_MONDAY` (2026-10-26) with the kitchen's start weekday |
| `pluralise`, `REGIONAL_NAMES`, `URGENT_CUES`, `SOON_CUES` | Spelling helper and the phrasing lists |

CLI: `python src/evaluation/pantry_messages.py --eval-dir data/evaluation/v3 [--dry-run]`.

## State

Frozen 2026-10-21 as `data/evaluation/v3/pantry_messages_m1.jsonl` (seed 20261021): 120 messages, 1,718 items.

## Limits

* Labels come from the generator, so the set measures how well the parser reads **this phrasing**, not a sample of real
  users' messages. A manually written and labelled set is still the proposal's measure.
* Amount wording is derived from the kitchen's grams (counts and cups are rounded), so a message's implied amount can
  differ slightly from the frozen kitchen.

## Tests

[`tests/evaluation/test_pantry_messages.py`](../tests/evaluation/test_pantry_messages.md)

## Change log

- 2026-10-21 — Created; m1 frozen from the v3 kitchens.
