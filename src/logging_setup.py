"""Logging for the whole project: one place that decides *where* log lines go and *how much* is shown.

Why this module exists
----------------------
A pantry goes through several packages before it becomes a plan (``nlp`` -> ``domain`` -> ``optimizer`` -> ``explain``
-> ``app``), and some steps degrade quietly by design: an unreachable LLM means "rules only", a rejected paraphrase
means "template text", a solver time limit means "a good plan, not a proven one". The returned objects record those
outcomes, but to *follow the flow* while developing you want one timeline of what ran, in which order, how long it
took and where it fell back. That is what the log is.

The split of responsibilities (the standard library's own convention)
--------------------------------------------------------------------
* **Library modules only emit.** Each one does ``logger = logging.getLogger(__name__)`` and calls ``logger.debug`` /
  ``info`` / ``warning``. They never add handlers or set levels, so importing them (in a test, a notebook, the
  benchmark) never changes anyone's output.
* **Entry points configure, once.** The Streamlit app and the evaluation CLIs call :func:`configure_logging` at
  start-up. Nothing else does.

Without :func:`configure_logging` (e.g. under pytest) Python still prints WARNING and above to stderr, and pytest's
``caplog`` sees every record - which is how the log calls are tested.

Level policy (what each level is for in this project)
-----------------------------------------------------
``DEBUG``    detail inside a step: each parsed fragment, model size, each LLM request, each table read.
``INFO``     one line per step the user would recognise: pantry reviewed, plan ready, re-planned, dataset loaded.
``WARNING``  a degradation the user gets: LLM failed so the rules result was kept, the solver found no plan.
``ERROR``    reserved for failures that are caught and survived; anything else propagates as an exception.

Privacy: the pantry text a user types is logged at DEBUG only, and API keys are never logged.

Configuration
-------------
``PTP_LOG_LEVEL`` (default ``INFO``) and ``PTP_LOG_FILE`` (default: none, stderr only), or the arguments of
:func:`configure_logging`. Example: ``PTP_LOG_LEVEL=DEBUG streamlit run src/ui/streamlit_app.py``.
"""
from __future__ import annotations

import logging
import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

ENV_LOG_LEVEL = "PTP_LOG_LEVEL"
ENV_LOG_FILE = "PTP_LOG_FILE"
DEFAULT_LEVEL = "INFO"          # one line per step; DEBUG is for chasing a specific problem

# time, level, which module, message. The module name is the "where in the pipeline" (nlp.pantry_parser, ...).
LOG_FORMAT = "%(asctime)s.%(msecs)03d %(levelname)-7s %(name)s: %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Third-party loggers that are chatty at INFO/DEBUG (httpx logs every request line; Streamlit's file watcher logs
# every poll; numexpr, loaded by pandas, announces its thread count). They are capped at WARNING so DEBUG shows *our*
# flow, not theirs.
QUIET_LOGGERS = ("httpx", "httpcore", "urllib3", "watchdog", "fsevents", "PIL", "matplotlib", "asyncio", "numexpr")

# Marks the handlers this module installed, so a second call replaces them instead of duplicating every line.
# (Streamlit re-executes the app script on every interaction, so configure_logging runs many times per process.)
_HANDLER_TAG = "_ptp_handler"


def _parse_level(level: str | int) -> int:
    """``"debug"`` / ``"INFO"`` / ``10`` -> a logging level number. Raises ``ValueError`` for anything else."""
    if isinstance(level, int):
        return level
    value = logging.getLevelName(level.strip().upper())
    if not isinstance(value, int):
        raise ValueError(f"unknown log level {level!r}; expected DEBUG, INFO, WARNING or ERROR")
    return value


def configure_logging(level: str | int | None = None, log_file: str | Path | None = None,
                      environ: dict[str, str] | None = None) -> int:
    """Send the project's log records to stderr (and optionally a file). Safe to call any number of times.

    Args:
        level: minimum level shown. ``None`` reads ``PTP_LOG_LEVEL``, else ``INFO``.
        log_file: also append to this file (parent folders are created). ``None`` reads ``PTP_LOG_FILE``; an
            empty value means stderr only.
        environ: the environment to read (tests pass a dict); defaults to ``os.environ``.

    Returns:
        The level number that was applied.

    Raises:
        ValueError: ``level`` (or ``PTP_LOG_LEVEL``) is not a known level name.
    """
    env = os.environ if environ is None else environ
    applied = _parse_level(level if level is not None else env.get(ENV_LOG_LEVEL) or DEFAULT_LEVEL)
    file_path = log_file if log_file is not None else env.get(ENV_LOG_FILE) or None

    root = logging.getLogger()
    for handler in [h for h in root.handlers if getattr(h, _HANDLER_TAG, False)]:
        root.removeHandler(handler)
        handler.close()

    formatter = logging.Formatter(LOG_FORMAT, DATE_FORMAT)
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if file_path:
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(path, encoding="utf-8"))
    for handler in handlers:
        handler.setFormatter(formatter)
        setattr(handler, _HANDLER_TAG, True)
        root.addHandler(handler)

    # The level lives on the root logger (not the handlers) so that pytest's caplog and any other handler see the
    # same records ours do.
    root.setLevel(applied)
    for name in QUIET_LOGGERS:
        logging.getLogger(name).setLevel(max(applied, logging.WARNING))
    return applied


@contextmanager
def timed(logger: logging.Logger, what: str, level: int = logging.DEBUG) -> Iterator[None]:
    """Log ``"<what> took N ms"`` when the block finishes, at ``level``.

    Use it around a step whose duration is worth knowing (a table read, a solve, an LLM call). If the block raises,
    the line says ``"<what> failed after N ms"`` and the exception propagates unchanged; logging it is the caller's job.
    The clock is not read at all when ``level`` is disabled, so a ``timed`` DEBUG block costs nothing at INFO.
    """
    if not logger.isEnabledFor(level):
        yield
        return
    started = time.perf_counter()
    try:
        yield
    except BaseException:
        logger.log(level, "%s failed after %.0f ms", what, 1000 * (time.perf_counter() - started))
        raise
    logger.log(level, "%s took %.0f ms", what, 1000 * (time.perf_counter() - started))
