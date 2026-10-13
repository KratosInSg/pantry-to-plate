# `src/nlp/urgency.py`

## Purpose

Detect "use me soon" cues in a fragment and translate them into a level (`NONE` / `SOON` / `URGENT`) and, where
possible, days left. This is the input to the optimiser's waste term: URGENT items are scheduled first.

## Public API

| Name | What |
| --- | --- |
| `find_urgency(fragment, today=None) -> (UrgencyCue \| None, remainder)` | Detect cues; return the fragment with them removed |
| `UrgencyCue` | `level`, `cue` (phrase), `days_left`, `may_be_unsafe`, `scope` (`item`/`both`/`all`) |
| `URGENT_DEFAULT_DAYS = 1`, `SOON_DEFAULT_DAYS = 3`, `SOON_THRESHOLD_DAYS = 4` | Assumptions behind the mapping |

## Cue families and mapping

| Family | Examples | Level | Days |
| --- | --- | --- | --- |
| explicit day | `expires tomorrow`, `use by friday`, `must be used today` | by days: ≤1 URGENT, ≤4 SOON, else NONE | exact |
| explicit duration | `good for 3 days`, `expires in 2 weeks` | by days (same thresholds) | exact |
| urgent words | `going bad`, `about to go off`, `wilting`, `overripe`, `use asap` | URGENT | 1 (assumed) |
| soon words | `getting old`, `needs using up`, `past its best`, `very ripe` | SOON | 3 (assumed) |
| unsafe words | `mouldy`, `gone off`, `slimy`, `expired` | URGENT + `may_be_unsafe` | 0 |

The "assumed" day counts are planning assumptions. The FoodKeeper shelf-life row for the ingredient can refine them
downstream.

## Behaviour worth knowing

* **Negation:** a cue is ignored when `not / isn't / still / never ...` appears in the 3 words before it
  (`not going bad`, `still fresh`).
* **"next friday"** means the coming Friday (everyday speech); only "next <today's weekday>" means +7 days.
* **Bare cues:** `"they're going bad"` returns an empty remainder; the parser attaches the cue to the previous
  item(s). `scope` says how far back (`both` = previous two, `all` = everything so far).
* **Safety:** `may_be_unsafe` lets the application refuse to plan with food that may already be unsafe.
* **Overlapping matches** (`must be used` + `must be used today`) are merged before removal so no stray words stay.

## Limits

English only; weekday names and today/tomorrow/in-N-days only (no calendar dates like "15 Oct"); no per-ingredient
sensitivity (a "bit old" loaf and "a bit old" fish are the same SOON).

## Tests

[`tests/nlp/test_urgency.py`](../tests/nlp/test_urgency.md)

## Change log

- 2026-10-12 — Created. Fixed overlapping-span cut ("must be used today" left "today" behind) and made "next friday"
  mean the upcoming Friday.
- 2026-10-12 — Added `UrgencyCue.explicit`: True for stated dates/durations ("expires tomorrow", "good for 3 days"), False for qualitative cues. The planner treats explicit dates as known constraints and the rest as estimates.
