# `src/logging_setup.py`

## Purpose

One place that decides where the project's log lines go and how much is shown, so you can follow a session from
pantry text to plan in one timeline: what ran, in which order, how long it took, and where it fell back.

## Where it sits

Outside the pipeline, used at both ends:

* **Library modules only emit.** Each one has `logger = logging.getLogger(__name__)` and calls `debug` / `info` /
  `warning`. They never add handlers or set levels, so importing one never changes anybody's output.
* **Entry points configure, once.** `ui/streamlit_app.py`, `evaluation/runner.py`, `evaluation/build_benchmark.py`
  and `evaluation/weight_sweep.py` call `configure_logging()` at start-up. Nothing else does.

Logger names are module paths (`nlp.pantry_parser`, `optimizer.weekly`, `app.service` …), so the name in each line
shows where in the pipeline it came from.

## Public API

| Name | What |
| --- | --- |
| `configure_logging(level=None, log_file=None, environ=None) -> int` | Installs a stderr handler (plus a file handler if asked) on the root logger and sets its level. Returns the level applied. Raises `ValueError` for an unknown level name. Safe to call repeatedly |
| `timed(logger, what, level=DEBUG)` | Context manager: logs `"<what> took N ms"` when the block ends, or `"<what> failed after N ms"` and re-raises |
| `ENV_LOG_LEVEL = "PTP_LOG_LEVEL"` | Default `INFO` |
| `ENV_LOG_FILE = "PTP_LOG_FILE"` | Optional; also append to this file (folders are created) |
| `QUIET_LOGGERS` | Third-party loggers capped at WARNING (httpx, urllib3, watchdog, numexpr, …) |

Usage:

```bash
PTP_LOG_LEVEL=DEBUG streamlit run src/ui/streamlit_app.py
PTP_LOG_FILE=logs/session.log streamlit run src/ui/streamlit_app.py
python src/evaluation/runner.py --split validation --planners optimiser --limit 6 --log-level DEBUG
```

On Windows PowerShell, set the variable first: `$env:PTP_LOG_LEVEL = "DEBUG"`.

## Level policy

| Level | Used for | Examples |
| --- | --- | --- |
| `DEBUG` | Detail inside a step | each parsed fragment and how it was matched; model size; each LLM request; each table read; each rejected paraphrase |
| `INFO` | One line per step a user would recognise | service ready; pantry reviewed (row counts by status); planning N days; plan ready (status, dinners, grocery items, seconds); re-planned; what went off |
| `WARNING` | A degradation the user gets | LLM unreachable or failed, so the rules / template result was kept; solver returned no plan; incomplete week; CP-SAT worker timed out |
| `ERROR` | Reserved for failures that are caught and survived | none yet; uncaught failures propagate as exceptions |

Per-scenario detail in `optimizer/` is DEBUG on purpose: the benchmark runner plans hundreds of scenarios, and
the service writes the INFO line for the app.

## Decisions

* **The level is set on the root logger, not on our handler.** pytest's `caplog` and any other handler then see the
  same records ours do.
* **Idempotent.** Our handlers carry a tag attribute; a second call removes them before adding new ones. Streamlit
  re-executes the app script on every interaction, so this matters: otherwise each click would double every line.
* **Privacy.** The pantry text a user types is logged at DEBUG only (`app.service`), and LLM prompts, answers and API
  keys are never logged (only sizes and timings).
* **The log is not a data channel.** Anything the explainer or evaluation needs (assumptions, fallbacks, cost terms)
  is still recorded in the returned objects, as CLAUDE.md requires. The log only shows a developer what happened.
* **CLI reports stay `print`.** The runner's and sweep's result tables are the program's output, not log records.
  Only progress lines moved to the log.

## Limits

* The CP-SAT worker (`optimizer/cpsat_worker.py`) runs as `python -I` in a child process and does not log. The parent
  logs its start, result and (at DEBUG) its stderr on failure.
* `weight_sweep.py` worker processes keep Python's default (WARNING and above to stderr).
* The offline build (`src/knowledge/build/`) still reports with `print`.

## Tests

[`tests/test_logging_setup.py`](tests/test_logging_setup.md). Log calls in modules are tested where they mark a
degradation: `tests/nlp/test_llm_fallback.py`, `tests/explain/test_paraphrase.py`, `tests/app/test_service.py`.

## Change log

- 2026-10-14 — Created: `configure_logging`, `timed`, level policy; wired into the app and the evaluation CLIs.
