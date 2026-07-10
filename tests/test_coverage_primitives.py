"""Baseline characterization tests for the coverage helpers that exist today.

Phase 0 goal: lock in the current behaviour of the pure helpers in `coverage.py` so the
Phase 1+ accuracy rework is regression-protected. No MongoDB / Ollama / GitHub needed.
"""
import coverage as cov


# --------------------------------------------------------------------------- is_test_file
class TestIsTestFile:
    TEST_PATHS = [
        "tests/test_login.py",
        "app/__tests__/foo.spec.ts",
        "src/components/Button.spec.tsx",
        "pkg/handler_test.go",
        "e2e/checkout.cy.js",
        "cypress/integration/login.js",
        "service/UserServiceTest.java",
        "api/users_test.py",
    ]
    IMPL_PATHS = [
        "app/auth/login.py",
        "src/api/users.py",
        "pkg/handler.go",
        "frontend/src/components/Button.tsx",
        "internal/service/user.go",
        "lib/payments/charge.rb",
    ]

    def test_detects_test_files(self):
        for p in self.TEST_PATHS:
            assert cov.is_test_file(p) is True, f"expected test file: {p}"

    def test_passes_impl_files(self):
        for p in self.IMPL_PATHS:
            assert cov.is_test_file(p) is False, f"expected impl file: {p}"

    def test_handles_empty(self):
        assert cov.is_test_file("") is False
        assert cov.is_test_file(None) is False


# --------------------------------------------------------------------------- extract_key
class TestExtractKey:
    def test_finds_ticket_key_in_branch(self):
        assert cov.extract_key("feature/ABC-123-login") == "ABC-123"

    def test_finds_key_with_digits_in_project(self):
        assert cov.extract_key("PROJ2-45 add endpoint") == "PROJ2-45"

    def test_no_key_returns_none(self):
        assert cov.extract_key("just a normal branch name") is None

    def test_lowercase_is_not_a_key(self):
        assert cov.extract_key("abc-123") is None

    def test_empty_input(self):
        assert cov.extract_key("") is None
        assert cov.extract_key(None) is None


# --------------------------------------------------------------------------- pr_text
class TestPrText:
    def test_includes_core_metadata(self):
        pr = {"number": 7, "title": "Add login", "head_ref": "feat/login", "body": "implements auth"}
        files = [{"filename": "app/auth/login.py", "status": "added"}]
        txt = cov.pr_text(pr, files)
        assert "PR #7" in txt
        assert "Add login" in txt
        assert "feat/login" in txt
        assert "implements auth" in txt
        assert "app/auth/login.py (added)" in txt

    def test_caps_file_list_at_40(self):
        pr = {"number": 1, "title": "big", "head_ref": "b", "body": ""}
        files = [{"filename": f"file_{i}.py", "status": "modified"} for i in range(60)]
        txt = cov.pr_text(pr, files)
        assert "file_39.py" in txt
        assert "file_40.py" not in txt


# --------------------------------------------------------------------------- map_pr_to_feature
# Mapping is now epic-driven: a PR carries an Epic key or a ticket key in its
# TITLE or BODY. Epics bind 1:1 to features. A ticket resolves to its parent
# Epic via Jira. There is NO semantic/embedding fallback.
class TestMapPrToFeature:
    def _pr(self, **over):
        base = {"number": 1, "title": "t", "body": ""}
        base.update(over)
        return base

    def test_maps_by_epic_key_in_title(self):
        from conftest import FakeStore, FakeJira
        store = FakeStore(epics={"EP-1": "feat-abc"})
        pr = self._pr(title="Implement EP-1 dashboard")
        fid, conf, method = cov.map_pr_to_feature(store, FakeJira(), pr, "p1")
        assert (fid, conf, method) == ("feat-abc", 1.0, "epic:EP-1")

    def test_maps_ticket_in_body_via_parent_epic(self):
        from conftest import FakeStore, FakeJira
        store = FakeStore(epics={"EP-1": "feat-abc"})
        jira = FakeJira(parents={"PROJ-42": "EP-1"})
        pr = self._pr(title="some work", body="closes PROJ-42")
        fid, conf, method = cov.map_pr_to_feature(store, jira, pr, "p1")
        assert (fid, conf, method) == ("feat-abc", 1.0, "ticket:PROJ-42->epic:EP-1")

    def test_unmapped_when_no_key(self):
        from conftest import FakeStore, FakeJira
        store = FakeStore(epics={"EP-1": "feat-abc"})
        fid, conf, method = cov.map_pr_to_feature(store, FakeJira(), self._pr(), "p1")
        assert (fid, conf, method) == (None, 0.0, "unmapped")

    def test_unmapped_when_epic_not_bound(self):
        from conftest import FakeStore, FakeJira
        store = FakeStore(epics={"EP-1": "feat-abc"})
        jira = FakeJira(parents={"PROJ-42": "EP-999"})   # parent epic bound to nothing
        pr = self._pr(title="PROJ-42 fix")
        assert cov.map_pr_to_feature(store, jira, pr, "p1") == (None, 0.0, "unmapped")

    def test_no_fallback_when_jira_unavailable(self):
        from conftest import FakeStore, FakeJira
        store = FakeStore(epics={"EP-1": "feat-abc"})
        jira = FakeJira(parents={"PROJ-42": "EP-1"}, ok=False)
        pr = self._pr(title="PROJ-42 fix")
        assert cov.map_pr_to_feature(store, jira, pr, "p1") == (None, 0.0, "unmapped")

    def test_direct_epic_preferred_over_ticket(self):
        from conftest import FakeStore, FakeJira
        store = FakeStore(epics={"EP-1": "feat-abc"})
        jira = FakeJira(parents={"PROJ-42": "EP-1"})
        pr = self._pr(title="EP-1 via ticket PROJ-42")
        assert cov.map_pr_to_feature(store, jira, pr, "p1") == ("feat-abc", 1.0, "epic:EP-1")
