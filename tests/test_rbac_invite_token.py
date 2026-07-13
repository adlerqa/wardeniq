"""Invite-token flow — the fix for the double-email / OTP-collision bug.

Invitations now use a single-use, time-limited TOKEN emailed as a LINK, kept
SEPARATE from the login OTP (different fields), so requesting a login code can no
longer overwrite the invite. These tests cover the token primitives (auth) and the
store's set/verify/expiry/consume behavior.
"""
import os
import time
import types
from pathlib import Path

import pytest

import auth

_ROOT = Path(__file__).resolve().parents[1]


class TestInviteTokenAuth:
    def test_token_roundtrip(self, monkeypatch):
        monkeypatch.setenv("APP_SECRET", "a-strong-secret-value-1234")
        t = auth.gen_invite_token()
        assert len(t) >= 32
        h = auth.hash_token(t)
        assert auth.token_matches(h, t) is True
        assert auth.token_matches(h, "wrong") is False

    def test_token_distinct_from_otp(self, monkeypatch):
        monkeypatch.setenv("APP_SECRET", "a-strong-secret-value-1234")
        t = auth.gen_invite_token()
        # an invite token and a login OTP must not be interchangeable
        assert auth.otp_matches(auth.hash_otp("123456"), t) is False
        assert auth.token_matches(auth.hash_token(t), "123456") is False

    def test_empty_token_never_matches(self):
        assert auth.token_matches("", "x") is False


class _FakeUsersCol:
    def __init__(self):
        self.docs = {}

    def update_one(self, q, upd):
        uid = q["_id"]
        d = self.docs.setdefault(uid, {"_id": uid})
        for k, v in upd.get("$set", {}).items():
            d[k] = v
        for k in upd.get("$unset", {}):
            d.pop(k, None)

    def find_one(self, q, proj=None):
        for d in self.docs.values():
            ok = True
            for k, v in q.items():
                if isinstance(v, dict) and "$gt" in v:
                    if not (d.get(k, 0) > v["$gt"]):
                        ok = False
                        break
                elif d.get(k) != v:
                    ok = False
                    break
            if ok:
                return dict(d)
        return None


def _make_store():
    """A real store.Store with only its users collection faked, so the actual
    invite-token methods run against it."""
    from store import Store
    from bson import ObjectId
    st = Store.__new__(Store)
    object.__setattr__(st, "users", _FakeUsersCol())
    uid = ObjectId("64f000000000000000000001")
    st.users.docs[uid] = {"_id": uid, "email": "a@x.com", "invite_status": "pending"}
    return st


class TestInviteTokenStore:
    def test_set_and_resolve(self):
        st = _make_store()
        t = auth.gen_invite_token()
        st.set_invite_token("64f000000000000000000001", auth.hash_token(t), time.time() + 3600)
        u = st.get_user_by_invite_token(t)
        assert u and u["id"] == "64f000000000000000000001" and u["email"] == "a@x.com"

    def test_expired_token_not_resolved(self):
        st = _make_store()
        t = auth.gen_invite_token()
        st.set_invite_token("64f000000000000000000001", auth.hash_token(t), time.time() - 1)
        assert st.get_user_by_invite_token(t) is None

    def test_wrong_token_not_resolved(self):
        st = _make_store()
        st.set_invite_token("64f000000000000000000001", auth.hash_token(auth.gen_invite_token()), time.time() + 3600)
        assert st.get_user_by_invite_token("some-other-token") is None

    def test_clear_consumes_token(self):
        st = _make_store()
        t = auth.gen_invite_token()
        st.set_invite_token("64f000000000000000000001", auth.hash_token(t), time.time() + 3600)
        assert st.get_user_by_invite_token(t) is not None
        st.clear_invite_token("64f000000000000000000001")
        assert st.get_user_by_invite_token(t) is None

