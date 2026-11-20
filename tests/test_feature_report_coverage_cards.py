"""Feature PDF coverage cards (found while verifying issue #249).

The cards read `code_pct` / `prs_count` / `automation_pct` from
store.feature_coverage_report(), which returns `coverage_pct` / `pr_count` and has no
`automation_pct`, so "Code coverage" and "Automation Test Coverage" printed 0% on every
export, whatever the real numbers were.
"""
import auth
import main
import pytest
import report
from fastapi.testclient import TestClient

main.store.add_audit = lambda *a, **kw: True
client = TestClient(main.app)

# The shape store.feature_coverage_report() really returns (no code_pct / prs_count).
REPORT = {"feature_id": "f1", "total_test_cases": 20, "covered": 5, "partial": 3,
          "uncovered": 15, "partial_pct": 15.0, "dev_tested": 2, "pr_count": 4,
          "repos_touched": 1, "prs": [], "evidence": [], "coverage_pct": 25.0,
          "dev_test_pct": 10.0}


class TestCoverageCards:
    def test_reads_the_keys_the_report_actually_returns(self):
        cards = dict(report._feature_coverage_cards(REPORT, prs=[]))
        assert cards["Pull requests"] == "4"
        assert cards["Code coverage"] == "25.0%"

    def test_automation_prefers_the_value_the_route_supplies(self):
        cards = dict(report._feature_coverage_cards({**REPORT, "automation_pct": 30.0}, prs=[]))
        assert cards["Automation Test Coverage"] == "30.0%"

    def test_automation_falls_back_to_dev_test_pct(self):
        cards = dict(report._feature_coverage_cards(REPORT, prs=[]))
        assert cards["Automation Test Coverage"] == "10.0%"

    def test_pull_request_count_falls_back_to_the_pr_list(self):
        cov = {k: v for k, v in REPORT.items() if k != "pr_count"}
        cards = dict(report._feature_coverage_cards(cov, prs=[{}, {}]))
        assert cards["Pull requests"] == "2"

    def test_empty_report_is_all_zero_not_a_crash(self):
        cards = dict(report._feature_coverage_cards({}, prs=[]))
        assert cards == {"Pull requests": "0", "Code coverage": "0%",
                         "Automation Test Coverage": "0%"}

    def test_pdf_still_renders_with_the_real_report_shape(self):
        pdf = report.build_feature_pdf({"name": "login", "version": 1}, {**REPORT}, [], [])
        assert pdf.startswith(b"%PDF")


@pytest.fixture
def exporter(monkeypatch):
    user = {"id": "u1", "email": "u1@example.com", "role": "editor", "active": True,
            "session_version": 0, "all_projects": True}
    monkeypatch.setattr(main.store, "get_user", lambda uid: user)
    monkeypatch.setattr(main.store, "get_feature",
                        lambda fid: {"id": fid, "project_id": "p1", "name": "login", "version": 2})
    monkeypatch.setattr(main.store, "get_project", lambda pid: {"id": pid, "name": "P"})
    monkeypatch.setattr(main.store, "feature_coverage_report", lambda fid: dict(REPORT))
    monkeypatch.setattr(main.store, "get_feature_cases", lambda fid: [])
    monkeypatch.setattr(main.store, "list_prs", lambda **kw: [])
    seen = {}
    monkeypatch.setattr(main.store, "get_automation_coverage",
                        lambda fid, version=None: seen.update(version=version) or {"coverage_pct": 40.0})
    captured = {}
    monkeypatch.setattr(report, "build_feature_pdf",
                        lambda f, cov, cases, prs: captured.update(cov=cov) or b"%PDF-1.4 fake")
    return {auth.SESSION_COOKIE: auth.sign_session("u1", 0)}, captured, seen


def test_route_passes_the_feature_pages_automation_figure_to_the_pdf(exporter):
    cookie, captured, seen = exporter
    r = client.get("/api/features/f1/report.pdf", cookies=cookie)
    assert r.status_code == 200
    assert captured["cov"]["automation_pct"] == 40.0
    assert captured["cov"]["coverage_pct"] == 25.0       # confirmed coverage, unchanged
    assert seen["version"] == 2                           # the feature's own version


def test_route_defaults_automation_to_zero_without_a_snapshot(exporter, monkeypatch):
    cookie, captured, _ = exporter
    monkeypatch.setattr(main.store, "get_automation_coverage", lambda fid, version=None: None)
    r = client.get("/api/features/f1/report.pdf", cookies=cookie)
    assert r.status_code == 200
    assert captured["cov"]["automation_pct"] == 0
