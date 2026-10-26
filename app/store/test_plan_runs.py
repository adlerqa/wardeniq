"""Generated test-plan run bookkeeping (create/update/fetch, staleness marking).

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


class TestPlanRunsMixin(_Base):
    """No __init__: shares the collection attributes/state that store/base.py's
    BaseStore.__init__ sets up (composed last in store/__init__.py's Store MRO)."""

    def create_test_plan_run(self, feature_id, version_number, created_by=None):
        now = time.time()
        # Find highest run_number for this feature_id
        highest = self.test_plan_runs.find_one({"feature_id": feature_id}, sort=[("run_number", -1)])
        run_number = (highest.get("run_number", 0) + 1) if highest else 1
        
        doc = {
            "feature_id": feature_id,
            "version_number": version_number,
            "run_number": run_number,
            "status": "PROCESSING",
            "source": "ai_generated",
            "content": None,
            "created_by": created_by,
            "created_at": now,
            "updated_at": now
        }
        res = self.test_plan_runs.insert_one(doc)
        return str(res.inserted_id), run_number

    def update_test_plan_run(self, run_id, status, content=None, error=None):
        fields = {"status": status, "updated_at": time.time()}
        if content is not None:
            fields["content"] = content
        if error is not None:
            fields["error"] = error
        self.test_plan_runs.update_one({"_id": ObjectId(run_id)}, {"$set": fields})

    def get_test_plan_run(self, run_id):
        p = self.test_plan_runs.find_one({"_id": ObjectId(run_id)})
        if p:
            p["id"] = str(p.pop("_id"))
        return p

    def get_latest_test_plan_run(self, feature_id):
        p = self.test_plan_runs.find_one({"feature_id": feature_id}, sort=[("run_number", -1)])
        if p:
            p["id"] = str(p.pop("_id"))
        return p

    def mark_feature_test_plans_stale(self, feature_id):
        """Flag a feature's test-plan runs as out of date (e.g. after an import
        changed its test cases), so consumers know the plan should be regenerated.
        Returns the number of runs flagged."""
        res = self.test_plan_runs.update_many(
            {"feature_id": feature_id},
            {"$set": {"stale": True, "stale_at": time.time()}})
        return getattr(res, "modified_count", 0)
