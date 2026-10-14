# `src/ui/logic.py`

## Purpose

The decisions behind the UI that are worth testing, kept free of Streamlit so they run without a browser.

## Public API

| Name | What |
| --- | --- |
| `build_replan_request(recipe_ids, marks) -> ReplanRequest` | Turns the per-day marks (*Planned / Cooked / Skipped / Reject this dinner*) into what `service.replan` needs: `cooked` (a recipe id, or `None` per skipped day), `rejected`, `remaining_days` |
| `ReplanRequest` | `ok`, `changed`, `problem`, `describe(rejected_names)` — one sentence saying what the button will do |
| `use_by_choices(start_weekday, horizon, original)`, `current_use_by_index`, `apply_use_by` | The use-by selector: our estimate, each day of the plan, "won't go off this week"; and how a choice changes an entry |
| `status_label(entry)`, `needs_choice(entry)` | Row wording and which rows must ask "which one?" |
| `display_name(name)` | Display form of a recipe/ingredient name; restores the possessive Food.com dropped ("julie s" → "Julie's") |
| `weekday_label(start_weekday, day, day_offset=0)`, `EXAMPLE_PANTRY`, `DAY_*` | Helpers and constants |

## Rules

* **The past is a leading run of Cooked / Skipped days.** After it a day can only be Planned or Rejected. A day marked
  Cooked after an unresolved one is a *contradiction* and is reported ("Mark days in order…"), not guessed at.
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

## Change log

- 2026-10-13 — Created.
- 2026-10-14 — Added `md_escape` (security review: typed links and images were rendered).
