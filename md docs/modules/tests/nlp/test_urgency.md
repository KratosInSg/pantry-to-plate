# `tests/nlp/test_urgency.py`

Tests [`nlp/urgency.py`](../../nlp/urgency.md). Uses the `today` fixture (Monday 2026-10-12).

| Test | Pins |
| --- | --- |
| `test_qualitative_cues` | "getting old" → SOON/3; "going bad", "wilting" → URGENT/1; remainder is just the food |
| `test_explicit_dates` | tomorrow, today, "good for 3 days", "use by friday" (=4), "next friday" (=4), "in 2 weeks" (reported, not urgent) |
| `test_remainder_has_no_dangling_words` | regression: overlapping spans left "today" behind |
| `test_no_cue_and_negation` | "not going bad", "still fresh", "isn't getting old" → no cue |
| `test_mouldy_is_flagged_unsafe` | `may_be_unsafe` is set |
| `test_bare_cue_leaves_empty_remainder_and_scope` | pronoun-only fragments and `item`/`both`/`all` scope |

## Change log

- 2026-10-12 — Created.
- 2026-10-12 — Added `test_explicit_flag_separates_known_dates_from_guesses`.
