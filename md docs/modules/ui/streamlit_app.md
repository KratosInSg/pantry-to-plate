# `src/ui/streamlit_app.py`

## Purpose

The script Streamlit runs (`streamlit run src/ui/streamlit_app.py`). It sets up the page, builds the cached service,
and wires the pantry step, the plan button and the week view together. Everything else is in `views.py` / `logic.py`.

## Flow

```
get_service(use_llm)  ── cached per process and LLM setting; holds the dataset and the parser's fuzzy index
sidebar_profile       ── the form (needs the service for the cuisine list)
pantry_step           ── text → editable rows → the rows to plan with
[Plan my week]        ── build_profile → make_scenario → plan_week   (a spinner; ~4-6 s)
week_view             ── tabs, marks, [Re-plan the remaining days] → replace the week, rerun
```

## Decisions

* **`src/` is put on `sys.path` by the script itself**: Streamlit adds only the script's folder, and the project's
  packages live one level up.
* **One service per process** (`st.cache_resource`), keyed by the LLM switch: it is read-only after construction, and
  rebuilding it would reload the dataset.
* **A profile error is shown, not raised.** `build_profile` raises `ValueError` for an out-of-range number; the page
  turns it into `st.error` and does not plan.
* **The LLM defaults on but is optional.** An unreachable model is normal; every screen works without it.

## Tests

[`tests/ui/test_app.py`](../tests/ui/test_app.md)

## Change log

- 2026-10-13 — Created.
- 2026-10-13 — Page shell: stylesheet, hero (replaces `st.title`), step strip, toasts after planning and re-planning.
