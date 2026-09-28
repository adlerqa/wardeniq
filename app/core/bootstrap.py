"""Startup bootstrap: secret/production posture checks, DB connect + index
build retry loop, legacy-feature migration, and admin seeding.

Moved out of main.py (Phase 2 of REFACTOR_PLAN.md). `bootstrap()` itself is
still invoked from main.py's `_startup()` on-event handler (Phase 4 concern —
background thread wiring hasn't moved yet), so this module does not change
when or how often bootstrap runs.

Three call sites reach into helpers that have NOT moved out of main.py yet
(`_smtp_cfg`, `_env_file_writable`, `_write_env_var` — all used extensively by
route handlers that are still in main.py, a Phase 6 concern). Importing them
at module level would be a real main<->core.bootstrap cycle (main imports
`bootstrap` from here; this module would need to import back from main before
main has finished defining anything). Both are therefore function-level
imports, resolved only when the function actually runs — by which point
main.py has fully executed and is in sys.modules — matching REFACTOR_PLAN.md's
"function-level imports to break a cycle only when absolutely unavoidable and
documented" allowance.
"""
import os
import time

import auth
from core.config import ADMIN_EMAIL, ADMIN_PASSWORD, ALLOW_WEAK_SECRET, AUTO_SETUP, ENV_FILE_PATH, IS_PRODUCTION
from core.logging_setup import get_logger
from core.state import store  # noqa: F401  (bare name-import is safe: store is
                                              # mutated, never rebound)

log = get_logger("bootstrap")

BOOT = {"stage": "starting", "ready": False, "detail": ""}


def public_boot_status():
    """Only operator-facing copy may cross the unauthenticated boundary.

    `detail` can contain arbitrary driver errors, URIs and credentials. Never
    return it here, even for an unknown/new failure mode.
    """
    boot = BOOT.copy()
    stage = boot["stage"]
    detail = {
        "starting": "wardenIQ is starting. Please wait.",
        "connecting": "Connecting to MongoDB. If this persists, check MONGO_URI and database availability, then restart.",
        "indexing": "Preparing MongoDB search indexes. If this persists, check that mongot or Atlas Search is available.",
    }.get(stage, "wardenIQ could not finish starting. Check the server logs and restart after fixing the problem.")
    if stage == "error":
        detail = boot.get("public_detail") or detail
    return {"stage": stage, "ready": boot["ready"],
            "detail": "" if boot["ready"] else detail}


def _ensure_app_secret():
    """Zero-config first run: if no real secret has been configured at all, generate a
    strong one automatically and persist it into .env, so a first-time user never has
    to hand-edit anything just to get past the weak-secret gate below.

    This does NOT weaken `_check_app_secret()` — it only fires when the effective
    secret is still unset/the shipped placeholder, and only when we can durably
    persist the generated value to .env (bind-mounted per docker-compose.app.yml), so
    the SAME secret survives a restart (sessions and encrypted-at-rest settings depend
    on that). If persistence isn't possible, we deliberately do nothing and let
    `_check_app_secret()` fail closed with its existing clear error, rather than run on
    a secret that would silently change on every restart.

    If an operator has already started customizing via SESSION_SECRET/ENCRYPTION_KEY,
    we leave it alone entirely — auto-filling just one half of an intentional split
    would be more confusing than helpful.
    """
    from api.routes.settings import _env_file_writable
    from core.deps import _write_env_var

    if not auth.secret_is_weak():
        return
    if os.getenv("SESSION_SECRET") or os.getenv("ENCRYPTION_KEY"):
        return
    if not _env_file_writable():
        return
    import secrets
    generated = secrets.token_urlsafe(32)
    ok, err = _write_env_var(ENV_FILE_PATH, "APP_SECRET", generated)
    if not ok:
        log.warning("could not persist an auto-generated APP_SECRET: %s", err)
        return
    os.environ["APP_SECRET"] = generated
    log.info("No APP_SECRET was set — generated a strong one automatically and saved it "
             "to .env. This key signs sessions and encrypts stored secrets: back up your "
             ".env file, and set your own APP_SECRET explicitly before going to production.")


def _bootstrap_password_targets():
    """The accounts the .env bootstrap password applies to.

    Two rows, because there are two ways to name yourself at the sign-in form (it is
    labelled "Username or email"):

      1. the local `admin` account — the zero-config bootstrap identity;
      2. the ADMIN_EMAIL admin — so the operator can sign in with the SAME
         email + password pair they configured in .env, instead of having to reach
         for /api/auth/reset-password-master to give that account a password.

    The `admin` row is created here if missing (it is this function's own
    bootstrap). The ADMIN_EMAIL row is only ever *seeded* — creating it belongs to
    the ADMIN_EMAIL seed step above, which validates the address first, so a
    malformed value never reaches this point as a user row.
    """
    targets = []
    admin = store.get_user_by_email("admin")
    if not admin:
        admin = store.create_user("admin", "Admin", "admin")
    targets.append(admin)

    email = (ADMIN_EMAIL or "").strip().lower()
    if email and email != "admin" and auth.is_valid_email(email):
        row = store.get_user_by_email(email)
        # Skip a row that IS the admin row (defensive: same id, different key).
        if row and row["id"] != admin["id"]:
            targets.append(row)
    return targets


