"""Hand-labelled ground truth for coverage-verdict and dedup accuracy.

HOW TO USE THIS
---------------
Each coverage example is a (feature, test cases, production code excerpts, expected
verdict per case) tuple where the expected verdict was decided BY A HUMAN reading the
code, not by the model. `run_eval.py` scores wardenIQ's actual output against these
labels, so a prompt tweak or a model swap produces a measurable delta instead of a
vibe.

The seed set below is deliberately small and honest about it: 20 coverage cases across
9 features and 10 dedup pairs, built from unambiguous situations where the correct
answer is not debatable. That is enough to catch regressions and to prove the harness
works, and STILL NOT enough to publish an accuracy figure from — it stays synthetic
and hand-built rather than drawn from real projects. To get a defensible number, add
20-30 real features from your own projects following the same shape — the fields are
documented in `CoverageExample` below. Cases where two reasonable engineers would
disagree should be left out rather than guessed at, since a noisy label is worse than
a missing one.

`HALLUCINATION_PROBES` are different in kind: they are adversarial by construction —
the model is scripted to cite files it was never shown, so a correct system MUST refuse
them. These need no human labelling and should always score 100%; a drop there is a
regression in the grounding layer itself.
"""

# --------------------------------------------------------------------------- shapes
# CoverageExample:
#   id            short stable identifier, used in the report
#   feature       feature name
#   requirement   the requirement text the cases were written from
#   excerpts      [{"repo","path","text"}] — the production code a reviewer would see
#   cases         [{"id","title","type","steps"}] — the suite under judgement
#   expected      {case_id: "covered"|"partial"|"uncovered"} — HUMAN ground truth
#   note          why the label is what it is (keep this; it is the audit trail)

_LOGIN_CODE = """\
from fastapi import APIRouter, HTTPException
router = APIRouter()

@router.post("/api/login")
def login(payload):
    user = authenticate(payload["email"], payload["password"])
    if not user:
        raise HTTPException(401, "invalid credentials")
    return {"token": issue_session(user)}

@router.post("/api/logout")
def logout(session_id):
    revoke_session(session_id)
    return {"ok": True}
"""

_RATE_LIMIT_PARTIAL = """\
WINDOW_SECONDS = 60

def record_attempt(email):
    # counts attempts but does not yet reject once the limit is exceeded
    _attempts.setdefault(email, []).append(now())
"""

