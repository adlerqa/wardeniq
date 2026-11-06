import os
import time
from fastapi.testclient import TestClient

from main import app, store
import auth

client = TestClient(app)


def test_password_reset_flow():
    # 1. Request password reset without SMTP (returns smtp_configured: false, no codes issued)
    res = client.post("/api/auth/request-password-reset", json={"username_or_email": "admin"})
    assert res.status_code == 200
    data = res.json()
    assert data.get("smtp_configured") is False

    user = store.get_user_by_email("admin")
    assert user is not None

    # 2. Directly set reset code (simulating email delivery when SMTP is on)
    reset_code = "123456"
    store.set_reset_code(user["id"], auth.hash_otp(reset_code), time.time() + 600)

    # 3. Try resetting with invalid code
    bad_res = client.post("/api/auth/reset-password", json={
        "username_or_email": "admin",
        "code": "000000",
        "new_password": "NewPassword123"
    })
    assert bad_res.status_code == 401

    # 4. Try password failing policy (< 8 chars)
    policy_res = client.post("/api/auth/reset-password", json={
        "username_or_email": "admin",
        "code": reset_code,
        "new_password": "short"
    })
    assert policy_res.status_code == 400

    # 5. Reset with valid password
    new_pw = "ValidPassword123"
    good_res = client.post("/api/auth/reset-password", json={
        "username_or_email": "admin",
        "code": reset_code,
        "new_password": new_pw
    })
    assert good_res.status_code == 200
    assert good_res.json().get("reset") is True

    # 6. Verify password works for login
    fresh_user = store.get_user_by_email("admin")
    assert auth.password_matches(fresh_user.get("password_hash"), new_pw)


def test_master_secret_reset_flow():
    effective_secret = auth._session_secret()

    # 1. Try master reset with wrong secret
    bad_res = client.post("/api/auth/reset-password-master", json={
        "username": "admin",
        "app_secret": "wrong-secret-key-12345",
        "new_password": "MasterNewPass123"
    })
    assert bad_res.status_code == 401

    # 2. Reset using correct APP_SECRET
    master_pw = "MasterNewPass123"
    good_res = client.post("/api/auth/reset-password-master", json={
        "username": "admin",
        "app_secret": effective_secret,
        "new_password": master_pw
    })
    assert good_res.status_code == 200
    assert good_res.json().get("reset") is True

    # 3. Verify admin password updated
    fresh_user = store.get_user_by_email("admin")
    assert auth.password_matches(fresh_user.get("password_hash"), master_pw)


if __name__ == "__main__":
    test_password_reset_flow()
    test_master_secret_reset_flow()
    print("=== PASS: test_password_reset_flow & test_master_secret_reset_flow ===")
