"""Password sign-in accepts an email address, not just the literal `admin`.

The sign-in form is labelled "Username or email", and /api/auth/reset-password
already sets a password on ANY user resolved by email — so login-password must
accept those users too. It previously hard-compared `username != "admin"` and
rejected them, leaving a user who had just reset their password unable to sign in.

These tests pin both halves: email sign-in works, and the paths that must NOT
grant access (no password set, unknown account, wrong password, SMTP configured)
still fail closed.
"""
import importlib
import sys

import pytest


class FakeStore:
    """Minimal users store. Mirrors the real get_user_by_email(), which strips and
    lowercases — the bootstrap admin row's email IS the string "admin"."""

    def __init__(self, users=None):
        self.users = {}
        for u in users or []:
            self.users[u["email"]] = u
        self.touched = []

    def get_user_by_email(self, email):
        return self.users.get((email or "").strip().lower())

    def has_users(self):
        return bool(self.users)

    def create_user(self, email, name, role):
        u = {"id": f"id-{email}", "email": email, "name": name, "role": role,
             "active": True, "session_version": 0}
        self.users[email] = u
        return u

    def get_user(self, uid):
        return next((u for u in self.users.values() if u["id"] == uid), None)

    def touch_login(self, uid):
        self.touched.append(uid)

    def set_user_password(self, uid, password_hash):
        u = self.get_user(uid)
        u["password_hash"] = password_hash
        u["session_version"] = u.get("session_version", 0) + 1
        return u


class FakeResponse:
    def __init__(self):
        self.cookies = {}

    def set_cookie(self, name, value, **kwargs):
        self.cookies[name] = value


@pytest.fixture
def routes():
    sys.path.insert(0, "app")
    mod = importlib.import_module("api.routes.auth")
    return mod


def _user(email, role="admin", password_hash=None, active=True):
    u = {"id": f"id-{email}", "email": email, "name": email.split("@")[0],
         "role": role, "active": active, "session_version": 0}
    if password_hash:
        u["password_hash"] = password_hash
    return u


def _login(routes, monkeypatch, store, username, password):
    monkeypatch.setattr(routes, "_smtp_cfg", lambda: None)
    monkeypatch.setattr(routes, "store", store)
    body = routes.LoginPasswordIn(username=username, password=password)
    return routes.login_password(body, FakeResponse())


# --------------------------------------------------------------- the fix itself
def test_email_account_with_a_password_can_sign_in(routes, monkeypatch):
    """The regression this fixes: an email user with a password was rejected."""
    import auth
    pw = "Str0ngPassw0rd"
    store = FakeStore([_user("jayesh@adlerqa.in", password_hash=auth.hash_password(pw))])
    r = _login(routes, monkeypatch, store, "jayesh@adlerqa.in", pw)
    assert r["user"]["email"] == "jayesh@adlerqa.in"


def test_email_lookup_is_case_insensitive(routes, monkeypatch):
    import auth
    pw = "Str0ngPassw0rd"
    store = FakeStore([_user("jayesh@adlerqa.in", password_hash=auth.hash_password(pw))])
    r = _login(routes, monkeypatch, store, "  Jayesh@AdlerQA.in  ", pw)
    assert r["user"]["email"] == "jayesh@adlerqa.in"


def test_bootstrap_admin_username_still_works(routes, monkeypatch):
    """The `admin` username must keep working — it's the documented first login."""
    import auth
    pw = "Str0ngPassw0rd"
    store = FakeStore([_user("admin", password_hash=auth.hash_password(pw))])
    r = _login(routes, monkeypatch, store, "admin", pw)
    assert r["user"]["email"] == "admin"


def test_first_boot_bootstraps_admin_from_default(routes, monkeypatch):
    store = FakeStore()
    r = _login(routes, monkeypatch, store, "admin", routes.DEFAULT_ADMIN_PASSWORD)
    assert r["user"]["email"] == "admin"
    assert r["user"]["role"] == "admin"


# ------------------------------------------------------------- must fail closed
def test_email_account_without_a_password_cannot_sign_in(routes, monkeypatch):
    """OTP-only accounts (seeded from ADMIN_EMAIL) have no password_hash. An empty
    or guessed password must not let them in, and the shipped admin123 default
    must NOT apply to them — it's only for the bootstrap `admin` row."""
    store = FakeStore([_user("jayesh@adlerqa.in")])
    for attempt in ("", "admin123", routes.DEFAULT_ADMIN_PASSWORD, "anything"):
        with pytest.raises(routes.HTTPException) as exc:
            _login(routes, monkeypatch, store, "jayesh@adlerqa.in", attempt)
        assert exc.value.status_code == 401
        assert exc.value.detail == "Invalid username or password"


def test_unknown_account_is_rejected(routes, monkeypatch):
    store = FakeStore([_user("admin")])
    with pytest.raises(routes.HTTPException) as exc:
        _login(routes, monkeypatch, store, "nobody@example.com", "whatever")
    assert exc.value.status_code == 401


