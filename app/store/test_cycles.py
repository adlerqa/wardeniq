"""Manual test-cycle execution: cycles, per-case cycle items, run reporting/CSV
export, and cycle templates.

Moved out of store.py (Phase 5 of REFACTOR_PLAN.md).
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


class TestCyclesMixin(_Base):
    """No __init__: shares the collection attributes/state that store/base.py's
    BaseStore.__init__ sets up (composed last in store/__init__.py's Store MRO)."""

    @staticmethod
    def _cycle_counts(items):
        counts = {key: 0 for key in ["pending", "passed", "failed", "skipped", "blocked"]}
        for item in items:
            status = str(item.get("execution_status") or item.get("status") or "pending").lower()
            counts[status] = counts.get(status, 0) + 1
        return counts

    def _cycle_activity(self, action, performed_by=None, item_id=None,
                        old_value=None, new_value=None):
        return {
            "id": str(ObjectId()), "action": action, "performed_by": performed_by,
            "item_id": item_id, "old_value": old_value, "new_value": new_value,
            "created_at": time.time(),
        }

    def _cycle_item_from_case(self, case_id, order):
        case = self.cases.find_one({"_id": ObjectId(case_id)}, {"embedding": 0})
        if not case:
            return None
        feature_id = case.get("source_feature_id")
        feature = (
            self.features.find_one({"_id": ObjectId(feature_id)}, {"name": 1, "version": 1})
            if feature_id and ObjectId.is_valid(feature_id) else None
        )
        return {
            "id": str(ObjectId()), "case_id": case_id, "testcase_id": case_id,
            "title": case.get("title"), "category": case.get("type") or "",
            "priority": case.get("priority") or "P2",
            "steps": [
                f"{step.get('action', '')} → {step.get('expected', '')}".strip(" →")
                for step in self.resolve_steps(case.get("step_ids", []))
            ],
            "feature_id": feature_id, "feature_name": (feature or {}).get("name", ""),
            "feature_version_number": (feature or {}).get("version"),
            "execution_status": "pending", "actual_result": "", "defect_link": "",
            "notes": "", "executed_by": None, "executed_at": None,
            "display_order": order, "created_at": time.time(), "updated_at": time.time(),
        }

    def create_cycle(self, project_id, name, case_ids, source=None, **meta):
        # A blank/whitespace-only name used to fall through to the frontend's
        # own client-side fallback (`Cycle ${date}`, one per calling site --
        # the plain "New cycle" button, "New cycle from selection", and
        # "New cycle from template" each had their own copy of it). That let a
        # cycle get created with no real name at all whenever a caller bypassed
        # or lacked that client-side default (e.g. a direct API call), and made
        # a second no-name click collide on the exact same date-only fallback
        # and surface a confusing "already exists" error instead of a plain
        # "name required" one. Reject it here instead, at the single place all
        # three creation paths funnel through (create_cycle_from_template()
        # delegates straight into this method too), rather than trusting every
        # caller to validate it client-side.
        name = (name or "").strip()
        if not name:
            raise ValueError("Cycle name is required")
        duplicate = self.db["test_cycles"].find_one({
            "project_id": project_id,
            "name_key": name.lower(),
        })
        if duplicate:
            raise ValueError("A test cycle with this name already exists in this project")
        items = []
        for index, case_id in enumerate(dict.fromkeys(case_ids), 1):
            item = self._cycle_item_from_case(case_id, index)
            if item:
                items.append(item)
        now = time.time()
        cid = self.db["test_cycles"].insert_one({
            "project_id": project_id, "name": name,
            "name_key": name.lower(), "description": meta.get("description", ""),
            "environment": meta.get("environment", ""), "build_version": meta.get("build_version", ""),
            "assigned_to": meta.get("assigned_to"), "scheduled_start_at": meta.get("scheduled_start_at"),
            "scheduled_end_at": meta.get("scheduled_end_at"), "actual_start_at": None,
            "actual_end_at": None, "status": "draft", "items": items,
            "source": source or {}, "activity": [self._cycle_activity("cycle_created", meta.get("created_by"))],
            "created_by": meta.get("created_by"), "created_at": now, "updated_at": now,
        }).inserted_id
        return str(cid)

    def list_cycles(self, project_id, status=None):
        query = {"project_id": project_id}
        if status:
            query["status"] = status
        out = []
        for c in self.db["test_cycles"].find(query).sort("_id", -1):
            items = c.get("items", [])
            counts = self._cycle_counts(items)
            out.append({"id": str(c["_id"]), "name": c.get("name"), "total": len(items),
                        "counts": counts, "status": c.get("status", "draft"),
                        "description": c.get("description", ""), "environment": c.get("environment", ""),
                        "build_version": c.get("build_version", ""), "source": c.get("source", {}),
                        "created_at": c.get("created_at"), "updated_at": c.get("updated_at")})
        return out

    def get_cycle(self, cycle_id):
        c = self.db["test_cycles"].find_one({"_id": ObjectId(cycle_id)})
        if not c:
            return None
        changed = False
        status_alias = {"pass": "passed", "fail": "failed"}
        for index, item in enumerate(c.get("items", []), 1):
            if not item.get("id"):
                item["id"] = str(ObjectId())
                changed = True
            raw_status = str(item.get("execution_status") or item.get("status") or "pending").lower()
            normalized_status = status_alias.get(raw_status, raw_status)
            if item.get("execution_status") != normalized_status:
                item["execution_status"] = normalized_status
                item["status"] = normalized_status
                changed = True
            # Refresh title/category/priority/steps from the LIVE case each read so edits to a
            # test case (or its shared steps) propagate into cycles that reference it.
            if item.get("case_id") and ObjectId.is_valid(item["case_id"]):
                case = self.cases.find_one({"_id": ObjectId(item["case_id"])}, {"embedding": 0})
                if case:
                    live = {
                        "title": case.get("title"), "category": case.get("type") or "",
                        "display_id": case.get("display_id") or "",
                        "priority": case.get("priority") or "P2",
                        "steps": [
                            f"{step.get('action', '')} → {step.get('expected', '')}".strip(" →")
                            for step in self.resolve_steps(case.get("step_ids", []))
                        ],
                    }
                    for key, value in live.items():
                        if item.get(key) != value:
                            item[key] = value
                            changed = True
            item.setdefault("display_order", index)
            item.setdefault("actual_result", "")
            item.setdefault("defect_link", "")
            item.setdefault("notes", "")
        if changed:
            self.db["test_cycles"].update_one(
                {"_id": c["_id"]},
                {"$set": {"items": c.get("items", []), "updated_at": time.time()}},
            )
        c["id"] = str(c.pop("_id"))
        c["counts"] = self._cycle_counts(c.get("items", []))
        c["total"] = len(c.get("items", []))
        return c

    def update_cycle(self, cycle_id, fields, performed_by=None):
        allowed = {
            "name", "description", "status", "environment", "build_version",
            "assigned_to", "scheduled_start_at", "scheduled_end_at",
        }
        update = {key: value for key, value in fields.items() if key in allowed}
        if "name" in update:
            update["name_key"] = str(update["name"]).strip().lower()
        update["updated_at"] = time.time()
        activity = self._cycle_activity("cycle_updated", performed_by)
        self.db["test_cycles"].update_one(
            {"_id": ObjectId(cycle_id)},
            {"$set": update, "$push": {"activity": activity}},
        )
        return self.get_cycle(cycle_id)

    def set_cycle_item_status(self, cycle_id, item_or_case_id, status, actual_result="",
                              defect_link="", notes="", executed_by=None):
        status = str(status).lower()
        if status not in {"pending", "passed", "failed", "skipped", "blocked"}:
            raise ValueError("Invalid cycle execution status")
        c = self.get_cycle(cycle_id)
        if not c:
            raise ValueError("Cycle not found")
        items = c.get("items", [])
        target = next(
            (item for item in items if item.get("id") == item_or_case_id or item.get("case_id") == item_or_case_id),
            None,
        )
        if not target:
            raise ValueError("Cycle item not found")
        old = target.get("execution_status", "pending")
        target.update({
            "execution_status": status, "status": status,
            "actual_result": actual_result, "defect_link": defect_link, "notes": notes,
            "executed_by": executed_by,
            "executed_at": time.time() if status != "pending" else None,
            "updated_at": time.time(),
        })
        counts = self._cycle_counts(items)
        terminal = counts["passed"] + counts["failed"] + counts["skipped"] + counts["blocked"]
        cycle_status = c.get("status", "draft")
        cycle_updates = {}
        if terminal == len(items) and items:
            cycle_status = "completed"
            cycle_updates["actual_end_at"] = time.time()
        elif cycle_status == "draft" and status != "pending":
            cycle_status = "active"
            cycle_updates["actual_start_at"] = time.time()
        cycle_updates.update({"items": items, "status": cycle_status, "updated_at": time.time()})
        self.db["test_cycles"].update_one(
            {"_id": ObjectId(cycle_id)},
            {
                "$set": cycle_updates,
                "$push": {"activity": self._cycle_activity(
                    "status_changed", executed_by, target["id"], old, status
                )},
            },
        )
        if cycle_status == "completed":
            # Coverage trend history (issue #45): a cycle reaching completion is
            # one of the events worth a point-in-time snapshot.
            try:
                self.save_coverage_snapshot(c.get("project_id"), "cycle_completion")
            except Exception as snap_e:  # noqa: BLE001
                print(f"[coverage-snapshot] skipped: {snap_e}", flush=True)
        return target

    def batch_cycle_item_status(self, cycle_id, item_ids, status, executed_by=None):
        for item_id in item_ids:
            self.set_cycle_item_status(cycle_id, item_id, status, executed_by=executed_by)
        return self.get_cycle(cycle_id)

    def add_cycle_items(self, cycle_id, case_ids, performed_by=None):
        c = self.get_cycle(cycle_id)
        if not c:
            raise ValueError("Cycle not found")
        existing = {item.get("case_id") for item in c.get("items", [])}
        items = c.get("items", [])
        # Case-insensitive, trimmed (feature_id, title) pairs already present in
        # this cycle -- mirrors create_cycle()'s own name-uniqueness check further
        # down this file. Without this, "Add Test Cases" -> "Create a new test
        # case" always succeeds even when the new case has the exact same
        # title/steps/expected-results as one already in this cycle for the same
        # feature: create_test_case() has no notion of "cycle" at all (its
        # NewCaseIn schema has no cycle_id field), so it always creates a
        # brand-new case document with its own case_id -- meaning the
        # `case_id in existing` check above can never catch this, since a freshly
        # created duplicate case never shares an id with the case it duplicates.
        existing_keys = {
            (item.get("feature_id"), (item.get("title") or "").strip().lower())
            for item in items
        }
        added = 0
        for case_id in case_ids:
            if case_id in existing:
                continue
            item = self._cycle_item_from_case(case_id, len(items) + 1)
            if not item:
                continue
            key = (item.get("feature_id"), (item.get("title") or "").strip().lower())
            if key in existing_keys:
                raise ValueError(
                    "A test case titled \"%s\" already exists in this cycle for "
                    "this feature" % item.get("title")
                )
            items.append(item)
            existing.add(case_id)
            existing_keys.add(key)
            added += 1
        self.db["test_cycles"].update_one(
            {"_id": ObjectId(cycle_id)},
            {
                "$set": {"items": items, "updated_at": time.time()},
                "$push": {"activity": self._cycle_activity(
                    "items_added", performed_by, new_value=str(added)
                )},
            },
        )
        return added

    def remove_cycle_item(self, cycle_id, item_id, performed_by=None):
        c = self.get_cycle(cycle_id)
        if not c:
            raise ValueError("Cycle not found")
        items = [item for item in c.get("items", []) if item.get("id") != item_id]
        for index, item in enumerate(items, 1):
            item["display_order"] = index
        self.db["test_cycles"].update_one(
            {"_id": ObjectId(cycle_id)},
            {
                "$set": {"items": items, "updated_at": time.time()},
                "$push": {"activity": self._cycle_activity("item_removed", performed_by, item_id)},
            },
        )

    def cycle_report(self, cycle_id):
        c = self.get_cycle(cycle_id)
        if not c:
            return None
        counts, total = c["counts"], c["total"]
        completed = total - counts.get("pending", 0)
        category, priority = {}, {}
        for item in c.get("items", []):
            category[item.get("category", "")] = category.get(item.get("category", ""), 0) + 1
            priority[item.get("priority", "")] = priority.get(item.get("priority", ""), 0) + 1
        return {
            "cycle": c,
            "summary": {
                **counts, "total": total,
                "pass_rate": round(100 * counts.get("passed", 0) / completed, 1) if completed else 0,
                "completion_rate": round(100 * completed / total, 1) if total else 0,
            },
            "category_breakdown": category, "priority_breakdown": priority,
            "recent_activity": list(reversed(c.get("activity", [])[-50:])),
        }

    def cycle_csv(self, cycle_id):
        import csv
        import io
        c = self.get_cycle(cycle_id)
        if not c:
            return None
        out = io.StringIO()
        writer = csv.writer(out)
        writer.writerow([f"Cycle: {c.get('name')}", f"Status: {c.get('status')}"])
        writer.writerow([])
        writer.writerow([
            "#", "Test Case ID", "Title", "Category", "Priority", "Status",
            "Feature", "Version", "Steps", "Actual Result", "Defect Link", "Notes",
        ])
        prio_map = {"p1": "High", "p2": "Medium", "p3": "Low", "1": "High", "2": "Medium",
                    "3": "Low", "critical": "High", "mid": "Medium", "high": "High",
                    "medium": "Medium", "low": "Low"}
        for item in c.get("items", []):
            prio = prio_map.get(str(item.get("priority") or "").strip().lower(), item.get("priority"))
            writer.writerow([
                item.get("display_order"),
                item.get("display_id") or item.get("case_id"),   # readable ID, not the Mongo _id
                item.get("title"),
                item.get("category"), prio, item.get("execution_status"),
                item.get("feature_name"), item.get("feature_version_number"),
                "\n".join(item.get("steps", [])), item.get("actual_result"),
                item.get("defect_link"), item.get("notes"),
            ])
        return out.getvalue()

    def delete_cycle(self, cycle_id):
        self.db["test_cycles"].delete_one({"_id": ObjectId(cycle_id)})
        return {"deleted": cycle_id}

    def save_cycle_as_template(self, cycle_id, name):
        c = self.get_cycle(cycle_id)
        if not c:
            return None
        case_ids = [it.get("case_id") for it in c.get("items", []) if it.get("case_id")]
        return str(self.db["cycle_templates"].insert_one({
            "project_id": c.get("project_id"), "name": name, "case_ids": case_ids,
            "description": c.get("description", ""), "environment": c.get("environment", ""),
            "build_version": c.get("build_version", ""), "case_count": len(case_ids),
            "created_at": time.time()}).inserted_id)

    def list_cycle_templates(self, project_id):
        out = []
        for t in self.db["cycle_templates"].find({"project_id": project_id}).sort("_id", -1):
            out.append({"id": str(t["_id"]), "name": t.get("name"),
                        "case_count": t.get("case_count", len(t.get("case_ids", []))),
                        "description": t.get("description", ""), "created_at": t.get("created_at")})
        return out

    def create_cycle_from_template(self, template_id, name, created_by=None):
        t = self.db["cycle_templates"].find_one({"_id": ObjectId(template_id)})
        if not t:
            return None
        return self.create_cycle(
            t.get("project_id"), name, t.get("case_ids", []), {"from_template": template_id},
            description=t.get("description", ""), environment=t.get("environment", ""),
            build_version=t.get("build_version", ""), created_by=created_by)

    def delete_cycle_template(self, template_id):
        self.db["cycle_templates"].delete_one({"_id": ObjectId(template_id)})
        return {"deleted": template_id}
