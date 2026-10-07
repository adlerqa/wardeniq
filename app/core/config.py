"""Environment-derived configuration constants.

Moved verbatim out of main.py (Phase 1 of REFACTOR_PLAN.md). These are pure
env-var reads with defaults — no singletons, no side effects beyond os.getenv
and the DEFAULT_ADMIN_PASSWORD policy check. Consumers should import the exact
names they need explicitly (avoid `from core.config import *`) so ruff's
dead-import signal keeps working.
"""
import os

import auth

# Database + Ollama endpoints are configurable two ways (Joomla-style): an explicit
# value in .env WINS (and shows as "configured" / locked in the UI); otherwise the
# bundled default is used and the value is editable from the frontend, which persists
# it back into .env. Compose injects the .env value (empty if the user hasn't set one)
# plus a *_BUNDLED fallback so we can tell "user-configured" from "using the default".
_ENV_MONGO = (os.getenv("MONGO_URI") or "").strip()
MONGO_URI_BUNDLED = os.getenv(
    "MONGO_URI_BUNDLED",
    "mongodb://mongod1.warden-net:27017,mongod2.warden-net:27017,"
    "mongod3.warden-net:27017/?replicaSet=rs0")
MONGO_URI = _ENV_MONGO or MONGO_URI_BUNDLED

_ENV_OLLAMA = (os.getenv("OLLAMA_URL") or "").strip()
OLLAMA_URL_BUNDLED = os.getenv("OLLAMA_URL_BUNDLED", "http://ollama:11434")

# Path to the .env file the app persists frontend config into. In Docker this is a
# bind-mount of the project's ./.env (see docker-compose.app.yml); changes apply on
# the next `docker compose up -d` (compose re-reads .env and re-injects the vars).
ENV_FILE_PATH = os.getenv("ENV_FILE_PATH", "/app/.env")
EMBED_MODEL = os.getenv("EMBED_MODEL", "nomic-embed-text")
EMBED_DIM = int(os.getenv("EMBED_DIM", "768"))
GEN_MODEL = os.getenv("GEN_MODEL", "qwen2.5:3b")
# Phase 6 (REFACTOR_PLAN.md): moved here (documented deviation, same reasoning as the
# other core/config.py constants) because both main.py's own generate-job code and the
# new api/routes/jira_atlassian.py router's inbound jira_webhook need it.
GEN_TOTAL = int(os.getenv("GEN_TOTAL", "16"))  # total target cases across all types
# How many independent passes the Mind Map reviewer makes per batch. >1 keeps a
# 'covered' verdict only when every pass agrees (cross-sample self-consistency),
# trading N x tokens for markedly less hallucination variance. 1 = single pass.
MINDMAP_SAMPLES = max(1, int(os.getenv("MINDMAP_SAMPLES", "1")))
# Mind Map retrieval shape. These used to be hard-coded (rank 24, <=2 chunks/file, 20
# chunks total) and became THE binding constraint once the excerpt character budget was
# fixed: auth.controller.ts holds ~6 function chunks but could contribute only 2, so
# sendOtp never reached the reviewer and every sendOtp case was judged "no implementation
# code provided" - while verifyOtp, which happened to be picked, was correctly found.
# Selection is now driven by the character budget instead of a chunk count.
# (Retrieval is now uncapped: the whole pool is ranked and every chunk is reviewed in
# windows. The former rank/chunk/per-file rationing knobs are gone — they existed only to
# choose what to throw away.)
DB_NAME = os.getenv("DB_NAME", "wardeniq")
VERSION = "0.2.3"
AUTO_SETUP = os.getenv("AUTO_SETUP", "true").lower() == "true"
STEP_AUTO = float(os.getenv("STEP_AUTO_REUSE", "0.95"))
CASE_AUTO = float(os.getenv("CASE_AUTO_REUSE", "0.93"))
SUGGEST = float(os.getenv("SUGGEST_THRESHOLD", "0.85"))
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_API = os.getenv("GITHUB_API", "https://api.github.com")
# Self-hosted GitLab support: point this at your instance (e.g. https://gitlab.example.com).
# Defaults to gitlab.com so nothing changes for the common case.
GITLAB_BASE_URL = (os.getenv("GITLAB_BASE_URL") or "https://gitlab.com").strip().rstrip("/")
# GitHub poller cadence. The frontend-saved value (settings.poll_interval_s) WINS;
# POLL_INTERVAL_SECONDS in .env is only the seed default for fresh installs; else the
# built-in 30-minute default. Resolved live per loop via current_poll_interval() so an
# in-app change applies without a restart. Floored at MIN_POLL_INTERVAL to protect the API.
_ENV_POLL = (os.getenv("POLL_INTERVAL_SECONDS") or "").strip()
POLL_INTERVAL_FALLBACK = 1800  # 30 minutes
MIN_POLL_INTERVAL = 30
MAP_AUTO = float(os.getenv("MAP_AUTO_THRESHOLD", "0.86"))
# GAP8 (opt-in): use embeddings to semantically match imported-pool rows to features
# during the background re-scan, as an ADDITIONAL promotion path beyond the algorithmic
# scorer. OFF by default (the token scorer already works and per-row embedding has cost).
IMPORT_SEMANTIC_MATCH = os.getenv("IMPORT_SEMANTIC_MATCH", "false").lower() == "true"
IMPORT_SEMANTIC_THRESHOLD = float(os.getenv("IMPORT_SEMANTIC_THRESHOLD", "0.78"))
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")
MONGOT_METRICS = os.getenv("MONGOT_METRICS", "http://mongot.warden-net:9946")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "").strip().lower()
# Installer-chosen bootstrap password for the local `admin` account. When set (and
# it passes the password policy), it REPLACES the shipped `admin123` default: the
# admin row is seeded with this password's hash at boot and admin123 stops working.
# Left empty (pure source dev), the legacy admin123 default applies with its
# mandatory change-on-first-login. Never logged.
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "").strip()
# The effective default password accepted for the bootstrap admin before any
# in-app change: the operator's ADMIN_PASSWORD if valid, else the shipped default.
DEFAULT_ADMIN_PASSWORD = (
    ADMIN_PASSWORD if (ADMIN_PASSWORD and not auth.password_policy_errors(ADMIN_PASSWORD))
    else auth.DEFAULT_LOCAL_PASSWORD)
