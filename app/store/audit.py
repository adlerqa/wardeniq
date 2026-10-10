"""Audit log: the `audit` collection accessor plus add/list.

Moved out of store.py (Phase 5 of docs/internal/REFACTOR_PLAN.md).
"""

import time


from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # mypy-only: gives this mixin visibility into the collection attributes and
    # cross-mixin helpers that store/__init__.py's Store actually composes in at
    # runtime (BaseStore.__init__ sets self.projects/self.cases/etc; other mixins
    # add their own methods). At runtime this mixin still inherits only `object`
    # (see the `else` branch) — Store's own MRO (store/__init__.py) is what really
    # provides these at runtime, unchanged from before this TYPE_CHECKING addition.
    from store.base import BaseStore as _Base
else:
    _Base = object


class AuditMixin(_Base):
    """No __init__: shares the collection attributes/state that store/base.py's
    BaseStore.__init__ sets up (composed last in store/__init__.py's Store MRO)."""

    @property
    def audit(self):
        return self.db["audit_logs"]

    def add_audit(self, action, actor=None, target=None, old=None, new=None,
                  ip=None, user_agent=None, detail=None):
        """Append an immutable audit entry. Best-effort: never let logging failures
        break the underlying action (callers wrap in try/except)."""
        doc = {"action": action, "ts": time.time(),
               "actor_id": (actor or {}).get("id") if isinstance(actor, dict) else actor,
               "actor_email": (actor or {}).get("email") if isinstance(actor, dict) else None,
               "target": target, "old": old, "new": new,
               "ip": ip, "user_agent": user_agent, "detail": detail}
        self.audit.insert_one(doc)
        return True

    def list_audit(self, limit=100, action=None, actor_email=None):
        q = {}
        if action:
            q["action"] = action
        if actor_email:
            q["actor_email"] = actor_email
        out = []
        for d in self.audit.find(q).sort("ts", -1).limit(int(limit)):
            d["id"] = str(d.pop("_id"))
            out.append(d)
        return out
