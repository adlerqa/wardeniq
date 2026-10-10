"""Stored-document CRUD (uploaded reference docs, not feature source text).

Moved out of store.py (Phase 5 of docs/internal/REFACTOR_PLAN.md).
"""

import time

from bson import ObjectId


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


class DocumentsMixin(_Base):
    """No __init__: shares the collection attributes/state that store/base.py's
    BaseStore.__init__ sets up (composed last in store/__init__.py's Store MRO)."""

    def save_stored_document(self, doc_data: dict) -> str:
        doc = dict(doc_data)
        if "created_at" not in doc:
            doc["created_at"] = time.time()
        res = self.documents.insert_one(doc)
        return str(res.inserted_id)

    def get_stored_document(self, doc_id: str) -> dict | None:
        try:
            d = self.documents.find_one({"_id": ObjectId(doc_id)})
            if d:
                d["id"] = str(d.pop("_id"))
            return d
        except Exception:
            return None

    def list_stored_documents(self, project_id: str = None, feature_id: str = None, limit: int = 100) -> list[dict]:
        query = {}
        if project_id:
            query["project_id"] = project_id
        if feature_id:
            query["feature_id"] = feature_id
        out = []
        for d in self.documents.find(query).sort("created_at", -1).limit(limit):
            d["id"] = str(d.pop("_id"))
            out.append(d)
        return out

    def delete_stored_document(self, doc_id: str) -> bool:
        try:
            res = self.documents.delete_one({"_id": ObjectId(doc_id)})
            return getattr(res, "deleted_count", 0) > 0
        except Exception:
            return False
