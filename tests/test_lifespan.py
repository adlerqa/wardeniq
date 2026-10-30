"""Lifespan regression tests (issue #198).

The two startup handlers used to be `@app.on_event("startup")` (deprecated
in FastAPI); they now run from `main.lifespan`. These tests pin that:
entering the app's lifespan starts exactly the same four background
callables, and no `on_event` startup handler remains registered.

`test_lifespan_starts_all_background_callables` is a behavior-parity check
(it passes on the old code too, since TestClient's context manager also
runs `on_event` handlers); `test_no_on_event_startup_handlers_remain` is
the discriminator — it fails pre-fix and passes post-fix.
"""

import main
from fastapi.testclient import TestClient


def test_lifespan_starts_all_background_callables(monkeypatch):
    calls = []
    monkeypatch.setattr(main, "bootstrap", lambda: calls.append("bootstrap"))
    monkeypatch.setattr(main, "_stale_job_sweeper",
                        lambda: calls.append("stale_job_sweeper"))
    monkeypatch.setattr(main, "_import_reanalysis_scheduler",
                        lambda: calls.append("import_reanalysis_scheduler"))
    monkeypatch.setattr(main, "poller", lambda: calls.append("poller"))
    with TestClient(main.app):
        pass
    # Thread-start order is sequential in code (bootstrap, sweeper,
    # scheduler, then poller); thread scheduling is not, so compare as a set.
    assert sorted(calls) == sorted(["bootstrap", "stale_job_sweeper",
                                    "import_reanalysis_scheduler", "poller"])


def test_no_on_event_startup_handlers_remain():
    assert main.app.router.on_startup == []
    assert main.app.router.lifespan_context is not None
