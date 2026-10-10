"""Serve the built React SPA: mount the compiled ``static-react/assets``
directory, and serve ``index.html``/``favicon.ico``/``logo2.png``/the
``/invite`` landing page (client-side routing is hash-based, so no path
catch-all is needed).

Extracted from app/main.py (docs/internal/REFACTOR_PLAN.md section 14, Phase 6, router
20/20 — LAST). Handler bodies are unchanged aside from the ``@app.`` ->
``@router.`` decorator swap.

Per docs/internal/REFACTOR_PLAN.md section 7/14, this router must be included **last** in
main.py's ``app.include_router(...)`` sequence, exactly where the equivalent
code sat at the end of the original main.py.

DISCOVERED DEVIATION (repo behavior vs. the plan's implied mechanical
``@app.`` -> ``@router.`` swap): the ``/assets`` StaticFiles mount cannot be
a module-level ``router.mount(...)`` call, because FastAPI's
``APIRouter.include_router()`` only copies ``APIRoute``/``Route``/
``APIWebSocketRoute``/``WebSocketRoute`` instances out of the included
router's ``.routes`` — a ``starlette.routing.Mount`` added via
``router.mount(...)`` is silently dropped and never reaches the real app.
(Verified directly: ``len(app.routes)`` after ``include_router`` was missing
the mount entirely.) So the mount is exposed here as ``mount_assets(app)``,
which main.py calls directly on the real ``FastAPI`` instance right after
``app.include_router(_static_spa_routes.router)`` — this is the only route
in the whole Phase-6 extraction that isn't a pure decorator swap, and it's
required for the asset mount to actually function at all.
"""
from fastapi import APIRouter
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

router = APIRouter()


def mount_assets(app):
    """Mount the compiled `static-react/assets` directory onto `app`.

    Must be called directly on the real FastAPI `app` instance (not on this
    module's `router`) — see the module docstring for why."""
    # Serve the built React SPA. `frontend/` is compiled to `static-react/` at image
    # build time (see app/Dockerfile) — hashed JS/CSS live under static-react/assets.
    app.mount("/assets", StaticFiles(directory="static-react/assets", check_dir=False), name="assets")


@router.get("/")
def index():
    return FileResponse("static-react/index.html")


@router.get("/favicon.ico")
@router.get("/logo2.png")
def favicon():
    return FileResponse("static-react/logo2.png")


@router.get("/invite")
def invite_landing():
    # Serve the SPA for invitation links (/invite?token=…). The frontend reads the
    # token and drives the verify → login → accept/decline flow. Client routing is
    # hash-based (#dashboard, …), so no path catch-all is needed.
    return FileResponse("static-react/index.html")