COVERAGE_EXAMPLES = [
    {
        "id": "auth-login-covered",
        "feature": "User authentication",
        "requirement": "Users log in with email and password and receive a session "
                       "token. Bad credentials are rejected with 401. Users can log out, "
                       "which revokes the session. Accounts can be deleted.",
        "excerpts": [{"repo": "api", "path": "app/auth/login.py", "text": _LOGIN_CODE}],
        "cases": [
            {"id": "ev-login-ok", "title": "Login with valid credentials issues a session",
             "type": "functional",
             "steps": [{"action": "POST /api/login with valid creds",
                        "expected": "200 and a session token"}]},
            {"id": "ev-login-401", "title": "Login with bad credentials is rejected",
             "type": "functional",
             "steps": [{"action": "POST /api/login with a wrong password",
                        "expected": "401 invalid credentials"}]},
            {"id": "ev-logout", "title": "Logout revokes the active session",
             "type": "functional",
             "steps": [{"action": "POST /api/logout", "expected": "session revoked"}]},
            {"id": "ev-delete", "title": "Delete account removes all user data",
             "type": "functional",
             "steps": [{"action": "DELETE /api/account", "expected": "user data purged"}]},
        ],
        "expected": {
            "ev-login-ok": "covered",     # login() authenticates and issues a session
            "ev-login-401": "covered",    # explicit HTTPException(401, ...)
            "ev-logout": "covered",       # logout() calls revoke_session
            "ev-delete": "uncovered",     # no delete/account code anywhere in the excerpt
        },
        "note": "Three behaviours are visibly implemented in the excerpt; account "
                "deletion appears in the requirement but has no implementing code, so a "
                "correct reviewer must call it uncovered rather than assuming it exists.",
    },
    {
        "id": "rate-limit-partial",
        "feature": "Login rate limiting",
        "requirement": "After 5 failed login attempts within 60 seconds the account is "
                       "locked and further attempts return 429.",
        "excerpts": [{"repo": "api", "path": "app/auth/throttle.py",
                      "text": _RATE_LIMIT_PARTIAL}],
        "cases": [
            {"id": "ev-rl-counts", "title": "Failed attempts are recorded per account",
             "type": "functional",
             "steps": [{"action": "fail a login", "expected": "the attempt is recorded"}]},
            {"id": "ev-rl-429", "title": "Sixth attempt in the window returns 429",
             "type": "functional",
             "steps": [{"action": "fail six logins in under a minute",
                        "expected": "429 too many requests"}]},
        ],
        "expected": {
            "ev-rl-counts": "covered",    # record_attempt() does exactly this
            "ev-rl-429": "uncovered",     # nothing rejects; the code comment says so
        },
        "note": "The relevant module exists and the counting half is implemented, but "
                "there is no rejection path — so the 429 behaviour is not covered. This "
                "example exists to catch a reviewer that marks a case covered because "
                "the surrounding area 'looks handled'.",
    },
    {
        "id": "empty-excerpts",
        "feature": "Reporting export",
        "requirement": "Users can export a report as PDF.",
        "excerpts": [],
        "cases": [
            {"id": "ev-export", "title": "Export produces a PDF", "type": "functional",
             "steps": [{"action": "click export", "expected": "a PDF downloads"}]},
        ],
        "expected": {"ev-export": "uncovered"},
        "note": "No code retrieved at all. The only defensible verdict is uncovered; "
                "anything else is the model inventing an implementation.",
    },
    {
        "id": "password-reset-partial",
        "feature": "Password reset",
        "requirement": "Users can request a password reset by email and receive a reset "
                       "link. They can then submit a new password with that token to "
                       "complete the reset. Reset tokens expire after 1 hour.",
        "excerpts": [{"repo": "api", "path": "app/auth/password_reset.py", "text": """\
from fastapi import APIRouter
router = APIRouter()

@router.post("/api/auth/request-password-reset")
def request_reset(payload):
    token = generate_reset_token(payload["email"])
    send_reset_email(payload["email"], token)
    return {"ok": True}
"""}],
        "cases": [
            {"id": "ev-pwreset-request", "title": "Requesting a reset sends an email with a token",
             "type": "functional",
             "steps": [{"action": "POST /api/auth/request-password-reset with an email",
                        "expected": "a reset email is sent"}]},
            {"id": "ev-pwreset-confirm", "title": "Submitting a new password with a valid token completes the reset",
             "type": "functional",
             "steps": [{"action": "POST the new password with the reset token",
                        "expected": "the password is updated"}]},
            {"id": "ev-pwreset-expiry", "title": "An expired reset token is rejected",
             "type": "functional",
             "steps": [{"action": "submit a reset token older than 1 hour",
                        "expected": "the reset is rejected"}]},
        ],
        "expected": {
            "ev-pwreset-request": "covered",     # request_reset() does exactly this
            "ev-pwreset-confirm": "uncovered",    # no confirm/complete endpoint in the excerpt
            "ev-pwreset-expiry": "uncovered",     # no expiry check anywhere in the excerpt
        },
        "note": "Only the request half of a two-step flow is implemented here. A "
                "reviewer that infers the confirm step exists because the request step "
                "does is exactly the overclaiming failure this dataset exists to catch.",
    },
    {
        "id": "csv-export-covered",
        "feature": "Report export",
        "requirement": "Users can export a report as CSV from the report detail page.",
        "excerpts": [{"repo": "api", "path": "app/reports/export.py", "text": """\
from fastapi import APIRouter, HTTPException, Response
router = APIRouter()

@router.get("/api/reports/{report_id}/export")
def export_report(report_id, format: str = "csv"):
    rows = fetch_report_rows(report_id)
    if format == "csv":
        return Response(to_csv(rows), media_type="text/csv")
    raise HTTPException(400, "unsupported format")
"""}],
        "cases": [
            {"id": "ev-export-csv", "title": "Exporting a report as CSV downloads a CSV file",
             "type": "functional",
             "steps": [{"action": "GET /api/reports/{id}/export?format=csv",
                        "expected": "a CSV file is returned"}]},
        ],
        "expected": {"ev-export-csv": "covered"},  # explicit format=="csv" branch returns CSV
        "note": "Single, unambiguous behaviour with a directly matching code path — a "
                "control example for the covered case in a non-auth domain.",
    },
    {
        "id": "pagination-partial",
        "feature": "Project list pagination",
        "requirement": "The projects list supports page/page_size query params. The "
                       "response includes a total X-Total-Count header so clients can "
                       "render pagination controls.",
        "excerpts": [{"repo": "api", "path": "app/projects/list.py", "text": """\
from fastapi import APIRouter
router = APIRouter()

@router.get("/api/projects")
def list_projects(page: int = 1, page_size: int = 20):
    items = db.projects.find().skip((page - 1) * page_size).limit(page_size)
    return {"items": list(items)}
"""}],
        "cases": [
            {"id": "ev-page-params", "title": "page and page_size control the returned slice",
             "type": "functional",
             "steps": [{"action": "GET /api/projects?page=2&page_size=10",
                        "expected": "the second page of 10 projects is returned"}]},
            {"id": "ev-page-total-count", "title": "Response includes an X-Total-Count header",
             "type": "functional",
             "steps": [{"action": "GET /api/projects", "expected": "X-Total-Count header is present"}]},
        ],
        "expected": {
            "ev-page-params": "covered",        # skip/limit is driven directly by the params
            "ev-page-total-count": "uncovered",  # no header, no total count anywhere in the excerpt
        },
        "note": "The slicing half of pagination is implemented; the total-count header "
                "the requirement also asks for is not — a case designed to catch a "
                "reviewer that marks the whole feature covered because part of it works.",
    },
    {
        "id": "rbac-admin-only-partial",
        "feature": "Admin-only user list",
        "requirement": "Only admins can list all users via /api/admin/users; other "
                       "roles receive 403.",
        "excerpts": [{"repo": "api", "path": "app/admin/users.py", "text": """\
from fastapi import APIRouter, Depends
router = APIRouter()

@router.get("/api/admin/users")
def list_all_users(current_user=Depends(require_role("admin"))):
    return {"users": db.users.find_all()}
"""}],
        "cases": [
            {"id": "ev-rbac-admin-list", "title": "An admin can list all users",
             "type": "functional",
             "steps": [{"action": "GET /api/admin/users as an admin",
                        "expected": "200 with the full user list"}]},
            {"id": "ev-rbac-non-admin-403", "title": "A non-admin listing users receives 403",
             "type": "functional",
             "steps": [{"action": "GET /api/admin/users as a non-admin",
                        "expected": "403 forbidden"}]},
        ],
        "expected": {
            "ev-rbac-admin-list": "covered",       # require_role("admin") gates the route
            "ev-rbac-non-admin-403": "uncovered",  # require_role's own body/status isn't in this excerpt
        },
        "note": "The dependency clearly restricts the route to admins, so the happy path "
                "is covered. But require_role()'s implementation — and specifically "
                "whether it returns 403 — is not shown in this excerpt, so a reviewer "
                "cannot cite evidence for the 403 case without inventing it.",
    },
    {
        "id": "webhook-retry-partial",
        "feature": "Webhook delivery retries",
        "requirement": "Webhook deliveries are retried on failure. After repeated "
                       "failures, retries back off exponentially, and delivery is "
                       "abandoned once a maximum total delay is reached.",
        "excerpts": [{"repo": "api", "path": "app/webhooks/deliver.py", "text": """\
import httpx

MAX_RETRIES = 3

def deliver_webhook(url, payload):
    for attempt in range(MAX_RETRIES):
        try:
            r = httpx.post(url, json=payload, timeout=5.0)
            if r.status_code < 300:
                return True
        except httpx.RequestError:
            continue
    return False
"""}],
        "cases": [
            {"id": "ev-webhook-retry", "title": "A failed delivery is retried",
             "type": "functional",
             "steps": [{"action": "the endpoint fails once", "expected": "delivery is retried"}]},
            {"id": "ev-webhook-backoff", "title": "Retries back off exponentially",
             "type": "functional",
             "steps": [{"action": "the endpoint fails repeatedly",
                        "expected": "the delay between retries grows"}]},
            {"id": "ev-webhook-ceiling", "title": "Delivery is abandoned past the max total delay",
             "type": "functional",
             "steps": [{"action": "the endpoint keeps failing past the delay ceiling",
                        "expected": "delivery stops being retried"}]},
        ],
        "expected": {
            "ev-webhook-retry": "covered",       # the for-loop retries up to MAX_RETRIES
            "ev-webhook-backoff": "uncovered",   # fixed retry count, no growing delay anywhere
            "ev-webhook-ceiling": "uncovered",   # no delay/time-based ceiling concept exists
        },
        "note": "A fixed retry count is not exponential backoff and is not a delay-based "
                "ceiling — two behaviours the requirement names explicitly that this code "
                "does not implement, despite 'it retries' being superficially true.",
    },
    {
        "id": "empty-excerpts-notifications",
        "feature": "Notification preferences",
        "requirement": "Users can configure which notification types they receive by "
                       "email versus in-app.",
        "excerpts": [],
        "cases": [
            {"id": "ev-notif-prefs", "title": "Users can toggle email vs in-app notifications",
             "type": "functional",
             "steps": [{"action": "open notification settings and toggle a channel",
                        "expected": "the preference is saved"}]},
        ],
        "expected": {"ev-notif-prefs": "uncovered"},
        "note": "Same class as 'empty-excerpts' in a different domain: no code retrieved "
                "means the only defensible verdict is uncovered.",
    },
]

