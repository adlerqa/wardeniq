"""Structured logging setup (issue #17).

Replaces bare `print()` diagnostics across app/ with the stdlib `logging`
package, so verbosity is controllable (`LOG_LEVEL`, default INFO) and every
line carries a level, a timestamp and a logger name instead of landing on
stdout undifferentiated.

Usage, from any module:

    from core.logging_setup import get_logger
    log = get_logger("validator")   # -> logger "wardeniq.validator"
    log.info("stage complete")

`get_logger()` lazily calls `configure_logging()` on first use, so there is no
import-order dependency on main.py or anywhere else — the first module that
asks for a logger configures the shared "wardeniq" root logger once.

Logger names are deliberately the same short area names the old bracket
prefixes used (`[Validator]` -> "validator", `[TestGen]` -> "testgen", etc.),
namespaced under "wardeniq." — `docker logs warden-app | grep wardeniq.validator`
finds the same lines `grep '\\[Validator\\]'` used to.
"""
import logging
import os

_ROOT_NAME = "wardeniq"
_configured = False


def configure_logging():
    """Idempotent: attaches exactly one handler to the "wardeniq" logger, ever."""
    global _configured
    if _configured:
        return
    level_name = (os.getenv("LOG_LEVEL") or "INFO").strip().upper()
    level = getattr(logging, level_name, None)
    if not isinstance(level, int):
        level = logging.INFO

    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(
        fmt="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))

    root = logging.getLogger(_ROOT_NAME)
    root.setLevel(level)
    root.addHandler(handler)
    # Don't also hand records to the interpreter's default root logger — this
    # package owns its own handler, so double logging would duplicate every line.
    root.propagate = False
    _configured = True


def get_logger(area: str) -> logging.Logger:
    """area is a short, stable name, e.g. "validator", "testgen", "bootstrap"."""
    configure_logging()
    return logging.getLogger(f"{_ROOT_NAME}.{area}")
