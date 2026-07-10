"""Per-project access control (users scoped to all projects or specific ones)."""
import os
import types
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]


def _import_main():
    old = Path.cwd()
    try:
        os.chdir(_ROOT / "app")
        import main
        return main
    finally:
        os.chdir(old)


M = _import_main()


class TestAccessHelpers:
    def test_admin_sees_all(self):
        u = {"role": "admin", "all_projects": False, "project_ids": ["p1"]}
        assert M._user_all_projects(u) is True
        assert M._user_can_access_project(u, "pZ") is True
        assert M._allowed_project_ids(u) is None

    def test_all_projects_flag(self):
        u = {"role": "viewer", "all_projects": True, "project_ids": []}
        assert M._user_all_projects(u) is True
        assert M._user_can_access_project(u, "anything") is True
        assert M._allowed_project_ids(u) is None

    def test_scoped_user(self):
        u = {"role": "editor", "all_projects": False, "project_ids": ["p1", "p2"]}
        assert M._user_all_projects(u) is False
        assert M._user_can_access_project(u, "p1") is True
        assert M._user_can_access_project(u, "p3") is False
        assert M._allowed_project_ids(u) == {"p1", "p2"}

    def test_missing_field_grandfathered(self):
        assert M._user_all_projects({"role": "viewer"}) is True

    def test_none_user_unrestricted(self):
        assert M._user_all_projects(None) is True

    def test_filter_projects(self):
        u = {"role": "viewer", "all_projects": False, "project_ids": ["p1"]}
        projs = [{"id": "p1", "name": "A"}, {"id": "p2", "name": "B"}]
        assert [p["id"] for p in M._filter_projects_for(u, projs)] == ["p1"]
        assert len(M._filter_projects_for({"role": "admin"}, projs)) == 2


class TestTargetProjectForPath:
    def test_pid_in_path(self):
        assert M._target_project_for_path("GET", "/api/projects/p1") == "p1"
        assert M._target_project_for_path("POST", "/api/projects/p1/repos") == "p1"
        assert M._target_project_for_path("GET", "/api/projects/p1/mindmap") == "p1"

    def test_collection_routes_return_none(self):
        assert M._target_project_for_path("GET", "/api/projects") is None
        assert M._target_project_for_path("POST", "/api/projects") is None

    def test_unrelated_paths_none(self):
        assert M._target_project_for_path("GET", "/api/dashboard") is None
        assert M._target_project_for_path("GET", "/api/users") is None

    def test_feature_path_resolves_via_store(self, monkeypatch):
        monkeypatch.setattr(M, "store", types.SimpleNamespace(
            get_feature=lambda fid: {"id": fid, "project_id": "pFEAT"}))
        assert M._target_project_for_path("GET", "/api/features/f9") == "pFEAT"

    def test_repo_path_resolves_via_store(self, monkeypatch):
        monkeypatch.setattr(M, "store", types.SimpleNamespace(
            get_repo=lambda rid: {"id": rid, "project_id": "pREPO"}))
        assert M._target_project_for_path("DELETE", "/api/repos/r1") == "pREPO"


class TestRequireProject:
    def _req(self, user):
        return types.SimpleNamespace(state=types.SimpleNamespace(user=user))

    def test_allows_member(self):
        r = self._req({"role": "viewer", "all_projects": False, "project_ids": ["p1"]})
        assert M._require_project(r, "p1")

    def test_denies_non_member(self):
        r = self._req({"role": "viewer", "all_projects": False, "project_ids": ["p1"]})
        with pytest.raises(M.HTTPException) as ei:
            M._require_project(r, "p2")
        assert ei.value.status_code == 403

    def test_admin_passes(self):
        r = self._req({"role": "admin"})
        assert M._require_project(r, "whatever")


class TestInviteProjectScope:
    @pytest.fixture
    def env(self, monkeypatch):
        docs = {}
        n = {"i": 0}

        class FS:
            def get_user_by_email(self, e):
                return None
            def get_project(self, pid):
                return {"id": pid} if pid in {"p1", "p2"} else None
            def get_user(self, uid):
                return docs.get(uid)
            def create_user(self, email, name, role="viewer", active=True,
                            invite_status="active", invited_by=None,
                            all_projects=True, project_ids=None):
                n["i"] += 1
                uid = f"u{n['i']}"
                docs[uid] = {"id": uid, "email": email, "name": name, "role": role,
                             "active": active, "invite_status": invite_status,
                             "invited_by": invited_by, "all_projects": all_projects,
                             "project_ids": project_ids or [], "invited_at": 1.0}
                return docs[uid]
            def set_otp(self, *a):
                pass

        monkeypatch.setattr(M, "store", FS())
        monkeypatch.setattr(M, "_deliver_otp", lambda *a, **k: ("sent", ""))
        return M

    def _req(self):
        return types.SimpleNamespace(state=types.SimpleNamespace(
            user={"id": "admin", "role": "admin"}))

    def test_invite_all_projects(self, env):
        r = env.invite_user(env.UserIn(email="a@x.com", role="viewer", all_projects=True), self._req())
        assert r["user"]["all_projects"] is True

    def test_invite_specific_projects(self, env):
        r = env.invite_user(env.UserIn(email="b@x.com", role="viewer", all_projects=False,
                                       project_ids=["p1", "p2"]), self._req())
        assert r["user"]["all_projects"] is False
        assert set(r["user"]["project_ids"]) == {"p1", "p2"}

    def test_invite_specific_but_empty_rejected(self, env):
        with pytest.raises(env.HTTPException) as ei:
            env.invite_user(env.UserIn(email="c@x.com", role="viewer", all_projects=False,
                                       project_ids=[]), self._req())
        assert ei.value.status_code == 400

    def test_invite_admin_forced_all_projects(self, env):
        r = env.invite_user(env.UserIn(email="d@x.com", role="admin", all_projects=False,
                                       project_ids=["p1"]), self._req())
        assert r["user"]["all_projects"] is True

    def test_invite_unknown_project_rejected(self, env):
        with pytest.raises(env.HTTPException) as ei:
            env.invite_user(env.UserIn(email="e@x.com", role="viewer", all_projects=False,
                                       project_ids=["nope"]), self._req())
        assert ei.value.status_code == 400