# --------------------------------------------------------------------------- adversarial
# Scripted model replies that MUST be caught by the grounding layer. `expected_status`
# is what the system should report after grounding, regardless of what the model claimed.
HALLUCINATION_PROBES = [
    {
        "id": "probe-invented-path",
        "excerpts": [{"repo": "api", "path": "app/auth/login.py", "text": _LOGIN_CODE}],
        "claim": {"status": "covered", "confidence": 0.95,
                  "rationale": "implemented in the session service",
                  "files": ["api:app/auth/session_service.py"]},
        "expected_status": "partial",
        "expect_rejected_citation": True,
        "note": "Plausible-sounding path that was never shown. Classic hallucination.",
    },
    {
        "id": "probe-no-citation",
        "excerpts": [{"repo": "api", "path": "app/auth/login.py", "text": _LOGIN_CODE}],
        "claim": {"status": "covered", "confidence": 0.9,
                  "rationale": "the code handles this", "files": []},
        "expected_status": "partial",
        "expect_rejected_citation": False,
        "note": "Confident claim with nothing to point at.",
    },
    {
        "id": "probe-absent-symbol",
        "excerpts": [{"repo": "api", "path": "app/auth/login.py", "text": _LOGIN_CODE}],
        "claim": {"status": "covered", "confidence": 0.9,
                  "rationale": "`rotate_refresh_token()` handles the rotation",
                  "files": ["api:app/auth/login.py"]},
        "expected_status": "partial",
        "expect_rejected_citation": False,
        "note": "Real file, but the named function does not exist in it.",
    },
    {
        "id": "probe-ambiguous-basename",
        "excerpts": [
            {"repo": "api", "path": "svc/a/handler.py", "text": "def go(): pass"},
            {"repo": "api", "path": "svc/b/handler.py", "text": "def go(): pass"},
        ],
        "claim": {"status": "covered", "confidence": 0.9,
                  "rationale": "handled in handler", "files": ["handler.py"]},
        "expected_status": "partial",
        "expect_rejected_citation": True,
        "note": "Ambiguous citation must not be laundered into evidence by picking one.",
    },
    {
        "id": "probe-honest-covered",
        "excerpts": [{"repo": "api", "path": "app/auth/login.py", "text": _LOGIN_CODE}],
        "claim": {"status": "covered", "confidence": 0.9,
                  "rationale": "`login()` calls `issue_session` after authenticate",
                  "files": ["api:app/auth/login.py"]},
        "expected_status": "covered",
        "expect_rejected_citation": False,
        "note": "CONTROL: a properly evidenced verdict must survive untouched. If this "
                "one degrades, the grounding layer is too aggressive and will destroy "
                "true positives.",
    },
    {
        "id": "probe-invented-path-2",
        "excerpts": [{"repo": "api", "path": "app/webhooks/deliver.py", "text": """\
import httpx

MAX_RETRIES = 3

def deliver_webhook(url, payload):
    for attempt in range(MAX_RETRIES):
        try:
            r = httpx.post(url, json=payload, timeout=5.0)
            if r.status_code < 300:
                return True
        except httpx.RequestError:
            continue
    return False
"""}],
        "claim": {"status": "covered", "confidence": 0.92,
                  "rationale": "handled by the retry queue",
                  "files": ["api:app/webhooks/retry_queue.py"]},
        "expected_status": "partial",
        "expect_rejected_citation": True,
        "note": "Second invented-path probe in a non-auth domain, so this class isn't "
                "only exercised against login code.",
    },
    {
        "id": "probe-absent-symbol-2",
        "excerpts": [{"repo": "api", "path": "app/webhooks/deliver.py", "text": """\
import httpx

MAX_RETRIES = 3

def deliver_webhook(url, payload):
    for attempt in range(MAX_RETRIES):
        try:
            r = httpx.post(url, json=payload, timeout=5.0)
            if r.status_code < 300:
                return True
        except httpx.RequestError:
            continue
    return False
"""}],
        "claim": {"status": "covered", "confidence": 0.9,
                  "rationale": "`apply_exponential_backoff()` spaces out retries",
                  "files": ["api:app/webhooks/deliver.py"]},
        "expected_status": "partial",
        "expect_rejected_citation": False,
        "note": "Real file, but the named function does not exist in it — same class "
                "as probe-absent-symbol, different domain.",
    },
    {
        "id": "probe-honest-covered-2",
        "excerpts": [{"repo": "api", "path": "app/webhooks/deliver.py", "text": """\
import httpx

MAX_RETRIES = 3

def deliver_webhook(url, payload):
    for attempt in range(MAX_RETRIES):
        try:
            r = httpx.post(url, json=payload, timeout=5.0)
            if r.status_code < 300:
                return True
        except httpx.RequestError:
            continue
    return False
"""}],
        "claim": {"status": "covered", "confidence": 0.9,
                  "rationale": "`deliver_webhook()` retries up to MAX_RETRIES times",
                  "files": ["api:app/webhooks/deliver.py"]},
        "expected_status": "covered",
        "expect_rejected_citation": False,
        "note": "Second positive control, non-auth domain — checks the grounding layer "
                "isn't tuned specifically to auth-shaped evidence.",
    },
]

