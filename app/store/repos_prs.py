"""Connected repos (GitHub/GitLab) and pull-request bookkeeping.

Moved out of store.py (Phase 5 of REFACTOR_PLAN.md). `_converge_repo_kinds` is a
repo-maintenance one-off (not name-matched by `*_repo*`) placed here because it
operates entirely on `self.repos`.
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


class ReposPrsMixin(_Base):
    """No __init__: shares the collection attributes/state that store/base.py's
    BaseStore.__init__ sets up (composed last in store/__init__.py's Store MRO)."""

    def _converge_repo_kinds(self):
        """One-time convergence for the repo 'kind' badge. Test-type repos were
        previously always tagged kind='other' by default (there was no way to choose
        their kind), so promote those to the dedicated 'test' kind added later. Only
        touches repo_type=='test' rows whose kind is unset/empty/'other' — a
        deliberately-chosen kind on a test repo (if any) is left alone. App repos are
        never auto-changed (their 'other' could be intentional)."""
        try:
            self.repos.update_many(
                {"repo_type": "test",
                 "kind": {"$in": ["other", "", None]}},
                {"$set": {"kind": "test"}})
        except Exception:  # noqa: BLE001
            pass

    def delete_repo(self, rid):
        self.prs.delete_many({"repo_id": rid})
        self.repos.delete_one({"_id": ObjectId(rid)})
        return {"deleted_repo": rid}

    def add_repo(self, project_id, owner, name, url, kind, default_branch="main",
                 repo_type="app", git_provider="github", label="", webhook_id=None,
                 webhook_secret_enc=""):
        full = f"{owner}/{name}"
        doc = {"project_id": project_id, "owner": owner, "name": name, "full_name": full,
               "url": url, "kind": kind, "label": label or full,
               "repo_type": repo_type, "git_provider": git_provider,
               "default_branch": default_branch, "watch": True,
               "webhook_id": webhook_id, "webhook_secret_enc": webhook_secret_enc,
               "last_synced": 0, "created_at": time.time()}
        existing = self.repos.find_one({"project_id": project_id, "full_name": full,
                                        "git_provider": git_provider})
        if existing:
            self.repos.update_one({"_id": existing["_id"]},
                                  {"$set": {k: v for k, v in doc.items() if v is not None
                                            and k not in ("created_at",)}})
            return str(existing["_id"])
        return str(self.repos.insert_one(doc).inserted_id)

    def get_repo(self, rid):
        if not ObjectId.is_valid(rid):
            return None
        r = self.repos.find_one({"_id": ObjectId(rid)})
        if not r:
            return None
        r["id"] = str(r.pop("_id"))
        return r

    def list_repos(self, project_id):
        out = []
        for r in self.repos.find({"project_id": project_id}).sort("_id", 1):
            r["id"] = str(r.pop("_id"))
            r["pr_count"] = self.prs.count_documents({"repo_id": r["id"]})
            # Don't return raw encrypted secret in API payloads.
            r["webhook_configured"] = bool(r.pop("webhook_secret_enc", "") or
                                           r.get("webhook_id"))
            out.append(r)
        return out

    def repos_watching(self):
        return [{**r, "id": str(r["_id"])} for r in self.repos.find({"watch": True})]

    def repo_by_fullname(self, full_name, git_provider=None):
        q = {"full_name": full_name}
        if git_provider:
            q["git_provider"] = git_provider
        r = self.repos.find_one(q)
        return ({**r, "id": str(r["_id"])} if r else None)

    def repos_by_fullname_app(self, full_name, git_provider="github"):
        """All `app` repos across projects sharing this full_name (for fan-out webhooks)."""
        q = {"full_name": full_name, "git_provider": git_provider, "repo_type": "app"}
        out = []
        for r in self.repos.find(q):
            r["id"] = str(r.pop("_id"))
            out.append(r)
        return out

    def set_repo_synced(self, repo_id, ts):
        self.repos.update_one({"_id": ObjectId(repo_id)}, {"$set": {"last_synced": ts}})

    def set_repo_watch(self, repo_id, watch):
        self.repos.update_one({"_id": ObjectId(repo_id)}, {"$set": {"watch": bool(watch)}})

    def set_repo_webhook(self, repo_id, webhook_id, webhook_secret_enc):
        self.repos.update_one({"_id": ObjectId(repo_id)}, {"$set": {
            "webhook_id": webhook_id, "webhook_secret_enc": webhook_secret_enc}})

    def set_repo_label(self, repo_id, label):
        self.repos.update_one({"_id": ObjectId(repo_id)}, {"$set": {"label": label}})

    def upsert_pr(self, doc):
        """doc keyed by (repo_id, number). Returns pr_id."""
        key = {"repo_id": doc["repo_id"], "number": doc["number"]}
        self.prs.update_one(key, {"$set": doc, "$setOnInsert": {"created_at_local": time.time()}},
                            upsert=True)
        return str(self.prs.find_one(key)["_id"])

    def set_pr_mapping(self, pr_id, feature_id, confidence, method):
        update = {"$set": {"feature_id": feature_id, "mapping_confidence": confidence,
                           "mapping_method": method}}
        if feature_id:
            # A resolved mapping supersedes any semantic suggestion left from an earlier run.
            update["$unset"] = {"mapping_suggestion": ""}
        self.prs.update_one({"_id": ObjectId(pr_id)}, update)

    def set_pr_suggestion(self, pr_id, suggestion):
        """Record (or, with None, clear) a semantic feature SUGGESTION for an unmapped PR
        (issue #54). Deliberately separate from feature_id / mapping_method / mapping_confidence:
        those drive coverage accounting, a suggestion must not."""
        if suggestion:
            self.prs.update_one({"_id": ObjectId(pr_id)}, {"$set": {"mapping_suggestion": suggestion}})
        else:
            self.prs.update_one({"_id": ObjectId(pr_id)}, {"$unset": {"mapping_suggestion": ""}})

    def set_pr_excluded(self, pr_id, excluded: bool):
        """Exclude/include a PR from Gap Analysis coverage. Excluded PRs remain
        listed (flagged) but do not contribute to a feature's coverage."""
        if not ObjectId.is_valid(pr_id):
            return None
        self.prs.update_one({"_id": ObjectId(pr_id)},
                            {"$set": {"excluded": bool(excluded)}})
        p = self.prs.find_one({"_id": ObjectId(pr_id)})
        return {"id": pr_id, "excluded": bool(p.get("excluded"))} if p else None

    def excluded_pr_run_keys(self, feature_id):
        """Set of (repo_id, str(pr_number)) for PRs excluded from a feature —
        used to flag/skip their coverage runs in the Gap Analysis list."""
        keys = set()
        for p in self.prs.find({"feature_id": feature_id, "excluded": True},
                               {"repo_id": 1, "number": 1}):
            keys.add((p.get("repo_id"), str(p.get("number"))))
        return keys

    def list_prs(self, project_id=None, feature_id=None):
        q = {}
        if project_id:
            q["project_id"] = project_id
        if feature_id:
            q["feature_id"] = feature_id
        out = []
        for p in self.prs.find(q).sort("number", -1):
            p["id"] = str(p.pop("_id")); out.append(p)
        return out

    def save_coverage(self, pr_id, feature_id, covered, dev_test_files, confidence, notice=""):
        self.coverage.update_one({"pr_id": pr_id}, {"$set": {
            "pr_id": pr_id, "feature_id": feature_id, "covered": covered,
            "dev_test_files": dev_test_files, "confidence": confidence,
            "notice": notice, "updated_at": time.time()}}, upsert=True)

    def list_unmapped_prs(self, project_id):
        """PRs in a project that didn't auto-map to a feature (need manual assignment)."""
        q = {"project_id": project_id,
             "$or": [{"feature_id": None}, {"feature_id": {"$exists": False}}]}
        out = []
        for p in self.prs.find(q).sort("number", -1):
            out.append({"id": str(p["_id"]), "number": p.get("number"), "title": p.get("title"),
                        "repo": p.get("repo_full_name"), "url": p.get("url"),
                        "state": p.get("state"), "author": p.get("author"),
                        "mapping_confidence": p.get("mapping_confidence", 0),
                        # Semantic suggestion (issue #54), or None. Not a mapping: the PR is
                        # still unmapped for coverage until someone assigns it.
                        "mapping_suggestion": p.get("mapping_suggestion")})
        return out

    def set_repo_scan_status(self, rid, status, **fields):
        upd = {"scan_status": status, **fields, "scan_status_updated_at": time.time()}
        self.repos.update_one({"_id": ObjectId(rid)}, {"$set": upd})

    def repos_for_project(self, project_id, repo_type=None, git_provider=None):
        q = {"project_id": project_id}
        if repo_type == "app":
            # "App" (analysis) repos = anything NOT explicitly a test repo, so unclassified /
            # legacy repos are still selectable in impact analysis + Mind Map.
            q["$or"] = [{"repo_type": "app"}, {"repo_type": {"$in": [None, ""]}},
                        {"repo_type": {"$exists": False}}]
        elif repo_type == "test":
            q["repo_type"] = "test"
        if git_provider:
            q["git_provider"] = git_provider
        out = []
        for r in self.repos.find(q).sort("_id", 1):
            r["id"] = str(r.pop("_id"))
            # Never leak the encrypted webhook secret to callers — surface only a
            # "configured" boolean (matches list_repos()). No internal caller reads
            # the raw blob from here.
            r["webhook_configured"] = bool(r.pop("webhook_secret_enc", "") or
                                           r.get("webhook_id"))
            out.append(r)
        return out
