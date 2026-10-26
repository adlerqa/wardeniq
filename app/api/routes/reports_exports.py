"""Feature PDF/CSV exports and Gap Analysis (PR coverage / automation) exports.

Moved out of main.py (Phase 6 of docs/internal/REFACTOR_PLAN.md — contiguous block, part of the
plan's "ideal first" extraction group). Decorator changed from `@app.` to `@router.`
only — same 7 paths, same status codes, same response shapes. `import report` is kept
local to each handler (not hoisted), matching the original main.py style exactly.
"""
from fastapi import APIRouter, HTTPException, Response

from core.state import store

router = APIRouter()


@router.get("/api/features/{fid}/report.pdf")
def feature_report(fid: str):
    import report
    f = store.get_feature(fid)
    if not f:
        raise HTTPException(404, "feature not found")
    project = store.get_project(f.get("project_id")) if f.get("project_id") else None
    if project and project.get("name"):
        f["project_name"] = project["name"]
    cov_rep = store.feature_coverage_report(fid)
    cases = store.get_feature_cases(fid)
    prs = store.list_prs(feature_id=fid)
    pdf = report.build_feature_pdf(f, cov_rep, cases, prs)
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="feature_{fid}.pdf"'})


def _selected_feature_cases(fid: str, selected_ids: list[str] | None = None):
    f = store.get_feature(fid)
    if not f:
        raise HTTPException(404, "feature not found")
    project = store.get_project(f.get("project_id")) if f.get("project_id") else None
    if project and project.get("name"):
        f["project_name"] = project["name"]
    cases = store.get_feature_cases(fid)
    if selected_ids:
        wanted = {str(x) for x in selected_ids}
        cases = [c for c in cases if c.get("id") in wanted or c.get("display_id") in wanted]
    if not cases:
        raise HTTPException(400, "no test cases selected")
    return f, cases


@router.get("/api/features/{fid}/export/pdf")
def feature_export_pdf(fid: str):
    import report
    f, cases = _selected_feature_cases(fid)
    pdf = report.build_testcase_pdf(f, cases)
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="test_cases_{fid}.pdf"'})


@router.post("/api/features/{fid}/export/pdf-selected")
def feature_export_selected_pdf(fid: str, body: dict):
    import report
    f, cases = _selected_feature_cases(fid, body.get("testCaseIds") or body.get("test_case_ids") or [])
    pdf = report.build_testcase_pdf(f, cases)
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="selected_test_cases_{fid}.pdf"'})


@router.get("/api/features/{fid}/gap/pr-coverage/export/{fmt}")
def export_gap_pr_coverage(fid: str, fmt: str):
    import report
    f = store.get_feature(fid)
    if not f:
        raise HTTPException(404, "feature not found")
    runs = store.list_code_coverage_runs(feature_id=fid, limit=500)
    # Flag PRs excluded from coverage (feature ships in the exclude-PR change);
    # guarded so this export works standalone until that lands.
    excluded_keys = (store.excluded_pr_run_keys(fid)
                     if hasattr(store, "excluded_pr_run_keys") else set())
    for r in runs:
        r["excluded"] = (r.get("repo_id"), str(r.get("pr_number"))) in excluded_keys
    cases = store.cases_brief(store.feature_test_case_ids(fid))
    if fmt == "csv":
        return Response(content=report.build_gap_pr_csv(f, runs, cases), media_type="text/csv",
                        headers={"Content-Disposition": f'attachment; filename="gap-pr-coverage-{fid}.csv"'})
    if fmt == "pdf":
        return Response(content=report.build_gap_pr_pdf(f, runs, cases), media_type="application/pdf",
                        headers={"Content-Disposition": f'attachment; filename="gap-pr-coverage-{fid}.pdf"'})
    raise HTTPException(400, "format must be csv or pdf")


@router.get("/api/features/{fid}/gap/automation/export/{fmt}")
def export_gap_automation(fid: str, fmt: str):
    import report
    f = store.get_feature(fid)
    if not f:
        raise HTTPException(404, "feature not found")
    snap = store.get_automation_coverage(fid, version=f.get("version", 1)) or {}
    if fmt == "csv":
        return Response(content=report.build_gap_automation_csv(f, snap), media_type="text/csv",
                        headers={"Content-Disposition": f'attachment; filename="gap-automation-{fid}.csv"'})
    if fmt == "pdf":
        return Response(content=report.build_gap_automation_pdf(f, snap), media_type="application/pdf",
                        headers={"Content-Disposition": f'attachment; filename="gap-automation-{fid}.pdf"'})
    raise HTTPException(400, "format must be csv or pdf")


@router.get("/api/features/{fid}/export/csv")
def feature_export_csv(fid: str):
    import report
    f, cases = _selected_feature_cases(fid)
    csv_bytes = report.build_testcase_csv(f, cases)
    return Response(content=csv_bytes, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="test_cases_{fid}.csv"'})


@router.post("/api/features/{fid}/export/csv-selected")
def feature_export_selected_csv(fid: str, body: dict):
    import report
    f, cases = _selected_feature_cases(fid, body.get("testCaseIds") or body.get("test_case_ids") or [])
    csv_bytes = report.build_testcase_csv(f, cases)
    return Response(content=csv_bytes, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="selected_test_cases_{fid}.csv"'})
