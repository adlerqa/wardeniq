"""Per-job token/cost usage: attaching a usage summary to a job record, and
aggregating it project/model-wide for the usage dashboard.

Moved out of store.py (Phase 5 of docs/internal/REFACTOR_PLAN.md) as its own domain file per
docs/internal/REFACTOR_PLAN.md section 13's file list, separate from jobs.py even though both
read/write the `jobs` collection.
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


class UsageMixin(_Base):
    """No __init__: shares the collection attributes/state that store/base.py's
    BaseStore.__init__ sets up (composed last in store/__init__.py's Store MRO)."""

    def set_job_usage(self, jid, usage):
        """Attach a per-process token/cost summary (from usage.summarize) to a job."""
        self.db["jobs"].update_one(
            {"_id": ObjectId(jid)},
            {"$set": {"usage": usage or {}, "updated_at": time.time()}})

    def usage_summary(self, project_id=None, prices=None, recent=40, scan=1000):
        """Aggregate token usage + cost across recent jobs: totals, per-model,
        per-project, and a list of recent processes (for the usage dashboard).

        Cost is recomputed live from stored token counts using the current price
        table, so editing prices in Settings updates historical costs too."""
        import usage as usage_mod
        price_map = {**usage_mod.DEFAULT_PRICES, **(prices or {})}

        def cost_of(model, pin, pout):
            p = usage_mod.price_for(model, price_map)
            if p is None:
                return None
            return (pin / 1e6) * float(p.get("in", 0)) + (pout / 1e6) * float(p.get("out", 0))

        q = {"usage.total_tokens": {"$gt": 0}}
        if project_id:
            q["project_id"] = project_id
        by_model, by_project = {}, {}
        totals = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "cost_usd": 0.0}
        any_cost = False
        recents = []
        pname = {}
        fname = {}
        for j in self.db["jobs"].find(q, {"params": 0}).sort("_id", -1).limit(scan):
            u = j.get("usage") or {}
            job_cost, job_has_cost = 0.0, False
            for model, d in (u.get("by_model") or {}).items():
                pin = int(d.get("prompt_tokens", 0) or 0)
                pout = int(d.get("completion_tokens", 0) or 0)
                c = cost_of(model, pin, pout)
                agg = by_model.setdefault(model, {
                    "calls": 0, "prompt_tokens": 0, "completion_tokens": 0,
                    "total_tokens": 0, "cost_usd": 0.0, "kind": d.get("kind", "llm"),
                    "has_cost": False})
                agg["calls"] += int(d.get("calls", 0) or 0)
                agg["prompt_tokens"] += pin
                agg["completion_tokens"] += pout
                agg["total_tokens"] += pin + pout
                if c is not None:
                    agg["cost_usd"] += c
                    agg["has_cost"] = True
                    job_cost += c
                    job_has_cost = True
            for k in ("prompt_tokens", "completion_tokens", "total_tokens"):
                totals[k] += int(u.get(k, 0) or 0)
            if job_has_cost:
                totals["cost_usd"] += job_cost
                any_cost = True
            pid = j.get("project_id") or ""
            if pid and pid not in pname and ObjectId.is_valid(pid):
                p = self.projects.find_one({"_id": ObjectId(pid)}, {"name": 1})
                pname[pid] = (p or {}).get("name") or pid
            pj = by_project.setdefault(pid or "—", {
                "project_id": pid, "name": pname.get(pid, "Unassigned" if not pid else pid),
                "total_tokens": 0, "cost_usd": 0.0, "has_cost": False})
            pj["total_tokens"] += int(u.get("total_tokens", 0) or 0)
            if job_has_cost:
                pj["cost_usd"] += job_cost
                pj["has_cost"] = True
            if len(recents) < recent:
                fid = j.get("feature_id") or ""
                if fid and fid not in fname and ObjectId.is_valid(fid):
                    f = self.features.find_one({"_id": ObjectId(fid)}, {"name": 1})
                    fname[fid] = (f or {}).get("name") or ""
                recents.append({
                    "id": str(j["_id"]), "type": j.get("type"),
                    "label": j.get("label") or j.get("type"),
                    "status": j.get("status"), "created_at": j.get("created_at"),
                    "project_id": pid, "project_name": pname.get(pid, ""),
                    "feature_id": fid, "feature_name": fname.get(fid, ""),
                    "total_tokens": u.get("total_tokens", 0),
                    "prompt_tokens": u.get("prompt_tokens", 0),
                    "completion_tokens": u.get("completion_tokens", 0),
                    "cost_usd": round(job_cost, 6) if job_has_cost else None,
                    "by_model": u.get("by_model") or {},
                })
        totals["cost_usd"] = round(totals["cost_usd"], 4) if any_cost else None
        for m in by_model.values():
            m["cost_usd"] = round(m["cost_usd"], 6) if m.pop("has_cost") else None
        proj_list = sorted(by_project.values(), key=lambda x: x["total_tokens"], reverse=True)
        for p in proj_list:
            p["cost_usd"] = round(p["cost_usd"], 4) if p.pop("has_cost") else None
        return {"totals": totals, "by_model": by_model,
                "by_project": proj_list, "recent": recents}
