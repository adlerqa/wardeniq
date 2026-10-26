"""Project CRUD and per-project PAT storage.

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


class ProjectsMixin(_Base):
    """No __init__: shares the collection attributes/state that store/base.py's
    BaseStore.__init__ sets up (composed last in store/__init__.py's Store MRO)."""

    def create_project(self, name, key=None, description="", jira_project_key=None,
                       jira_project_name=None, confluence_space_key=None,
                       confluence_space_name=None, default_git_provider="github"):
        doc = {"name": name, "key": key, "description": (description or ""),
               "jira_project_key": jira_project_key, "jira_project_name": jira_project_name,
               "confluence_space_key": confluence_space_key,
               "confluence_space_name": confluence_space_name,
               "default_git_provider": (default_git_provider or "github").lower(),
               "created_at": time.time()}
        return str(self.projects.insert_one(doc).inserted_id)

    def get_or_default_project(self):
        p = self.projects.find_one({})
        if p:
            return str(p["_id"])
        return self.create_project("Default Project")

    def get_project(self, pid):
        if not ObjectId.is_valid(pid):
            return None
        p = self.projects.find_one({"_id": ObjectId(pid)})
        if not p:
            return None
        p["id"] = str(p.pop("_id"))
        return p

    def list_projects(self):
        out = []
        for p in self.projects.find({}).sort("_id", -1):
            pid = str(p.pop("_id")); p["id"] = pid
            # Strip secret/encrypted blobs before returning.
            for k in ("github_pat_enc", "gitlab_pat_enc"):
                p.pop(k, None)
            p["github_pat_set"] = bool(self.projects.find_one(
                {"_id": ObjectId(pid)}, {"github_pat_enc": 1}).get("github_pat_enc"))
            p["gitlab_pat_set"] = bool(self.projects.find_one(
                {"_id": ObjectId(pid)}, {"gitlab_pat_enc": 1}).get("gitlab_pat_enc"))
            p["repo_count"] = self.repos.count_documents({"project_id": pid})
            # Each version of a feature is stored as its OWN document in
            # `features` (create_feature()/features.py), all sharing one
            # `group_id` as the stable feature identity -- `_id` is per-version,
            # not per-feature. A raw count_documents() over the collection was
            # counting every version as if it were a distinct feature, so
            # creating a new version of an existing feature inflated this
            # number just like adding a brand-new one would. Dedup by group_id
            # (falling back to the doc's own _id for pre-versioning features
            # that predate group_id, exactly as list_features() already does)
            # so this matches what the Features page actually lists.
            group_ids = set()
            for f in self.features.find({"project_id": pid}, {"group_id": 1}):
                group_ids.add(f.get("group_id", str(f["_id"])))
            p["feature_count"] = len(group_ids)
            out.append(p)
        return out

    def update_project(self, pid, fields):
        """Apply a $set update to a project doc; safe-ignores empty input."""
        if not ObjectId.is_valid(pid) or not fields:
            return None
        clean = {k: v for k, v in fields.items() if v is not None}
        if not clean:
            return self.get_project(pid)
        self.projects.update_one({"_id": ObjectId(pid)}, {"$set": clean})
        return self.get_project(pid)

    def get_project_github_pat_enc(self, pid):
        if not ObjectId.is_valid(pid):
            return ""
        p = self.projects.find_one({"_id": ObjectId(pid)}, {"github_pat_enc": 1})
        return (p or {}).get("github_pat_enc", "") or ""

    def get_project_gitlab_pat_enc(self, pid):
        if not ObjectId.is_valid(pid):
            return ""
        p = self.projects.find_one({"_id": ObjectId(pid)}, {"gitlab_pat_enc": 1})
        return (p or {}).get("gitlab_pat_enc", "") or ""

    def set_project_github_pat_enc(self, pid, enc):
        self.projects.update_one({"_id": ObjectId(pid)},
                                 {"$set": {"github_pat_enc": enc or ""}})

    def set_project_gitlab_pat_enc(self, pid, enc):
        self.projects.update_one({"_id": ObjectId(pid)},
                                 {"$set": {"gitlab_pat_enc": enc or ""}})

    def rename_project(self, pid, name):
        self.projects.update_one({"_id": ObjectId(pid)}, {"$set": {"name": name}})

    def delete_project(self, pid):
        if not ObjectId.is_valid(pid) or not self.projects.find_one({"_id": ObjectId(pid)}):
            return None
        fids = [str(f["_id"]) for f in self.features.find({"project_id": pid}, {"_id": 1})]
        project_case_ids = {
            row["test_case_id"] for row in self.assoc.find(
                {"feature_id": {"$in": fids}}, {"test_case_id": 1}
            )
        }
        externally_shared = {
            cid for cid in project_case_ids
            if self.assoc.count_documents({
                "test_case_id": cid,
                "feature_id": {"$nin": fids},
            }) > 0
        }
        removed_orphan_cases = 0
        for fid in fids:
            result = self.delete_feature(fid)
            removed_orphan_cases += result.get("removed_orphan_cases", 0)
        rids = [str(r["_id"]) for r in self.repos.find({"project_id": pid}, {"_id": 1})]
        for rid in rids:
            self.delete_repo(rid)
        self.code_chunks.delete_many({"project_id": pid})
        self.code_cov.delete_many({"project_id": pid})
        self.db["test_cycles"].delete_many({"project_id": pid})
        self.db["jobs"].delete_many({"project_id": pid})
        self.projects.delete_one({"_id": ObjectId(pid)})
        self.cleanup_orphaned_steps()
        return {
            "deleted_project": pid,
            "features": len(fids),
            "repos": len(rids),
            "removed_orphan_cases": removed_orphan_cases,
            "preserved_shared_cases": len(externally_shared),
        }
