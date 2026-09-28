"""Coverage snapshot persistence (issue #45): a point-in-time rollup captured on
meaningful events, so a future trend UI has real history to chart instead of only
ever knowing "right now". This is the storage/persistence half only — the
Dashboard trend charts and "since last release" comparison view are separate,
later work per the issue's own suggested split.

Deliberately its own mixin file (not store/dashboard.py): dashboard.py computes
the CURRENT rollup live on every request; this module PERSISTS that rollup at a
point in time and retrieves the history — a different concern ("snapshot, don't
recompute", per the issue's own design note).
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

# The completion events worth snapshotting (issue #45's list). A snapshot
# records WHICH of these triggered it, so a future trend chart can filter/label
# by source rather than showing one undifferentiated line.
SNAPSHOT_EVENTS = {"generation", "code_analysis", "mindmap", "cycle_completion"}

# Retention: keep at most this many snapshots per project — a simple, predictable
# rolling-window bound on growth rather than an unbounded collection or a
# separately scheduled sweep job.
SNAPSHOT_RETENTION_PER_PROJECT = 500

# A retry of the same completion event (e.g. a job retry, or a second cycle item
# correction moments after the first) within this window is treated as the same
# data point, not a second one — avoids a burst of near-identical snapshots
# muddying the trend line without losing genuinely separate events.
SNAPSHOT_DEDUP_WINDOW_SECONDS = 60


class CoverageSnapshotsMixin(_Base):
    """No __init__: shares the collection attributes/state that store/base.py's
    BaseStore.__init__ sets up (composed last in store/__init__.py's Store MRO)."""

    def save_coverage_snapshot(self, project_id, event, commit_sha=None, job_id=None):
        """Persist a point-in-time coverage rollup for `project_id`, triggered by
        `event` (must be one of SNAPSHOT_EVENTS). Returns the new snapshot's id,
        or the id of the existing snapshot it deduplicated against.

        Returns None (does nothing) for an unrecognized event, a missing
        project_id, or a project with no dashboard rollup entry (e.g. it was
        deleted mid-job) — this must never break the job that triggers it, so it
        never raises for a "nothing to snapshot" situation.
        """
        if not project_id or event not in SNAPSHOT_EVENTS:
            return None
        rollup = next((p for p in self.dashboard().get("projects", [])
                      if p.get("id") == project_id), None)
        if rollup is None:
            return None

        now = time.time()
        dup = self.db["coverage_snapshots"].find_one(
            {"project_id": project_id, "event": event,
             "at": {"$gte": now - SNAPSHOT_DEDUP_WINDOW_SECONDS}},
            sort=[("at", -1)],
        )
        if dup:
            return str(dup["_id"])

        doc = {
            "project_id": project_id,
            "event": event,
            "at": now,
            "commit_sha": commit_sha or None,
            "job_id": job_id or None,
            "coverage_pct": rollup.get("code_pct", 0),
            "automation_pct": rollup.get("automation_pct", 0),
            "case_count": rollup.get("test_cases", 0),
        }
        sid = str(self.db["coverage_snapshots"].insert_one(doc).inserted_id)
        self._prune_coverage_snapshots(project_id)
        return sid

    def _prune_coverage_snapshots(self, project_id):
        """Keep at most SNAPSHOT_RETENTION_PER_PROJECT snapshots for `project_id`
        — a rolling window instead of unbounded growth."""
        stale_ids = [d["_id"] for d in self.db["coverage_snapshots"].find(
            {"project_id": project_id}, {"_id": 1}
        ).sort("at", -1).skip(SNAPSHOT_RETENTION_PER_PROJECT)]
        if stale_ids:
            self.db["coverage_snapshots"].delete_many({"_id": {"$in": stale_ids}})

    def list_coverage_snapshots(self, project_id, limit=200):
        """Snapshots for `project_id`, oldest first — the shape a trend chart
        wants to plot directly."""
        docs = list(self.db["coverage_snapshots"].find(
            {"project_id": project_id}
        ).sort("at", -1).limit(limit))
        docs.reverse()
        for d in docs:
            d["id"] = str(d.pop("_id"))
        return docs
