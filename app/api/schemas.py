"""Pydantic models shared by 2+ routers.

Per docs/internal/REFACTOR_PLAN.md section 14 step 1: "anything shared by two routers goes to
api/schemas.py or core/deps.py — never duplicated" and "avoids router-to-router
imports, which would create a cycle." A model used by exactly one router stays
defined in that router's own file; it only moves here once a second caller needs it.
"""
from pydantic import BaseModel


# {email: str} — used by api/routes/auth.py's request_otp AND (until settings.py
# is extracted in a later Phase 6 commit) main.py's /api/smtp/test handler, which
# reuses this exact shape rather than defining its own.
#
# NOTE: this is a plain comment, not a class docstring — pydantic promotes a
# docstring to the generated OpenAPI schema's `description` field, which would
# change the public API contract from what main.py's original inline model
# exposed (no description). Keeping it a comment preserves byte-identical
# openapi.json output.
class OtpRequestIn(BaseModel):
    email: str
