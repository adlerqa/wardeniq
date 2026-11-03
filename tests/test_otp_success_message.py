"""Regression coverage for the OTP-login false-success-message bug.

QA report: "incorrect Success Message Displayed When OTP Email Fails to Send" —
entering a (syntactically valid) email and clicking Send Code shows a success
message even though no OTP email ever arrives.

Root cause: `request_otp()` has three legitimate anti-enumeration / anti-abuse
branches — unrecognized email, deactivated account, rate-limited account — that
deliberately never attempt delivery and return the *same* `{"sent": True}` shape
a real send returns (so the endpoint can't be used to probe which accounts
exist or are being throttled; this masking itself is correct and intentional,
matching the pattern already used a few routes down in
`request_password_reset()`). The bug is narrower: the response carried no signal
that anything was skipped, and the frontend's hardcoded "Code sent. Check your
inbox." text is only true for a *real* send — so testers who (very naturally)
tried the flow with an email that wasn't already a registered, active account
saw an unconditional success claim and, correctly, no email.

The fix adds an honest, non-committal `message` field ("If an account exists
...") to every masked branch, and has the frontend prefer `r.message` over its
old hardcoded string. `sent` stays `True` and no branch is distinguishable from
another by response *shape* — only by wording that itself reveals nothing — so
the anti-enumeration property this code exists for is unaffected.

These tests call `request_otp()` directly (same FakeStore-monkeypatch pattern as
test_rbac_auth.py::TestSmtpAndPasswordLogin), not through a live server, but
they exercise the real function body end-to-end for each branch, including
confirming `_deliver_otp` is never invoked when nothing should be sent.
"""
import pytest
from fastapi import HTTPException


def _import_auth_routes():
    import os
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    old = Path.cwd()
    try:
        os.chdir(root / "app")
        import main  # noqa: WPS433
        return main._auth_routes
    finally:
        os.chdir(old)


class _FakeStore:
    """Mirrors the FakeStore used in test_rbac_auth.py, extended with an
    `active` flag per user and a scriptable otp_recent_issue_count so both new
    masked branches (inactive / rate-limited) can be driven directly."""

    def __init__(self):
        self.users = {}
        self.issue_count = 0
        self.otp_calls = []

    def get_user_by_email(self, email):
        return self.users.get(email)

    def create_user(self, email, name, role="viewer", active=True):
        u = {"id": "uid-" + email, "email": email, "name": name, "role": role,
             "active": active}
        self.users[email] = u
        return u

    def list_users(self):
        return list(self.users.values())

    def otp_recent_issue_count(self, uid, w, max_per_window=None):
        return self.issue_count

    def set_otp(self, uid, h, exp):
        self.otp_calls.append(uid)


@pytest.fixture(scope="module")
def auth_routes():
    return _import_auth_routes()


def _never_deliver(*a, **k):
    raise AssertionError("_deliver_otp must not be called when nothing should be sent")


class TestMaskedBranchesNeverClaimDelivery:
    """The three "nothing was attempted" branches must all: keep sent=True (so the
    response shape alone can't be used to enumerate accounts), never call
    _deliver_otp, and carry the same honest, non-committal message — never the
    confident "Code sent" text a real send gets."""

    def test_unregistered_email_with_existing_users(self, monkeypatch, auth_routes):
        fs = _FakeStore()
        # A real (valid-email) user already exists, so this is NOT the first-run
        # bootstrap case -- auth.is_valid_email("admin") is False, which is why
        # the fixture must use a real address here rather than the "admin" login.
        fs.create_user("someone-else@example.com", "Someone Else", "viewer")
        monkeypatch.setattr(auth_routes, "store", fs)
        monkeypatch.setattr(auth_routes, "_deliver_otp", _never_deliver)

        body = auth_routes.OtpRequestIn(email="nobody-registered@example.com")
        r = auth_routes.request_otp(body)

        assert r["sent"] is True
        assert r["message"] == auth_routes.OTP_MASKED_MESSAGE
        assert "dev_code" not in r
        assert "delivery" not in r
        assert fs.get_user_by_email("nobody-registered@example.com") is None

    def test_deactivated_account(self, monkeypatch, auth_routes):
        fs = _FakeStore()
        fs.create_user("disabled@example.com", "Disabled", "viewer", active=False)
        monkeypatch.setattr(auth_routes, "store", fs)
        monkeypatch.setattr(auth_routes, "_deliver_otp", _never_deliver)

        body = auth_routes.OtpRequestIn(email="disabled@example.com")
        r = auth_routes.request_otp(body)

        assert r == {"sent": True, "message": auth_routes.OTP_MASKED_MESSAGE}

    def test_rate_limited_account(self, monkeypatch, auth_routes):
        fs = _FakeStore()
        fs.create_user("busy@example.com", "Busy", "viewer", active=True)
        fs.issue_count = auth_routes.OTP_MAX_PER_WINDOW + 1
        monkeypatch.setattr(auth_routes, "store", fs)
        monkeypatch.setattr(auth_routes, "_deliver_otp", _never_deliver)

        body = auth_routes.OtpRequestIn(email="busy@example.com")
        r = auth_routes.request_otp(body)

        assert r == {"sent": True, "message": auth_routes.OTP_MASKED_MESSAGE}
        # And a genuine, un-throttled request for the same account DOES still
        # attempt delivery -- proves this isn't accidentally masking everyone.
        fs.issue_count = 0
        monkeypatch.setattr(auth_routes, "_deliver_otp",
                             lambda *a, **k: ("sent", ""))
        r2 = auth_routes.request_otp(body)
        assert r2["message"] == "Code sent. Check your inbox."


class TestRealDeliveryMessagesUnaffected:
    def test_successful_smtp_send_gets_confident_message(self, monkeypatch, auth_routes):
        fs = _FakeStore()
        fs.create_user("real@example.com", "Real", "viewer", active=True)
        monkeypatch.setattr(auth_routes, "store", fs)
        monkeypatch.setattr(auth_routes, "_deliver_otp", lambda *a, **k: ("sent", ""))

        body = auth_routes.OtpRequestIn(email="real@example.com")
        r = auth_routes.request_otp(body)

        assert r["sent"] is True
        assert r["delivery"] == "email"
        assert r["message"] == "Code sent. Check your inbox."
        assert "dev_code" not in r

    def test_dev_mode_still_returns_dev_code(self, monkeypatch, auth_routes):
        fs = _FakeStore()
        fs.create_user("dev@example.com", "Dev", "viewer", active=True)
        monkeypatch.setattr(auth_routes, "store", fs)
        monkeypatch.setattr(auth_routes, "_deliver_otp",
                             lambda *a, **k: ("logged", "482913"))

        body = auth_routes.OtpRequestIn(email="dev@example.com")
        r = auth_routes.request_otp(body)

        assert r["dev_code"] == "482913"
        assert r["delivery"] == "log"

    def test_send_failure_still_raises_502_not_a_false_success(self, monkeypatch, auth_routes):
        fs = _FakeStore()
        fs.create_user("broken-smtp@example.com", "Broken", "viewer", active=True)
        monkeypatch.setattr(auth_routes, "store", fs)
        monkeypatch.setattr(auth_routes, "_deliver_otp",
                             lambda *a, **k: ("error", "connection refused"))

        body = auth_routes.OtpRequestIn(email="broken-smtp@example.com")
        with pytest.raises(HTTPException) as exc_info:
            auth_routes.request_otp(body)
        assert exc_info.value.status_code == 502
