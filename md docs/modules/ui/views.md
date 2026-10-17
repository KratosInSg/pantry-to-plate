# `src/ui/views.py`

## Purpose

The Streamlit layout, one function per screen area. No planning, parsing or explaining happens here: a view reads
results from `PantryToPlateService`, lays them out, and reports what the user did.

## Functions

| Function | Screen area |
| --- | --- |
| `sidebar_profile(service)` | The profile form; returns the values for `service.build_profile` and the LLM switch |
| `pantry_step(service, today)` | Text box, "Read my pantry", "Use an example", the review rows, "Add something we missed"; returns the rows to plan with |
| `week_view(service, week)` | Metrics, the four tabs, and the re-plan controls; returns a new `PlannedWeek` if the user re-planned |
| `_day_card`, `_shopping_tab`, `_why_tab`, `_rules_tab` | Parts of the week view |

## State (`st.session_state`)

`review_id` (bumps on every new reading, so widget keys never leak between readings) · `entries` / `originals`
(the editable rows and the rows as first parsed, to restore "we estimate") · `week` (the current plan) / `week_id` ·
`reworded` (an LLM-reworded copy of the plan) · `read_requested` (set by the example button's callback) ·
`rated_dinners` (dinners marked "Loved it", kept for the session; shown in the Tastes section with a "Forget them" button,
and passed to `build_profile` so a fresh plan learns from them).

## Pantry review rows

Each row reads `🥬 **Spinach** (Ready)`: the food's own icon (`theme.food_icon`, from the row's `food_group`) in a
narrow first column, drawn large on a round tile (`theme.food_icon_html`), then the name, and a coloured status badge (Streamlit's `:color-badge[...]`, label from `logic.status_badge`, colour from
`KIND_BADGE`): green *Ready*; orange *Check amount* (planned, but on our guessed amount); red *Pick one* /
*Not recognised* / *Add amount* (needs the user first); grey *Left out* (unsafe, never planned). The status used to
be a leading emoji (✅ 🟡 ❓ ❌ ⚠️); with a food icon in that spot two emojis competed, and a word is clearer than a
colour code. Rows that need explaining (a choice, an unsafe item) keep their sentence underneath. The icon is
decorative: the name is always next to it. It has its own column because Markdown cannot size one character and the
name line holds user text that must never be rendered as HTML. On a phone-width screen Streamlit stacks columns, so
the icon sits above the name. It also helps checking the parse: a wrong match shows a wrong-looking icon.

## Things that were learned the hard way

* **Widget state can only be set in a callback.** Assigning to `st.session_state["pantry_text"]` after the text area
  exists raises `StreamlitAPIException`; "Use an example" crashed on the first real click until it became a callback
  that only *queues* the read. Found by the headless test, not by reading the code.
* **A slow step needs a spinner.** The first read can take ~30 s when Ollama must load the model; without a spinner
  the page looked frozen.
* **A default shown in an editor is still an assumption.** A row with no amount is displayed with 100 g so there is
  something to edit, and is stored as an *assumed* quantity — not presented as the user's.

## Limits

* One user, one session; no persistence across browser sessions.
* The plan is replaced in place on re-plan (no history / undo yet).
* Layout is functional, not designed: no custom theme.

## Tests

Through [`tests/ui/test_app.py`](../tests/ui/test_app.md).

## Change log

- 2026-10-13 — Created.
- 2026-10-13 — Redesign: card containers with keys (styled by `theme.py`), chips on each dinner, reasons/ingredients/steps behind expanders, grouped sidebar, shopping list in grouped cards, empty states.
- 2026-10-14 — Diet selector defaults to vegetarian (`DEFAULT_DIET`) and has a help tooltip defining each diet (`DIET_HELP`), since vegetarian here excludes eggs.
- 2026-10-14 — Security: `max_chars` on every text box (`MAX_PANTRY_CHARS`, `MAX_FOOD_FIELD_CHARS` = 300, `MAX_QUERY_CHARS`); user and dataset text escaped with `logic.md_escape` before Markdown; over-limit text shows an error instead of failing.
- 2026-10-14 — `sidebar_profile(service, offer_llm=True)`: `offer_llm=False` hides the LLM switch (returns `False`).

- 2026-10-15 — Diet sidebar now exposes strict food exclusions separate from allergies.
- 2026-10-16 — Ingredients table shows "swap: milk (25 g) and lemon juice (1.7 g)" in the From column when a substitution rule replaced buying an item.
- 2026-10-16 — Tastes section shows how many loved dinners shape new plans (with "Forget them"); `sidebar_profile` returns `rated_dinners`; re-plan passes `loved`.
- 2026-10-17 — Pantry rows show the food's icon and a coloured status badge (`KIND_BADGE`, `_row_heading`) instead of a status emoji and a status line; the icon is shown large in its own column.
- 2026-10-17 — Ingredients table has a Protein column next to Amount (per serving, grams × USDA; "—" when USDA has no value).
