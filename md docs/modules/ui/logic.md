# `src/ui/logic.py`

## Purpose

The decisions behind the UI that are worth testing, kept free of Streamlit so they run without a browser.

## Public API

| Name | What |
| --- | --- |
| `build_replan_request(recipe_ids, marks) -> ReplanRequest` | Turns the per-day marks (*Planned / Cooked / Loved it / Skipped / Reject this dinner*) into what `service.replan` needs: `cooked` (a recipe id, or `None` per skipped day), `loved`, `rejected`, `remaining_days` |
| `ReplanRequest` | `ok`, `changed`, `problem`, `loved`, `describe(rejected_names, loved_names)` — one sentence saying what the button will do |
| `use_by_choices(start_weekday, horizon, original)`, `current_use_by_index`, `apply_use_by` | The use-by selector: our estimate, each day of the plan, "won't go off this week"; and how a choice changes an entry |
| `status_label(entry)`, `status_badge(entry)`, `needs_choice(entry)` | Row wording, the short badge tag (*Ready*, *Check amount*, *Pick one*, *Not recognised*, *Add amount*, *Left out*; fixed text, safe in Markdown), and which rows must ask "which one?" |
| `display_name(name)` | Display form of a recipe/ingredient name; restores the possessive Food.com dropped ("julie s" → "Julie's") |
| `weekday_label(start_weekday, day, day_offset=0)`, `EXAMPLE_PANTRY`, `DAY_*` | Helpers and constants |

## Rules

* **The past is a leading run of Cooked / Loved it / Skipped days.** After it a day can only be Planned or Rejected. A
  past mark after an unresolved day is a *contradiction* and is reported ("Mark days in order…"), not guessed at.
* **"Loved it" is "Cooked", plus rating evidence:** the dinner counts as eaten and its recipe id is in `loved`, so the
  service adds it to the profile's rated dinners.
* **Rejecting today's dinner is not "elapsed".** It re-plans from day 0 with that recipe excluded.
* **Marking every day done is an error** ("nothing left to plan"), never an empty plan.
* **"Not sure" restores the parser's estimate**; picking a day states a hard deadline; "won't go off" states the
  absence of one.

## Limits

* The use-by selector offers whole days only, relative to today.
* `display_name` is a heuristic for one known artefact of the dataset's names.

## Tests

[`tests/ui/test_logic.py`](../tests/ui/test_logic.md)

## Markdown safety

`md_escape(text)` backslash-escapes every punctuation character that Markdown or Streamlit's extensions (`:color[...]`, `:material/...:`, `$` LaTeX) could act on, and folds newlines to spaces. Use it on any user- or dataset-derived string placed inside `st.markdown` / `st.warning` / `st.error`. HTML needs no escaping there (Streamlit strips it); the HTML helpers in `ui.theme` use `html.escape`.

## The user's today

`local_today(browser_timezone, now_utc, configured_timezone=None) -> (date, source)` returns the calendar date where the user is. Order: the browser's IANA zone (`st.context.timezone`), then `PTP_TIMEZONE`, then the server's own date. `source` says which one was used. The browser value is client-supplied, so an unknown or malformed name is ignored rather than raising. Why it matters: "today" sets the plan's weekday names and how many days a stated use-by leaves, and a cloud host runs on UTC (a day behind Singapore from 00:00 to 08:00).

## Change log

- 2026-10-13 — Created.
- 2026-10-14 — Added `md_escape` (security review: typed links and images were rendered).
- 2026-10-14 — Added `local_today` (the user's date from the browser timezone; fixes weekday names on a UTC server).
- 2026-10-16 — "Loved it" day mark (`DAY_LOVED`): a cooked day whose recipe becomes rating evidence (`ReplanRequest.loved`).
- 2026-10-17 — Added `status_badge` (the short tag on a pantry row's coloured badge).