def _seed_bootstrap_password():
    """Apply the .env bootstrap password to the accounts it names.

    The contract, as an operator reads it off .env:

      * ADMIN_PASSWORD blank  → nothing is seeded, and DEFAULT_ADMIN_PASSWORD (see
        core/config.py) stays the shipped `admin123`, so `admin` / admin123 signs in
        with its forced change-on-first-login.
      * ADMIN_PASSWORD set    → seeded onto the local `admin` row AND the ADMIN_EMAIL
        row, so BOTH `admin` and that email sign in with it. DEFAULT_ADMIN_PASSWORD
        becomes that value, so admin123 stops working.

    Only ever fills an EMPTY password — a password changed in-app survives restarts.
    RESET_ADMIN_PASSWORD / ADMIN_PASSWORD_FORCE are the deliberate override: they
    overwrite an existing password, on every boot while the variable is set.
    A value failing the policy is ignored with a warning rather than half-applied.
    """
    reset_env_pw = os.getenv("RESET_ADMIN_PASSWORD", "").strip() or os.getenv("ADMIN_PASSWORD_FORCE", "").strip()
    if reset_env_pw:
        errs = auth.password_policy_errors(reset_env_pw)
        if errs:
            log.warning("RESET_ADMIN_PASSWORD does not meet policy (%s); ignoring it.",
                       ", ".join(errs))
            return
        for row in _bootstrap_password_targets():
            store.set_user_password(row["id"], auth.hash_password(reset_env_pw))
            log.info("Force-reset the password for %r from RESET_ADMIN_PASSWORD "
                    "environment variable.", row["email"])
        return

    if not ADMIN_PASSWORD:
        # Nothing configured: the shipped admin123 default stands (config.py resolves
        # DEFAULT_ADMIN_PASSWORD to it) and no row is created or touched here.
        return

    errs = auth.password_policy_errors(ADMIN_PASSWORD)
    if errs:
        log.warning("ADMIN_PASSWORD does not meet the policy (%s); ignoring it — the "
                   "bootstrap admin keeps the default until changed.", ", ".join(errs))
        return

    for row in _bootstrap_password_targets():
        if not row.get("password_hash"):
            store.set_user_password(row["id"], auth.hash_password(ADMIN_PASSWORD))
            log.info("Seeded the password for %r from ADMIN_PASSWORD (the shipped "
                    "default is disabled).", row["email"])


def _check_app_secret():
    """Fail closed (or loudly warn) if APP_SECRET is weak.

    APP_SECRET signs sessions/OTPs and derives the Fernet key for secrets at rest,
    so a default/short value lets anyone forge an admin session and decrypt stored
    credentials. Auth is always on, so we refuse to boot on a weak secret; set
    ALLOW_WEAK_SECRET=true to override for a trusted local run.
    """
    if not auth.secret_is_weak():
        return
    msg = ("APP_SECRET is unset, the shipped placeholder, or shorter than "
           f"{auth.MIN_SECRET_LEN} chars. It signs login sessions and encrypts "
           "stored secrets — a weak value is a critical vulnerability.")
    if not ALLOW_WEAK_SECRET:
        BOOT.update(stage="error", ready=False,
                    public_detail="APP_SECRET is missing or insecure. Set a strong APP_SECRET and restart.",
                    detail=f"insecure APP_SECRET: {msg} Set a strong APP_SECRET "
                           "(or ALLOW_WEAK_SECRET=true for a trusted local run).")
        raise RuntimeError(f"[wardenIQ] refusing to start — {msg}")
    log.warning("%s (allowed because ALLOW_WEAK_SECRET=true)", msg)


def _check_production_posture():
    """In a production posture (APP_ENV=production) refuse to boot with settings that
    are acceptable only for local development. Fails closed so an insecure instance
    never comes up on the public internet by accident."""
    from core.deps import _smtp_cfg # see module docstring

    if not IS_PRODUCTION:
        return
    problems = []
    if ALLOW_WEAK_SECRET:
        problems.append("ALLOW_WEAK_SECRET=true (must be false)")
    if not auth.COOKIE_SECURE:
        problems.append("COOKIE_SECURE=false (sessions must be HTTPS-only)")
    if not _smtp_cfg():
        problems.append("SMTP not configured (email sign-in would be unavailable)")
    if problems:
        detail = ("insecure production configuration: " + "; ".join(problems) +
                  ". Fix these, or unset APP_ENV=production for a local run.")
        BOOT.update(stage="error", ready=False, detail=detail, public_detail=detail)
        raise RuntimeError(f"[wardenIQ] refusing to start — {detail}")


