"""Global exception handlers.

Moved out of main.py (Phase 2 of REFACTOR_PLAN.md). Registration itself
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
    """Raised by launch_job()/run_tracked() (workers/registry.py) — #111's
    "prevent new processing from starting" requirement — when a database
    migration job is currently running. Same one-place-not-every-call-site
    approach as _InvalidId above: dozens of routes call launch_job/run_tracked,
    so converting this to a clean 409 here (rather than a raise HTTPException
    at each call site) is what keeps this a one-file change."""


async def migration_in_progress_handler(request: Request, exc: MigrationInProgress):  # noqa: ARG001
    return JSONResponse(
        {"detail": str(exc) or "a database migration is in progress — try again once it finishes"},
        status_code=409,
    )
