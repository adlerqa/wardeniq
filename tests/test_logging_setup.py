"""Structured logging setup (issue #17).

Deliberately does NOT assert on exact log message text/formatting — only on the
structural contract: LOG_LEVEL is honoured, configuration is idempotent (no
duplicate handlers, no duplicate lines), logger names are namespaced under
"wardeniq.", and nothing crashes on an unrecognized LOG_LEVEL value. Message
wording is free to change without breaking this suite.
"""
import logging

import pytest

from core import logging_setup


@pytest.fixture(autouse=True)
def _reset_logging_state(monkeypatch):
    """Every test gets a clean, unconfigured "wardeniq" logger to configure itself,
    and the real state is restored afterward so other test files see it configured
    exactly once, the way a real process would."""
    root = logging.getLogger("wardeniq")
    saved_handlers = list(root.handlers)
    saved_level = root.level
    saved_propagate = root.propagate
    saved_configured = logging_setup._configured

    root.handlers.clear()
    logging_setup._configured = False

    try:
        yield
    finally:
        monkeypatch.undo()
        root.handlers.clear()
        root.handlers.extend(saved_handlers)
        root.setLevel(saved_level)
        root.propagate = saved_propagate
        logging_setup._configured = saved_configured


class TestConfigureLogging:
    def test_default_level_is_info(self, monkeypatch):
        monkeypatch.delenv("LOG_LEVEL", raising=False)
        logging_setup.configure_logging()
        assert logging.getLogger("wardeniq").level == logging.INFO

    def test_log_level_env_var_is_honoured(self, monkeypatch):
        monkeypatch.setenv("LOG_LEVEL", "DEBUG")
        logging_setup.configure_logging()
        assert logging.getLogger("wardeniq").level == logging.DEBUG

    def test_log_level_is_case_insensitive(self, monkeypatch):
        monkeypatch.setenv("LOG_LEVEL", "warning")
        logging_setup.configure_logging()
        assert logging.getLogger("wardeniq").level == logging.WARNING

    def test_unrecognized_log_level_falls_back_to_info(self, monkeypatch):
        monkeypatch.setenv("LOG_LEVEL", "NOT_A_REAL_LEVEL")
        logging_setup.configure_logging()
        assert logging.getLogger("wardeniq").level == logging.INFO

    def test_configure_is_idempotent_no_duplicate_handlers(self, monkeypatch):
        monkeypatch.delenv("LOG_LEVEL", raising=False)
        logging_setup.configure_logging()
        logging_setup.configure_logging()
        logging_setup.configure_logging()
        assert len(logging.getLogger("wardeniq").handlers) == 1

    def test_root_logger_does_not_propagate(self, monkeypatch):
        # Prevents every line from also being handled (and possibly duplicated)
        # by the interpreter's default root logger.
        monkeypatch.delenv("LOG_LEVEL", raising=False)
        logging_setup.configure_logging()
        assert logging.getLogger("wardeniq").propagate is False


class TestGetLogger:
    def test_returns_a_namespaced_logger(self, monkeypatch):
        monkeypatch.delenv("LOG_LEVEL", raising=False)
        log = logging_setup.get_logger("validator")
        assert log.name == "wardeniq.validator"

    def test_get_logger_triggers_configuration(self, monkeypatch):
        monkeypatch.delenv("LOG_LEVEL", raising=False)
        assert not logging.getLogger("wardeniq").handlers
        logging_setup.get_logger("testgen")
        assert len(logging.getLogger("wardeniq").handlers) == 1

    def test_repeated_calls_return_the_same_underlying_logger(self, monkeypatch):
        monkeypatch.delenv("LOG_LEVEL", raising=False)
        a = logging_setup.get_logger("bootstrap")
        b = logging_setup.get_logger("bootstrap")
        assert a is b

    def test_child_logger_inherits_the_configured_level(self, monkeypatch):
        monkeypatch.setenv("LOG_LEVEL", "ERROR")
        log = logging_setup.get_logger("jobs")
        assert log.getEffectiveLevel() == logging.ERROR


class TestNoRemainingDiagnosticPrints:
    """Regression guard for #17's acceptance criterion: no bare print() left in
    app/ for diagnostic output. The three intentional CLI utilities (meant to be
    run directly by a human and read from their own stdout) are exempted."""

    _EXEMPT = {
        "reset_password.py",
        "test_password_reset.py",
        "test_validator_gen.py",
        # Only mentions print() in its own docstring, explaining what it replaces.
        "logging_setup.py",
    }

    def test_no_print_calls_outside_exempt_cli_scripts(self):
        import pathlib
        app_root = pathlib.Path(__file__).resolve().parent.parent / "app"
        offenders = []
        for path in app_root.rglob("*.py"):
            if path.name in self._EXEMPT:
                continue
            if "print(" in path.read_text(encoding="utf-8"):
                offenders.append(str(path.relative_to(app_root)))
        assert offenders == []