def _search_unsupported(e) -> bool:
    """Heuristic: does the connected MongoDB clearly LACK Search/Vector Search (as
    opposed to a search service that's merely still starting)? A search-less server
    rejects the search-index commands outright ('no such command' / 'unrecognized'),
    which is worth failing fast on — unlike 'connecting to Search Index Management
    service', which is transient while a bundled mongot boots."""
    m = str(e).lower()
    return any(s in m for s in (
        "no such command", "unrecognized", "command not found",
        "notimplemented", "atlas search is not", "search is not supported",
    ))


def _search_index_limit(e) -> bool:
    """The connected DB supports search but won't allow enough indexes — the classic
    MongoDB Atlas per-tier cap ('maximum number of FTS indexes ... for this instance
    size'). No point retrying; the fix is a bigger tier or self-managed mongot."""
    m = str(e).lower()
    return ("maximum number of fts indexes" in m
            or ("fts index" in m and "instance size" in m)
            or "maximum number of search indexes" in m)


_SEARCH_REQUIRED_MSG = (
    "wardenIQ requires a MongoDB with Vector Search — it's where embeddings are "
    "searched. The database at MONGO_URI doesn't have it. Use MongoDB Atlas (search "
    "built in) or a self-managed MongoDB running mongot, then restart."
)

_SEARCH_INDEX_LIMIT_MSG = (
    "This MongoDB Atlas cluster doesn't allow enough search indexes. wardenIQ needs 6, "
    "but your tier caps them (the free M0 tier allows only 3). Fix: upgrade to a "
    "dedicated Atlas tier (M10 or higher), or use a self-managed MongoDB with mongot "
    "(no such limit), then restart."
)


def bootstrap():
    _ensure_app_secret()
    _check_app_secret()
    _check_production_posture()
    BOOT.update(stage="connecting")
    for _ in range(60):
        try:
            store.ping(); break
        except Exception as e:  # noqa: BLE001
            BOOT["detail"] = str(e); time.sleep(2)
    try:
        store.fail_orphaned_jobs()
    except Exception as e:  # noqa: BLE001
        BOOT["detail"] = f"job recovery: {e}"
    if AUTO_SETUP:
        BOOT.update(stage="indexing")
        idx_err = None
        # Generous retry: a bundled mongot can take a while to sync + build indexes.
        for _ in range(40):
            try:
                store.ensure_indexes(); idx_err = None; break
            except Exception as e:  # noqa: BLE001
                idx_err = e
                # These two won't resolve by waiting → stop retrying and report clearly.
                if _search_unsupported(e) or _search_index_limit(e):
                    break
                BOOT["detail"] = f"index retry: {e}"; time.sleep(3)
        if idx_err is not None:
            # Refuse to serve, with a message that matches the actual cause rather than
            # a raw driver dump. The Atlas per-tier index cap is a distinct, common case.
            if _search_index_limit(idx_err):
                detail = _SEARCH_INDEX_LIMIT_MSG
                reason = "too few search indexes allowed by the Atlas tier"
            else:
                detail = _SEARCH_REQUIRED_MSG
                reason = "Vector Search unavailable"
            BOOT.update(stage="error", ready=False, detail=detail, public_detail=detail)
            log.error("refusing to serve — %s: %s", reason, idx_err)
            return
    # Adopt features created before project_id existed into a default project.
    try:
        store.migrate_legacy_features()
    except Exception as e:  # noqa: BLE001
        BOOT["detail"] = f"migrate: {e}"
    # Seed the first admin from ADMIN_EMAIL (if set and not already present).
    # Validate it first: a malformed value (e.g. a leaked .env comment) must NOT be
    # inserted as a user — warn loudly and skip instead.
    try:
        if ADMIN_EMAIL:
            if not auth.is_valid_email(ADMIN_EMAIL):
                log.warning("ADMIN_EMAIL is not a valid email (%r); skipping admin seed. "
                          "Fix ADMIN_EMAIL in .env (no inline comments on the value "
                          "line).", ADMIN_EMAIL)
            elif not store.get_user_by_email(ADMIN_EMAIL):
                store.create_user(ADMIN_EMAIL, ADMIN_EMAIL.split("@")[0], "admin")
    except Exception as e:  # noqa: BLE001
        BOOT["detail"] = f"admin seed: {e}"
    try:
        _seed_bootstrap_password()
    except Exception as e:  # noqa: BLE001
        BOOT["detail"] = f"admin password seed: {e}"
    BOOT.update(stage="ready", ready=True, detail="")
