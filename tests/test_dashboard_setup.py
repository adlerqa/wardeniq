"""Dashboard first-run checklist flags (issue #254).

store.setup_status() derives the "Get started" card's step states from real
data only: the scoped dashboard counts plus the `settings.configured` flag the
first-run gate (frontend 16-boot.js) already uses. Uses an in-memory fake
store, same pattern as tests/test_dashboard_automation_coverage.py.
"""
from bson import ObjectId

from store import Store


class _FakeCollection:
    """Supports the query shapes dashboard() and get_settings() issue."""

    def __init__(self, docs=None):
        self.docs = docs or []

    def _matches(self, doc, query):
        for k, v in (query or {}).items():
            if isinstance(v, dict) and "$in" in v:
                if doc.get(k) not in v["$in"]:
                    return False
            elif doc.get(k) != v:
                return False
        return True

    def find(self, query=None, projection=None):
        return [d for d in self.docs if self._matches(d, query)]

    def find_one(self, query=None, projection=None, **kw):
        matches = self.find(query)
        return matches[0] if matches else None

    def count_documents(self, query=None):
        return len(self.find(query))


class _BrokenSettings:
    def find_one(self, *a, **kw):
        raise RuntimeError("settings unavailable")


def _store(settings=None):
    s = Store.__new__(Store)
    s.db = {"automation_coverage": _FakeCollection([]),
            "settings": _FakeCollection([dict(settings, _id="app")] if settings is not None else [])}
    for name in ("coverage", "features", "cases", "assoc", "projects", "prs", "repos", "steps"):
        setattr(s, name, _FakeCollection([]))
    # tests/conftest.py stubs Store.get_settings to `{}` for the whole suite; restore
    # the real read (SettingsMixin.get_settings) on this instance only.
    s.get_settings = lambda: s.db["settings"].find_one({"_id": "app"}) or {}
    return s


def _add_project(s, name="P"):
    oid = ObjectId()
    s.projects.docs.append({"_id": oid, "name": name})
    return str(oid)


def _add_feature_with_case(s, pid):
    fid, cid = ObjectId(), ObjectId()
    s.features.docs.append({"_id": fid, "group_id": str(fid), "version": 1,
                            "project_id": pid, "sources": []})
    s.assoc.docs.append({"feature_id": str(fid), "test_case_id": str(cid)})
    s.cases.docs.append({"_id": cid, "type": "functional"})
    return str(fid)


NOTHING_DONE = {"llm_configured": False, "has_project": False, "has_repo": False,
                "has_feature": False, "has_test_cases": False}


class TestSetupStatus:
    def test_fresh_install_has_nothing_done(self):
        assert _store().setup_status({}) == NOTHING_DONE

    def test_flags_come_from_counts(self):
        st = _store({"configured": True}).setup_status(
            {"projects": 1, "repos": 2, "features": 3, "test_cases": 4})
        assert st == {"llm_configured": True, "has_project": True, "has_repo": True,
                      "has_feature": True, "has_test_cases": True}

    def test_only_booleans_are_exposed(self):
        st = _store({"configured": True, "llm_api_key_enc": "secret"}).setup_status(
            {"projects": 3, "repos": 1})
        assert all(isinstance(v, bool) for v in st.values())

    def test_llm_not_configured(self):
        st = _store({"configured": False}).setup_status(
            {"projects": 1, "features": 1, "test_cases": 1})
        assert st["llm_configured"] is False
        assert st["has_test_cases"] is True

    def test_saved_llm_fields_without_configured_flag_do_not_count(self):
        # Only the explicit `configured` flag (set when the LLM section is saved,
        # or backfilled for old installs) counts -- same rule as the boot gate.
        st = _store({"llm_provider": "ollama"}).setup_status({})
        assert st["llm_configured"] is False

    def test_missing_counts_and_none_values_are_treated_as_zero(self):
        st = _store({"configured": True}).setup_status({"projects": None})
        assert st["has_project"] is False

    def test_settings_read_failure_does_not_break_dashboard(self):
        s = _store()
        s.db["settings"] = _BrokenSettings()
        assert s.setup_status({"projects": 1})["llm_configured"] is False


class TestDashboardIncludesSetup:
    def test_empty_install(self):
        result = _store().dashboard()
        assert result["setup"] == NOTHING_DONE

    def test_project_only(self):
        s = _store({"configured": True})
        _add_project(s)
        st = s.dashboard()["setup"]
        assert st["llm_configured"] and st["has_project"]
        assert not st["has_feature"] and not st["has_test_cases"]

    def test_feature_and_cases(self):
        s = _store({"configured": True})
        pid = _add_project(s)
        _add_feature_with_case(s, pid)
        st = s.dashboard()["setup"]
        assert st["has_feature"] and st["has_test_cases"]
        assert st["has_repo"] is False

    def test_repo_flag(self):
        s = _store({"configured": True})
        pid = _add_project(s)
        s.repos.docs.append({"project_id": pid, "full_name": "o/r"})
        assert s.dashboard()["setup"]["has_repo"] is True

    def test_scoped_user_only_sees_their_projects(self):
        # Another project has data, but a user scoped to an empty project must
        # still be shown the steps as not done.
        s = _store({"configured": True})
        other = _add_project(s, "Other")
        _add_feature_with_case(s, other)
        s.repos.docs.append({"project_id": other, "full_name": "o/r"})
        mine = _add_project(s, "Mine")
        st = s.dashboard(project_ids={mine})["setup"]
        assert st["has_project"] is True
        assert st["has_feature"] is False
        assert st["has_test_cases"] is False
        assert st["has_repo"] is False

    def test_scoped_user_with_no_projects(self):
        s = _store({"configured": True})
        _add_project(s)
        st = s.dashboard(project_ids=set())["setup"]
        assert st["has_project"] is False