def test_unknown_account_cannot_bootstrap_itself_with_the_default(routes, monkeypatch):
    """Only the `admin` username may create the bootstrap row on first boot."""
    store = FakeStore()
    with pytest.raises(routes.HTTPException) as exc:
        _login(routes, monkeypatch, store, "attacker@example.com",
               routes.DEFAULT_ADMIN_PASSWORD)
    assert exc.value.status_code == 401
    assert exc.value.detail == "Invalid username or password"
    assert store.users == {}


def test_wrong_password_is_rejected(routes, monkeypatch):
    import auth
    store = FakeStore([_user("jayesh@adlerqa.in",
                             password_hash=auth.hash_password("Str0ngPassw0rd"))])
    with pytest.raises(routes.HTTPException) as exc:
        _login(routes, monkeypatch, store, "jayesh@adlerqa.in", "wrong")
    assert exc.value.status_code == 401


def test_seeded_password_disables_the_shipped_default(routes, monkeypatch):
    """Once a real password exists, admin123 must stop working."""
    import auth
    store = FakeStore([_user("admin", password_hash=auth.hash_password("Str0ngPassw0rd"))])
    with pytest.raises(routes.HTTPException) as exc:
        _login(routes, monkeypatch, store, "admin", "admin123")
    assert exc.value.status_code == 401


def test_deactivated_account_is_rejected(routes, monkeypatch):
    import auth
    pw = "Str0ngPassw0rd"
    store = FakeStore([_user("jayesh@adlerqa.in", password_hash=auth.hash_password(pw),
                             active=False)])
    with pytest.raises(routes.HTTPException) as exc:
        _login(routes, monkeypatch, store, "jayesh@adlerqa.in", pw)
    assert exc.value.status_code == 401
    assert "deactivated" in exc.value.detail


def test_password_login_disabled_once_smtp_is_configured(routes, monkeypatch):
    import auth
    pw = "Str0ngPassw0rd"
    store = FakeStore([_user("jayesh@adlerqa.in", password_hash=auth.hash_password(pw))])
    monkeypatch.setattr(routes, "_smtp_cfg", lambda: {"host": "smtp.gmail.com"})
    monkeypatch.setattr(routes, "store", store)
    body = routes.LoginPasswordIn(username="jayesh@adlerqa.in", password=pw)
    with pytest.raises(routes.HTTPException) as exc:
        routes.login_password(body, FakeResponse())
    assert exc.value.status_code == 400
    assert "Password login is disabled" in exc.value.detail


# ---------------------------------------------------- change-password (companion)
# Any account that HAS a password can rotate it in-app. Previously this route
# hard-blocked `email != "admin"`, so an email account given a password by the
# ADMIN_PASSWORD seed could sign in but never change its own password.
class FakeRequest:
    def __init__(self):
        self.state = type("S", (), {})()
        self.client = type("C", (), {"host": "127.0.0.1"})()
        self.headers = {}
        self.url = type("U", (), {"path": "/api/auth/change-password"})()
        self.method = "POST"


def _change(routes, monkeypatch, store, actor, current, new):
    monkeypatch.setattr(routes, "store", store)
    monkeypatch.setattr(routes, "_current_user", lambda req: actor)
    monkeypatch.setattr(routes, "_audit", lambda *a, **k: None)
    body = routes.ChangePasswordIn(current_password=current, new_password=new)
    return routes.change_password(body, FakeRequest(), FakeResponse())


def test_email_account_with_a_password_can_change_it(routes, monkeypatch):
    import auth
    old, new = "Str0ngPassw0rd", "N3wPassw0rdHere"
    row = _user("jayesh@adlerqa.in", password_hash=auth.hash_password(old))
    store = FakeStore([row])
    r = _change(routes, monkeypatch, store, row, old, new)
    assert r["changed"] is True
    assert auth.password_matches(store.users["jayesh@adlerqa.in"]["password_hash"], new)


def test_otp_only_account_cannot_set_a_first_password_here(routes, monkeypatch):
    """No password to change — and this route must not become a way to set one."""
    row = _user("otp@adlerqa.in", role="viewer")
    store = FakeStore([row])
    with pytest.raises(routes.HTTPException) as exc:
        _change(routes, monkeypatch, store, row, "", "N3wPassw0rdHere")
    assert exc.value.status_code == 400
    assert "one-time code" in exc.value.detail
    assert "password_hash" not in store.users["otp@adlerqa.in"]


def test_local_admin_can_still_change_from_the_shipped_default(routes, monkeypatch):
    import auth
    row = _user("admin")
    store = FakeStore([row])
    r = _change(routes, monkeypatch, store, row, routes.DEFAULT_ADMIN_PASSWORD,
                "N3wPassw0rdHere")
    assert r["changed"] is True
    assert auth.password_matches(store.users["admin"]["password_hash"], "N3wPassw0rdHere")


def test_wrong_current_password_is_rejected(routes, monkeypatch):
    import auth
    row = _user("jayesh@adlerqa.in", password_hash=auth.hash_password("Str0ngPassw0rd"))
    store = FakeStore([row])
    with pytest.raises(routes.HTTPException) as exc:
        _change(routes, monkeypatch, store, row, "wrong", "N3wPassw0rdHere")
    assert exc.value.status_code == 400
    assert "current password is incorrect" in exc.value.detail