# --------------------------------------------------------------------------- dedup pairs
# expected_same=True  -> these two SHOULD be treated as the same case (reuse/merge)
# expected_same=False -> these two are genuinely different and must NOT be merged
DEDUP_PAIRS = [
    {
        "id": "same-wording-drift",
        "a": {"category": "api_tests", "method": "POST", "endpoint": "/api/login",
              "title": "Login with valid credentials returns a token",
              "expected_result": {"status_code": 200},
              "steps": [{"content": "POST /api/login with valid creds",
                         "expectedResult": "200 and a token"}]},
        "b": {"category": "api_tests", "method": "POST", "endpoint": "/api/login",
              "title": "Valid credentials log the user in and return a token",
              "expected_result": {"status_code": 200},
              "steps": [{"content": "send a POST to /api/login with good credentials",
                         "expectedResult": "200 with a token"}]},
        "expected_same": True,
        "note": "Same endpoint, same status, same behaviour, different phrasing.",
    },
    {
        "id": "diff-status-same-endpoint",
        "a": {"category": "api_tests", "method": "POST", "endpoint": "/api/login",
              "title": "Valid credentials return 200",
              "expected_result": {"status_code": 200},
              "steps": [{"content": "valid creds", "expectedResult": "200"}]},
        "b": {"category": "api_tests", "method": "POST", "endpoint": "/api/login",
              "title": "Invalid credentials return 401",
              "expected_result": {"status_code": 401},
              "steps": [{"content": "bad creds", "expectedResult": "401"}]},
        "expected_same": False,
        "note": "Happy path vs auth failure on the same route — merging these loses a "
                "whole behaviour. The scenario-kind guard should stop it.",
    },
    {
        "id": "diff-method-same-path",
        "a": {"category": "api_tests", "method": "GET", "endpoint": "/api/events",
              "title": "List events", "expected_result": {"status_code": 200},
              "steps": [{"content": "GET /api/events", "expectedResult": "200 list"}]},
        "b": {"category": "api_tests", "method": "POST", "endpoint": "/api/events",
              "title": "Create event", "expected_result": {"status_code": 201},
              "steps": [{"content": "POST /api/events", "expectedResult": "201 created"}]},
        "expected_same": False,
        "note": "Read vs write on one path.",
    },
    {
        "id": "same-path-id-normalized",
        "a": {"category": "api_tests", "method": "GET", "endpoint": "/api/users/42",
              "title": "Fetch a user by id", "expected_result": {"status_code": 200},
              "steps": [{"content": "GET /api/users/42", "expectedResult": "200 user"}]},
        "b": {"category": "api_tests", "method": "GET", "endpoint": "/api/users/99",
              "title": "Fetch a user by id", "expected_result": {"status_code": 200},
              "steps": [{"content": "GET /api/users/99", "expectedResult": "200 user"}]},
        "expected_same": True,
        "note": "Concrete ids must normalize to {id} — otherwise every id spawns a "
                "duplicate case.",
    },
    {
        "id": "diff-404-vs-403",
        "a": {"category": "api_tests", "method": "GET", "endpoint": "/api/users/{id}",
              "title": "Unknown user returns 404", "expected_result": {"status_code": 404},
              "steps": [{"content": "GET a missing id", "expectedResult": "404"}]},
        "b": {"category": "api_tests", "method": "GET", "endpoint": "/api/users/{id}",
              "title": "Other user's record is forbidden",
              "expected_result": {"status_code": 403},
              "steps": [{"content": "GET another user's id", "expectedResult": "403"}]},
        "expected_same": False,
        "note": "not_found vs forbidden are distinct scenario kinds.",
    },
    {
        "id": "same-wording-drift-export",
        "a": {"category": "api_tests", "method": "POST", "endpoint": "/api/reports/export",
              "title": "Export report as PDF succeeds",
              "expected_result": {"status_code": 200},
              "steps": [{"content": "POST /api/reports/export with format=pdf",
                         "expectedResult": "200 and a PDF file is returned"}]},
        "b": {"category": "api_tests", "method": "POST", "endpoint": "/api/reports/export",
              "title": "Successfully exporting a report generates a PDF",
              "expected_result": {"status_code": 200},
              "steps": [{"content": "send a POST to /api/reports/export requesting PDF format",
                         "expectedResult": "response is 200 with a PDF file"}]},
        "expected_same": True,
        "note": "Same endpoint, same status, same behaviour, different phrasing — a "
                "second instance of this class in a non-login domain.",
    },
    {
        "id": "diff-role-same-endpoint",
        "a": {"category": "api_tests", "method": "GET", "endpoint": "/api/admin/users",
              "title": "Admin can list all users",
              "expected_result": {"status_code": 200},
              "steps": [{"content": "GET /api/admin/users as an admin",
                         "expectedResult": "200 list of users"}]},
        "b": {"category": "api_tests", "method": "GET", "endpoint": "/api/admin/users",
              "title": "Non-admin listing users is forbidden",
              "expected_result": {"status_code": 403},
              "steps": [{"content": "GET /api/admin/users as a non-admin",
                         "expectedResult": "403 forbidden"}]},
        "expected_same": False,
        "note": "Happy path vs a role-based rejection on the same route — merging these "
                "loses the 403 behaviour entirely.",
    },
    {
        "id": "diff-method-same-resource-2",
        "a": {"category": "api_tests", "method": "PATCH", "endpoint": "/api/projects/7",
              "title": "Update project name", "expected_result": {"status_code": 200},
              "steps": [{"content": "PATCH /api/projects/7 with a new name",
                         "expectedResult": "200 updated"}]},
        "b": {"category": "api_tests", "method": "DELETE", "endpoint": "/api/projects/7",
              "title": "Delete project", "expected_result": {"status_code": 204},
              "steps": [{"content": "DELETE /api/projects/7", "expectedResult": "204 removed"}]},
        "expected_same": False,
        "note": "Update vs delete on one resource — a second write/write pair distinct "
                "from the existing read/write example.",
    },
    {
        "id": "same-path-id-normalized-2",
        "a": {"category": "api_tests", "method": "GET",
              "endpoint": "/api/projects/12/features/55",
              "title": "Fetch a feature by id", "expected_result": {"status_code": 200},
              "steps": [{"content": "GET /api/projects/12/features/55",
                         "expectedResult": "200 feature"}]},
        "b": {"category": "api_tests", "method": "GET",
              "endpoint": "/api/projects/12/features/77",
              "title": "Fetch a feature by id", "expected_result": {"status_code": 200},
              "steps": [{"content": "GET /api/projects/12/features/77",
                         "expectedResult": "200 feature"}]},
        "expected_same": True,
        "note": "Second id-normalization instance, on a nested resource path rather "
                "than a top-level one.",
    },
    {
        "id": "diff-restore-vs-purge-project",
        # Written out directly (not via the _functional() helper below) because that
        # helper is defined further down in this module, after DEDUP_PAIRS.
        "a": {"category": "business_tests", "title": "A soft-deleted project can be restored",
              "steps": [{"content": "restore a soft-deleted project",
                         "expectedResult": "the project is active again"}]},
        "b": {"category": "business_tests", "title": "A soft-deleted project can be permanently purged",
              "steps": [{"content": "purge a soft-deleted project",
                         "expectedResult": "the project is permanently removed"}]},
        "expected_same": False,
        "note": "Non-API pair, unlike every other entry in this list: restore and purge "
                "are opposite, non-reversible outcomes on the same object. Measured "
                "similarity is 0.333 — well under the 0.65 general threshold — so this "
                "one is genuinely decidable rather than a known-limitation case.",
    },
]


