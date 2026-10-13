# `src/ui/` — the Streamlit prototype

## Purpose

A first, working front end: describe your pantry in words, check what was understood, plan the week, read the reasons,
shop, cook, and re-plan when life happens. It is **layout and state only** — every decision is the backend's
(`app.service.PantryToPlateService`), so the UI can be replaced (React, mobile) without touching a rule.

```bash
streamlit run src/ui/streamlit_app.py        # then open http://localhost:8501
```

## Files

| File | Role | Doc |
| --- | --- | --- |
| `streamlit_app.py` | The script Streamlit runs: page set-up, the cached service, the plan button, state wiring | [streamlit_app.md](streamlit_app.md) |
| `views.py` | One function per screen area (sidebar profile, pantry review, week tabs, day cards) | [views.md](views.md) |
| `theme.py` | The visual language: stylesheet, hero, step strip, chips, empty states | [theme.md](theme.md) |
| `logic.py` | Pure decisions: what day marks mean for a re-plan, use-by choices, labels. No Streamlit | [logic.md](logic.md) |

## What the user sees

1. **About you** (sidebar): diet, allergies, cuisines and foods liked / disliked, calorie and protein targets,
   weeknight time. Unmatched food names are reported, never turned into a different food.
2. **What's in your kitchen?**: free text → one row per item with its status (understood / amount assumed / which one?
   / not recognised), an editable amount, a use-by choice and a "use it" tick. "Add something we missed" is an
   ingredient search.
3. **Plan the week** → four tabs: *Your week* (a card per dinner: why, ingredients with where each comes from, how to
   cook it, and a mark: Planned / Cooked / Skipped / Reject this dinner), *Shopping list*, *Why this plan*,
   *Rules & notes*.
4. **Re-plan the remaining days** from what is left, honouring the marks.

## Design rules

* **Honest by default.** An assumed amount is labelled and stays labelled until the user changes it; an estimated
  use-by says "estimate"; a row we could not recognise is not planned with.
* **The language model is optional and visible.** A sidebar switch controls it; the first read can take ~30 s if
  Ollama has to load the model, and the page says so while it works.
* **Nothing is decided here.** Views read `PlannedWeek`; `logic` interprets marks; the service plans.

## Tests

[`tests/ui/test_logic.py`](../tests/ui/test_logic.md) (pure) and [`tests/ui/test_app.py`](../tests/ui/test_app.md)
(the real script, driven headlessly with Streamlit's `AppTest`).

## Change log

- 2026-10-13 — Package created.
- 2026-10-13 — Redesign: warm palette, hero, 3-step strip, card layout, chips, grouped sidebar, staggered entrance motion (off under reduced motion), toasts. Theme in `theme.py` and `.streamlit/config.toml`.
