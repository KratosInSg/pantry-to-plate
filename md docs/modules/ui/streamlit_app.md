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

## Logging

Calls `logging_setup.configure_logging()` before `main()`. It is idempotent, so Streamlit re-running the script on each interaction does not duplicate lines. Logs go to the terminal running `streamlit run`. Use `PTP_LOG_LEVEL=DEBUG` for the detailed trace and `PTP_LOG_FILE=...` to keep it.

## Today and the language model

* **Today** is `logic.local_today(st.context.timezone, now, $PTP_TIMEZONE)`, not `date.today()`. Set `PTP_TIMEZONE` (e.g. `Asia/Singapore`) on a host whose visitors' browsers might not report a zone.
* **LLM switch**: `llm_reachable(LlmConfig.from_env())` probes the configured model (cached `LLM_PROBE_TTL_S` = 300 s). When nothing answers (a cloud host), the switch is not shown and the service is rules-only. Starting Ollama locally shows the switch within five minutes.

## Change log

- 2026-10-13 — Created.
- 2026-10-13 — Page shell: stylesheet, hero (replaces `st.title`), step strip, toasts after planning and re-planning.
- 2026-10-14 — Configures logging at start-up (`logging_setup.configure_logging`).
- 2026-10-14 — Profile notes and validation errors are escaped with `logic.md_escape` (they quote what the user typed). `.streamlit/config.toml` now hides tracebacks (`showErrorDetails = "none"`) and developer menu items.
- 2026-10-14 — "Today" comes from the visitor's browser timezone; the LLM switch is shown only when a model is reachable.
- 2026-10-16 — After a re-plan, the profile's `rated_dinners` are kept in `st.session_state["rated_dinners"]` so the next "Plan my week" uses them.