# Auth is ALWAYS enforced — there is no bypass flag. The first admin bootstraps
# without SMTP by reading a one-time code printed to the server log (see
# _deliver_otp), then configures email in-app.
# Deployment posture. "production" turns on hard startup gates (see
# _check_production_posture) and disables the public API docs. Anything else
# (default "development") keeps the zero-config local behaviour.
APP_ENV = os.getenv("APP_ENV", os.getenv("ENV", "development")).strip().lower()
IS_PRODUCTION = APP_ENV in ("production", "prod")
# When auth is on, a weak/default APP_SECRET is disqualifying (it signs sessions
# AND derives the secret-at-rest key). We refuse to boot in that case unless the
# operator explicitly opts out for a local/dev run.
ALLOW_WEAK_SECRET = os.getenv("ALLOW_WEAK_SECRET", "false").lower() == "true"
# Display label for this single-tenant instance (shown on the invite banner). Not a
# tenant/org — just a name for the deployment.
APP_WORKSPACE_NAME = os.getenv("APP_WORKSPACE_NAME", "WardenIQ").strip() or "WardenIQ"
# Optional deploy-time lock to a single AI provider (e.g. "bedrock" for an
# air-gapped enterprise install). Empty = no lock; the UI shows every provider.
PROVIDER_LOCK = os.getenv("LLM_PROVIDER_LOCK", "").strip().lower()
# OTP request throttle: at most OTP_MAX_PER_WINDOW codes issued to one account within
# OTP_WINDOW_SECONDS (stops email-bombing / code brute-force churn).
OTP_WINDOW_SECONDS = int(os.getenv("OTP_WINDOW_SECONDS", "900"))   # 15 min
OTP_MAX_PER_WINDOW = int(os.getenv("OTP_MAX_PER_WINDOW", "5"))

# Stale-job sweep (Phase 4, REFACTOR_PLAN.md): how long a "running" job can go without
# a heartbeat before background/schedulers.py's `_stale_job_sweeper` fails it, and how
# often the sweep runs.
STALE_JOB_TTL_SECONDS = int(os.getenv("STALE_JOB_TTL_SECONDS", "600"))
STALE_JOB_SWEEP_INTERVAL_SECONDS = int(os.getenv("STALE_JOB_SWEEP_INTERVAL_SECONDS", "60"))