def _functional(title, action, expected):
    return {"category": "business_tests", "title": title,
            "steps": [{"content": action, "expectedResult": expected}]}


# --------------------------------------------------------------------------- known limits
# MEASURED FINDING — read this before touching REUSE_SIMILARITY_GENERAL.
#
# Non-API cases have no structural key (no method, no endpoint, no status code), so the
# reuse decision rests entirely on token-set Jaccard similarity. Measured against the
# pairs below, that metric CANNOT separate duplicates from distinct behaviours, because
# the two classes overlap:
#
#     genuinely the SAME, reworded ................ 0.500
#     genuinely DIFFERENT (delete user/project) ... 0.833   <-- higher than the same pair
#     genuinely DIFFERENT (export PDF/CSV) ........ 0.750   <-- higher than the same pair
#     genuinely DIFFERENT (login/password reset) .. 0.444
#     genuinely DIFFERENT (session 30min/24h) ..... 0.286
#
# Consequences, stated plainly:
#   * No threshold merges the 0.500 pair while keeping the 0.833 and 0.750 pairs apart.
#   * The shipped default (0.65) sits BELOW 0.750, so the two distinct pairs below can be
#     merged — a FALSE MERGE, which silently destroys a test case and is the worse error
#     direction. (In production a candidate must also clear the 0.93 embedding gate first,
#     so this needs both filters to agree before it bites; it is a real risk, not a
#     guaranteed bug.)
#   * Raising the constant toward ~0.9 removes those false merges at the cost of more
#     duplicates — duplicates being the recoverable error. That is a product trade-off,
#     so the default is left alone and the knob (WARDENIQ_REUSE_SIM_GENERAL) plus this
#     measurement are provided instead of a silent change.
#
# The durable fix is not a better threshold: it is a discriminator that notices the two
# cases act on DIFFERENT DOMAIN OBJECTS ('project' vs a stopworded 'user', 'pdf' vs
# 'csv'). That needs designing and validating against far more than five pairs, so it is
# deliberately not attempted here.
#
# These pairs are reported by the eval, not scored, so they can't be "fixed" by tuning a
# number until the suite goes green.
KNOWN_LIMITATION_PAIRS = [
    {
        "id": "limit-same-functional-rewording",
        "a": _functional("A locked account cannot log in",
                         "attempt login on a locked account",
                         "login is refused and the reason is shown"),
        "b": _functional("Locked accounts are refused login",
                         "try to log in while the account is locked",
                         "the login is refused, showing the reason"),
        "expected_same": True,
        "note": "Same behaviour, different words. Scores 0.50 — under the 0.65 default, "
                "so it is NOT merged and a duplicate is created. Safe error, but a miss.",
    },
    {
        "id": "limit-diff-delete-object",
        "a": _functional("Admin can delete a user", "admin deletes a user",
                         "the user is removed"),
        "b": _functional("Admin can delete a project", "admin deletes a project",
                         "the project is removed"),
        "expected_same": False,
        "note": "Different objects, same verb. Scores 0.833 — ABOVE the default, so these "
                "can be wrongly merged. Note 'user'/'users' are stopwords, which strips "
                "the very noun that distinguishes them.",
    },
    {
        "id": "limit-diff-export-format",
        "a": _functional("Export report as PDF", "click export and choose PDF",
                         "a PDF file downloads"),
        "b": _functional("Export report as CSV", "click export and choose CSV",
                         "a CSV file downloads"),
        "expected_same": False,
        "note": "Different formats. Scores 0.750 — ABOVE the default; wrongly mergeable.",
    },
    {
        "id": "limit-diff-locked-login-vs-reset",
        "a": _functional("A locked account cannot log in",
                         "attempt login on a locked account", "login is refused"),
        "b": _functional("A locked account cannot reset its password",
                         "request a password reset on a locked account",
                         "the reset is refused"),
        "expected_same": False,
        "note": "Scores 0.444 — correctly kept apart at the default.",
    },
    {
        "id": "limit-diff-session-expiry-rule",
        "a": _functional("Session expires after 30 minutes idle",
                         "wait 30 minutes without activity", "the session expires"),
        "b": _functional("Session expires after 24 hours regardless of activity",
                         "stay active for 24 hours", "the session expires"),
        "expected_same": False,
        "note": "Scores 0.286 — correctly kept apart at the default.",
    },
    {
        "id": "limit-same-csv-export-reword",
        "a": _functional("Exporting a report as CSV downloads the file",
                         "click export and choose CSV format", "a CSV file is downloaded"),
        "b": _functional("Choosing CSV export downloads a CSV file",
                         "click export, choose CSV format", "a CSV file downloads"),
        "expected_same": True,
        "note": "Same behaviour, different wording — scores 0.636, just under the 0.65 "
                "default, so it is NOT merged and a duplicate is created. A near-miss "
                "companion to limit-same-functional-rewording's 0.500: shows the "
                "threshold has a false-negative edge even for close paraphrases, not "
                "just loosely-worded ones. Safe error (a duplicate, not a false merge), "
                "but still a miss.",
    },
]
