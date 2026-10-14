# `tests/test_logging_setup.py`

## Purpose

Tests [`src/logging_setup.py`](../logging_setup.md).

## What is covered

| Test | Guarantees |
| --- | --- |
| `test_repeated_calls_do_not_duplicate_handlers` | Calling `configure_logging` again (Streamlit reruns) replaces our handler and does not add another |
| `test_level_comes_from_the_environment_and_defaults_to_info` | `INFO` by default; `PTP_LOG_LEVEL` is read case-insensitively; an explicit argument wins |
| `test_unknown_level_is_an_error_not_a_silent_default` | A typo in the level raises `ValueError` |
| `test_log_file_receives_records` | `PTP_LOG_FILE` creates the folder and receives formatted lines (level, logger name, message) |
| `test_chatty_third_party_loggers_are_capped_at_warning` | `httpx` etc. are capped at WARNING, and never made more verbose than the chosen level |
| `test_timed_logs_duration` / `..._reports_failure_and_re_raises` / `..._is_silent_when_its_level_is_disabled` | `timed` reports elapsed ms, reports failures without swallowing them, and logs nothing when its level is off |

An autouse fixture restores the root logger's level and handlers after each test, so pytest's own log capture is
unaffected.

## Change log

- 2026-10-14 — Created.
