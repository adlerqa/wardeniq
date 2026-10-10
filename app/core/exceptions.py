"""Global exception handlers.

Moved out of main.py (Phase 2 of docs/internal/REFACTOR_PLAN.md). Registration itself
(`app.exception_handler(_InvalidId)(...)`) stays in main.py — it needs the
`app` instance — but the handler function and the exception class it's keyed
on live here.
"""
from bson.errors import InvalidId as _InvalidId
from fastapi import Request
from fastapi.responses import JSONResponse


async def invalid_id_handler(request: Request, exc: _InvalidId):  # noqa: ARG001
    """A malformed Mongo id (wrong length/format) reaches ObjectId() from many
    path params and request bodies across the codebase. Without a handler,
    bson raises InvalidId, which surfaces as a confusing HTTP 500. Convert it
    to a clean 400 in one place instead of guarding ~100 individual call sites."""
    return JSONResponse({"detail": "invalid id format"}, status_code=400)


class MigrationInProgress(Exception):
    """Raised by launch_job()/run_tracked() (workers/registry.py) while a database
    migration is running (issue #111: no new background work may start mid-copy).
    Many routes call those two functions, so -- like _InvalidId above -- it is turned
    into a clean 409 here in one place rather than at every call site. Non-HTTP
    callers (pollers, webhook threads) catch it themselves."""


class MigrationBlocked(MigrationInProgress):
    """A migration may not START right now: another migration is already running, or
    something else is running and the caller did not accept a best-effort snapshot
    (workers/registry.py's migration_blocker()). Subclasses MigrationInProgress so the
    same global handler turns it into a 409 for every launch path."""


MIGRATION_IN_PROGRESS_MSG = ("a database migration is in progress -- try again once it "
                             "finishes")


async def migration_in_progress_handler(request: Request, exc: MigrationInProgress):  # noqa: ARG001
    return JSONResponse({"detail": str(exc) or MIGRATION_IN_PROGRESS_MSG}, status_code=409)
