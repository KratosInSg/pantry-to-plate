"""Tests for ``src/logging_setup.py``: configuration is idempotent, levels/files come from arguments or env, and
``timed`` reports durations without swallowing errors.

Every test restores the root logger afterwards, so pytest's own capture (``caplog``) is unaffected.
"""
from __future__ import annotations

import logging

import pytest

from logging_setup import QUIET_LOGGERS, _HANDLER_TAG, configure_logging, timed


@pytest.fixture(autouse=True)
def restore_root_logger():
    root = logging.getLogger()
    level, handlers = root.level, list(root.handlers)
    quiet = {n: logging.getLogger(n).level for n in QUIET_LOGGERS}
    yield
    for h in [h for h in root.handlers if h not in handlers]:
        root.removeHandler(h)
        h.close()
    root.setLevel(level)
    for n, lvl in quiet.items():
        logging.getLogger(n).setLevel(lvl)


def _ours() -> list[logging.Handler]:
    return [h for h in logging.getLogger().handlers if getattr(h, _HANDLER_TAG, False)]


def test_repeated_calls_do_not_duplicate_handlers():
    configure_logging("INFO", environ={})
    configure_logging("INFO", environ={})
    configure_logging("DEBUG", environ={})
    assert len(_ours()) == 1                       # Streamlit re-runs the script; lines must not double up
    assert logging.getLogger().level == logging.DEBUG


def test_level_comes_from_the_environment_and_defaults_to_info():
    assert configure_logging(environ={}) == logging.INFO
    assert configure_logging(environ={"PTP_LOG_LEVEL": "debug"}) == logging.DEBUG
    assert configure_logging("WARNING", environ={"PTP_LOG_LEVEL": "DEBUG"}) == logging.WARNING   # argument wins


def test_unknown_level_is_an_error_not_a_silent_default():
    with pytest.raises(ValueError, match="unknown log level"):
        configure_logging("LOUD", environ={})


def test_log_file_receives_records(tmp_path):
    path = tmp_path / "logs" / "run.log"                 # parent folder is created
    configure_logging("INFO", environ={"PTP_LOG_FILE": str(path)})
    logging.getLogger("optimizer.weekly").info("plan ready")
    for h in _ours():
        h.flush()
    text = path.read_text(encoding="utf-8")
    assert "INFO" in text and "optimizer.weekly: plan ready" in text


def test_chatty_third_party_loggers_are_capped_at_warning():
    configure_logging("DEBUG", environ={})
    assert logging.getLogger("httpx").level == logging.WARNING
    configure_logging("ERROR", environ={})
    assert logging.getLogger("httpx").level == logging.ERROR     # never *more* verbose than the chosen level


def test_timed_logs_duration(caplog):
    log = logging.getLogger("tests.timed")
    with caplog.at_level(logging.DEBUG, logger="tests.timed"):
        with timed(log, "read table"):
            pass
    assert any(r.getMessage().startswith("read table took ") and r.getMessage().endswith(" ms")
               for r in caplog.records)


def test_timed_reports_failure_and_re_raises(caplog):
    log = logging.getLogger("tests.timed")
    with caplog.at_level(logging.DEBUG, logger="tests.timed"), pytest.raises(KeyError):
        with timed(log, "solve"):
            raise KeyError("boom")
    assert any("solve failed after" in r.getMessage() for r in caplog.records)


def test_timed_is_silent_when_its_level_is_disabled(caplog):
    log = logging.getLogger("tests.timed")
    with caplog.at_level(logging.INFO, logger="tests.timed"):
        with timed(log, "quiet step", logging.DEBUG):
            pass
    assert not caplog.records
