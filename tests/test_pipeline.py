"""End-to-end accuracy check on a LABELLED sample (no network).

This exercises the grounded pipeline the workers orchestrate — commit→case matching and
PR coverage — against a hand-labelled feature so we can assert precision (no cross-domain
false positives) and recall (implemented cases are caught) in CI, as a stand-in for a live
repo run. It is the verification step for Phases 2–4.
"""
import coverage as cov
import grounding as g
from conftest import FakeLLM

# A feature with four labelled cases: login (endpoint-implemented), logout (symbol-implemented),
# delete-account (NOT implemented by the diff), and an OTP case from a different domain.
CASES = [
    {"id": "login", "type": "functional",
     "title": "Login with valid credentials issues a session",
     "steps": ["POST /api/login with valid creds -> 200 + token"]},
    {"id": "logout", "type": "functional",
     "title": "Logout revokes the active session",
     "steps": ["call logout(session_id) -> session revoked"]},
    {"id": "delete", "type": "functional",
     "title": "Delete account purges all user data",
     "steps": ["DELETE /api/account -> data purged"]},
    {"id": "otp", "type": "functional",
     "title": "OTP code expires after five minutes",
     "steps": ["wait five minutes -> code rejected"]},
]

LOGIN_DIFF = (
    "@@ -0,0 +1,6 @@\n"
    '+@router.post("/api/login")\n'
    "+def login(payload):\n"
    "+    return issue_session(payload)\n"
    "+\n"
    "+def logout(session_id):\n"
    "+    return revoke_session(session_id)\n"
)
COMMITS = [{"repo": "o/r", "sha": "deadbeef1234", "message": "implement auth",
            "files": [{"filename": "app/auth.py", "status": "added",
                       "additions": 6, "deletions": 0, "patch": LOGIN_DIFF}]}]


def test_commit_analysis_precision_and_recall():
    out = g.match_commit_changes(COMMITS, CASES)
    matched = out["matched_ids"]
    # PRECISION: cross-domain / unimplemented cases must NOT be flagged
    assert matched & {"delete", "otp"} == set()
    # RECALL: both implemented cases are caught
    assert {"login", "logout"} <= matched
    # login is an exact endpoint match (tier 1) with real file:line evidence
    lm = out["matches"]["login"]
    assert lm["tier"] == 1 and lm["signal_type"] == "endpoint"
    assert lm["evidence"][0]["file"] == "app/auth.py" and lm["evidence"][0]["line"] == 1
    # logout is caught only by the guarded symbol tier
    assert out["matches"]["logout"]["signal_type"] == "symbol"


def test_pr_coverage_pipeline_labeled():
    files = [
        {"filename": "app/auth.py", "status": "added", "additions": 6, "deletions": 0, "patch": LOGIN_DIFF},
        {"filename": "tests/test_login.py", "status": "added", "additions": 3, "deletions": 0,
         "patch": "@@ +1,2 @@\n+def test_login():\n+    assert True\n"},
    ]
    # not a test-only PR (it changes production code)
    assert g.is_test_only(files) is False
    prod, test_files, _ = g.classify_diff_files(files)
    prod_files = [f for f in files if f["filename"] in set(prod)]

    # grounded implementation coverage
    pseudo = [{"repo": "o/r", "sha": "42", "message": "login", "files": prod_files}]
    gm = g.match_commit_changes(pseudo, CASES)
    assert "login" in gm["matched_ids"]

    # remaining cases verified by the (faked) LLM — say delete-account is now implemented
    remaining = [c for c in CASES if c["id"] not in gm["matched_ids"]]
    llm = FakeLLM(response={"covered": [
        {"test_case_id": "delete", "status": "covered", "confidence": 0.82, "rationale": "purge impl"}]})
    res = cov.verify_pr_implementation(llm, {"number": 1, "title": "x"}, prod_files, remaining)
    covered_ids = gm["matched_ids"] | {x["test_case_id"] for x in res["covered"]}
    assert {"login", "delete"} <= covered_ids

    # automation signal: the changed login test file marks the login case dev-tested
    assert "login" in g.dev_tested_cases(test_files, CASES)


def test_test_only_pr_is_flagged():
    files = [{"filename": "tests/test_login.py", "status": "modified",
              "additions": 2, "deletions": 0, "patch": "@@ +1 @@\n+x\n"},
             {"filename": "jest.config.js", "status": "modified",
              "additions": 1, "deletions": 0, "patch": "@@ +1 @@\n+y\n"}]
    assert g.is_test_only(files) is True
