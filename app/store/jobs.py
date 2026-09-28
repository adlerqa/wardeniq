"""Background job bookkeeping: create/update/progress/result, listing, and the
orphaned/stale sweeps used by background/schedulers.py.

Moved out of store.py (Phase 5 of REFACTOR_PLAN.md).
"""

import time

from bson import ObjectId

from core.logging_setup import get_logger

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

log = get_logger("jobs")


class JobsMixin(_Base):
    """No __init__: shares the collection attributes/state that store/base.py's
    BaseStore.__init__ sets up (composed last in store/__init__.py's Store MRO)."""

    def create_job(self, jtype, params, label="", project_id=None, feature_id=None):
        return str(self.db["jobs"].insert_one({
            "type": jtype, "label": label, "status": "running", "stage": "starting",
            "progress": 0, "logs": [{"stage": "starting", "progress": 0, "at": time.time()}],
            "params": params, "result": {}, "error": None,
            "project_id": project_id, "feature_id": feature_id,
            "created_at": time.time(), "updated_at": time.time()}).inserted_id)

    def update_job(self, jid, **fields):
        fields["updated_at"] = time.time()
        self.db["jobs"].update_one({"_id": ObjectId(jid)}, {"$set": fields})
        stage = fields.get("stage")
        status = fields.get("status")
        progress = fields.get("progress")
        error = fields.get("error")
        parts = [f"job={jid}"]
        if status:
            parts.append(f"status={status}")
        if stage:
            parts.append(f"stage='{stage}'")
        if progress is not None:
            parts.append(f"progress={progress}%")
        if error:
            parts.append(f"error='{error}'")
        if len(parts) > 1:
            (log.error if error else log.info)(" ".join(parts))

    def update_job_progress(self, jid, stage, progress=None):
        now = time.time()
        fields = {"stage": stage, "updated_at": now}
        if progress is not None:
            fields["progress"] = max(0, min(100, int(progress)))
        self.db["jobs"].update_one(
            {"_id": ObjectId(jid)},
            {
                "$set": fields,
                "$push": {
                    "logs": {
                        "$each": [{"stage": stage, "progress": fields.get("progress"), "at": now}],
                        "$slice": -80,
                    }
                },
            },
        )
        prog_str = f" ({fields['progress']}%). Log saved." if progress is not None else ""
        log.info("job=%s %s%s", jid, stage, prog_str)

    def merge_job_result(self, jid, **fields):
        upd = {f"result.{k}": v for k, v in fields.items()}
        upd["updated_at"] = time.time()
        self.db["jobs"].update_one({"_id": ObjectId(jid)}, {"$set": upd})

    def get_job(self, jid):
        j = self.db["jobs"].find_one({"_id": ObjectId(jid)})
        if j:
            j["id"] = str(j.pop("_id"))
        return j

    def list_jobs(self, limit=60, status=None, jtype=None):
        q = {}
        if status:
            q["status"] = status
        if jtype:
            q["type"] = jtype
        out = []
        for j in self.db["jobs"].find(q, {"params": 0}).sort("_id", -1).limit(limit):
            j["id"] = str(j.pop("_id"))
            out.append(j)
        return out

    def fail_orphaned_jobs(self):
        """Background threads do not survive an application process restart."""
        now = time.time()
        orphaned = list(self.db["jobs"].find({"status": "running"}, {"_id": 1, "stage": 1}))
        for job in orphaned:
            stage = job.get("stage") or "unknown"
            message = (
                "Generation worker stopped because the application restarted while "
                f"the job was at: {stage}. Retry the job to continue."
            )
            self.db["jobs"].update_one(
                {"_id": job["_id"], "status": "running"},
                {
                    "$set": {
                        "status": "failed",
                        "stage": "interrupted by application restart",
                        "error": message,
                        "updated_at": now,
                    },
                    "$push": {
                        "logs": {
                            "$each": [{
                                "stage": "interrupted by application restart",
                                "progress": None,
                                "at": now,
                            }],
                            "$slice": -80,
                        }
                    },
                },
            )
        if orphaned:
            log.warning("Marked %d orphaned running job(s) as failed.", len(orphaned))
        return len(orphaned)

    def sweep_stale_jobs(self, ttl_seconds=600):
        """Fail any 'running' job whose heartbeat (`updated_at`) is older than
        ttl_seconds. Workers call update_job_progress() regularly, so a stale
        updated_at means the worker thread is dead or hung. Runs on a timer,
        not just at startup, so live-process hangs also recover and the UI
        stops spinning forever.
        """
        now = time.time()
        cutoff = now - ttl_seconds
        stale = list(self.db["jobs"].find(
            {"status": "running", "updated_at": {"$lt": cutoff}},
            {"_id": 1, "stage": 1, "updated_at": 1}))
        for job in stale:
            stage = job.get("stage") or "unknown"
            idle = int(now - float(job.get("updated_at") or now))
            message = (
                f"Worker heartbeat lost — no progress for {idle}s while at: "
                f"{stage}. Marked failed by the stale-job sweeper. Retry to continue."
            )
            self.db["jobs"].update_one(
                {"_id": job["_id"], "status": "running"},
                {
                    "$set": {
                        "status": "failed",
                        "stage": "stalled",
                        "error": message,
                        "updated_at": now,
                    },
                    "$push": {
                        "logs": {
                            "$each": [{
                                "stage": "stalled — worker heartbeat lost",
                                "progress": None,
                                "at": now,
                            }],
                            "$slice": -80,
                        }
                    },
                },
            )
        if stale:
            log.warning("Swept %d stalled running job(s).", len(stale))
        return len(stale)
