"""First-start terminal database/backend selection in run.ps1 (issue #109) --
the Windows entry point, added to keep parity with run.sh's PR #113 change.

run.ps1 is a real PowerShell script with no --dry-run mode, so these tests run
the ACTUAL, unmodified, committed script end-to-end in an isolated temp
directory via `pwsh` (PowerShell 7, cross-platform) -- the same "drive the
real file" philosophy as tests/test_run_sh_db_selection.py. A fake `docker` on
PATH stands in for the real Docker CLI; a real, local HTTP server stands in
for the app's readiness endpoint (run.ps1 calls the PowerShell cmdlet
Invoke-RestMethod directly, not an external `curl` binary, so it can't be
faked via PATH the way run.sh's `curl` call was -- an actual tiny server is
the honest equivalent). No real container, network, or MongoDB connection is
ever touched.

Requires `pwsh` on PATH; skips entirely (module-level) if it isn't installed,
matching this repo's existing skip-if-unavailable pattern for infrastructure
the test environment may not have (see tests/test_db_integration.py). GitHub
Actions has no Windows job today (.github/workflows/ci.yml runs everything on
ubuntu-latest) -- this suite runs the script logic for real via cross-platform
PowerShell 7, which is a genuine (not faked) execution of the same code, but
is not literal Windows execution; see the PR for exactly what that does and
doesn't cover.
"""
import http.server
import json
import os
import shutil
import stat
import subprocess
import threading
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PWSH = shutil.which("pwsh")

if not PWSH:
    pytest.skip("pwsh (PowerShell 7) not found on PATH -- skipping run.ps1 tests",
                allow_module_level=True)

FAKE_DOCKER_SH = """#!/usr/bin/env bash
if [ "$1" = "info" ]; then
  echo "${FAKE_KERNEL_VERSION:-6.1.0-generic}"
  exit 0
fi
if [ "$1" = "compose" ]; then
  exit 0
fi
exit 0
"""


class _ReadyBootStatusHandler(http.server.BaseHTTPRequestHandler):
    """Stands in for the real app's /api/auth/boot-status -- always reports
    ready, so run.ps1's readiness-poll loop returns on its first check
    instead of spinning for up to 5 real minutes."""

    def do_GET(self):  # noqa: N802 (BaseHTTPRequestHandler's own naming)
        body = json.dumps({"ready": True}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):  # noqa: ARG002 -- silence per-request stderr noise
        pass


@pytest.fixture(scope="module")
def boot_status_server():
    server = http.server.HTTPServer(("127.0.0.1", 8001), _ReadyBootStatusHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield
    finally:
        server.shutdown()
        thread.join(timeout=5)


@pytest.fixture()
def sandbox(tmp_path):
    """A temp directory with the REAL run.ps1 plus everything it touches, and
    a fake docker placed first on PATH."""
    shutil.copy(REPO_ROOT / "run.ps1", tmp_path / "run.ps1")
    shutil.copy(REPO_ROOT / ".env.example", tmp_path / ".env.example")
    (tmp_path / "config").mkdir()

    bin_dir = tmp_path / "fakebin"
    bin_dir.mkdir()
    docker_path = bin_dir / "docker"
    docker_path.write_text(FAKE_DOCKER_SH)
    docker_path.chmod(docker_path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return tmp_path, bin_dir


def _run(sandbox, boot_status_server, env=None, kernel_version=None):  # noqa: ARG001
    tmp_path, bin_dir = sandbox
    full_env = {k: v for k, v in os.environ.items()
               if not k.startswith("WARDENIQ_") and k != "FAKE_KERNEL_VERSION"}
    full_env["PATH"] = f"{bin_dir}:{os.environ['PATH']}"
    if kernel_version:
        full_env["FAKE_KERNEL_VERSION"] = kernel_version
    full_env.update(env or {})
    return subprocess.run(
        [PWSH, "-NoLogo", "-NonInteractive", "-File", "run.ps1"], cwd=tmp_path, env=full_env,
        stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=30,
    )


def _env_file(sandbox) -> str:
    tmp_path, _ = sandbox
    return (tmp_path / ".env").read_text()


def _has_env_line(env_text: str, line: str) -> bool:
    """True if `line` (e.g. "MONGO_URI=foo") appears as an actual assignment,
    not inside .env.example's own commented-out documentation lines."""
    return line in env_text.splitlines()


def _has_env_key(env_text: str, key: str) -> bool:
    return any(ln.startswith(f"{key}=") for ln in env_text.splitlines())


# ------------------------------------------------------------------ defaults
def test_noninteractive_default_is_community_with_no_db_changes(sandbox, boot_status_server):
    r = _run(sandbox, boot_status_server, env={"WARDENIQ_ASSUME_YES": "1"})
    assert r.returncode == 0, r.stdout + r.stderr
    env_text = _env_file(sandbox)
    assert not _has_env_key(env_text, "MONGO_URI")
    assert not _has_env_key(env_text, "COMPOSE_FILE")


def test_existing_install_is_never_reprompted_or_changed(sandbox, boot_status_server):
    _run(sandbox, boot_status_server, env={"WARDENIQ_ASSUME_YES": "1", "WARDENIQ_DB": "external",
                                           "WARDENIQ_MONGO_URI": "mongodb://reachable-test-host/"})
    before = _env_file(sandbox)
    r = _run(sandbox, boot_status_server, env={"WARDENIQ_ASSUME_YES": "1"})
    assert r.returncode == 0, r.stdout + r.stderr
    assert _env_file(sandbox) == before


# ------------------------------------------------------------------- percona
def test_percona_selection_persists_uri_and_compose_file(sandbox, boot_status_server):
    r = _run(sandbox, boot_status_server, env={"WARDENIQ_ASSUME_YES": "1", "WARDENIQ_DB": "percona"})
    assert r.returncode == 0, r.stdout + r.stderr
    env_text = _env_file(sandbox)
    assert _has_env_line(env_text, "MONGO_URI=mongodb://mongod-percona:27017/?replicaSet=rs0")
    assert _has_env_line(env_text, "COMPOSE_FILE=docker-compose.app.yml:docker-compose.mongodb-percona.yml:docker-compose.ollama.yml")
    pwfile = sandbox[0] / "config" / "pwfile-percona"
    assert pwfile.exists()
    assert pwfile.read_text().strip()


def test_percona_still_hits_the_kernel_guard(sandbox, boot_status_server):
    r = _run(sandbox, boot_status_server, env={"WARDENIQ_ASSUME_YES": "1", "WARDENIQ_DB": "percona"},
             kernel_version="6.19.0-generic")
    assert r.returncode == 1
    assert "kernel >= 6.19" in (r.stdout + r.stderr)


def test_percona_passes_the_kernel_guard_on_an_older_kernel(sandbox, boot_status_server):
    r = _run(sandbox, boot_status_server, env={"WARDENIQ_ASSUME_YES": "1", "WARDENIQ_DB": "percona"},
             kernel_version="6.10.0-generic")
    assert r.returncode == 0, r.stdout + r.stderr


def test_existing_percona_install_still_hits_kernel_guard_on_rerun(sandbox, boot_status_server):
    r1 = _run(sandbox, boot_status_server, env={"WARDENIQ_ASSUME_YES": "1", "WARDENIQ_DB": "percona"},
              kernel_version="6.10.0-generic")
    assert r1.returncode == 0, r1.stdout + r1.stderr
    # A LATER run, on a since-upgraded (bad) kernel, must still be caught -- the
    # exact gap #109 flagged: MONGO_URI alone must not silently bypass the guard
    # for an already-configured Percona install.
    r2 = _run(sandbox, boot_status_server, env={"WARDENIQ_ASSUME_YES": "1"}, kernel_version="6.19.0-generic")
    assert r2.returncode == 1
    assert "kernel >= 6.19" in (r2.stdout + r2.stderr)


# ------------------------------------------------------------------- external
def test_external_reachable_uri_is_saved(sandbox, boot_status_server):
    r = _run(sandbox, boot_status_server, env={"WARDENIQ_ASSUME_YES": "1", "WARDENIQ_DB": "external",
                                               "WARDENIQ_MONGO_URI": "mongodb://reachable-test-host/"})
    assert r.returncode == 0, r.stdout + r.stderr
    env_text = _env_file(sandbox)
    assert _has_env_line(env_text, "MONGO_URI=mongodb://reachable-test-host/")
    assert _has_env_line(env_text, "COMPOSE_FILE=docker-compose.app.yml:docker-compose.ollama.yml")
    assert _has_env_line(env_text, "OLLAMA_URL_BUNDLED=http://host.docker.internal:11434")


def test_external_skips_the_kernel_guard_even_on_a_bad_kernel(sandbox, boot_status_server):
    r = _run(sandbox, boot_status_server, env={"WARDENIQ_ASSUME_YES": "1", "WARDENIQ_DB": "external",
                                               "WARDENIQ_MONGO_URI": "mongodb://reachable-test-host/"},
             kernel_version="6.19.0-generic")
    assert r.returncode == 0, r.stdout + r.stderr


def test_external_malformed_uri_noninteractive_warns_but_does_not_block(sandbox, boot_status_server):
    r = _run(sandbox, boot_status_server, env={"WARDENIQ_ASSUME_YES": "1", "WARDENIQ_DB": "external",
                                               "WARDENIQ_MONGO_URI": "not-a-uri"})
    assert r.returncode == 0, r.stdout + r.stderr
    assert "doesn't look like a valid MongoDB connection string" in (r.stdout + r.stderr)
    assert _has_env_line(_env_file(sandbox), "MONGO_URI=not-a-uri")


def test_external_with_no_uri_at_all_still_proceeds_with_a_warning(sandbox, boot_status_server):
    r = _run(sandbox, boot_status_server, env={"WARDENIQ_ASSUME_YES": "1", "WARDENIQ_DB": "external"})
    assert r.returncode == 0, r.stdout + r.stderr
    assert "no MONGO_URI provided" in (r.stdout + r.stderr)
    env_text = _env_file(sandbox)
    assert not _has_env_key(env_text, "MONGO_URI")
    assert _has_env_line(env_text, "COMPOSE_FILE=docker-compose.app.yml:docker-compose.ollama.yml")


# --------------------------------------------------------------------- errors
def test_invalid_wardeniq_db_value_fails_clearly_not_silently(sandbox, boot_status_server):
    r = _run(sandbox, boot_status_server, env={"WARDENIQ_ASSUME_YES": "1", "WARDENIQ_DB": "mysql"})
    assert r.returncode == 1
    assert "invalid WARDENIQ_DB value" in (r.stdout + r.stderr)
    env_text = _env_file(sandbox)
    assert not _has_env_key(env_text, "MONGO_URI")
    assert not _has_env_key(env_text, "COMPOSE_FILE")


# ---------------------------------------------------------- credential safety
def test_external_uri_with_credentials_is_never_printed(sandbox, boot_status_server):
    """A non-interactive WARDENIQ_MONGO_URI with embedded credentials must
    never appear in stdout/stderr -- run.ps1 only ever writes it into .env,
    never Write-Host's it back (unlike a malformed-URI warning, which quotes
    the value -- that path is exercised separately, deliberately, with a
    credential-free placeholder in test_external_malformed_uri... above)."""
    secret_uri = "mongodb://produser:hunter2secret@reachable-test-host:27017/?replicaSet=rs0"
    r = _run(sandbox, boot_status_server, env={"WARDENIQ_ASSUME_YES": "1", "WARDENIQ_DB": "external",
                                               "WARDENIQ_MONGO_URI": secret_uri})
    assert r.returncode == 0, r.stdout + r.stderr
    assert "hunter2secret" not in r.stdout
    assert "hunter2secret" not in r.stderr
    # It DOES land in .env (that's the whole point -- config persistence, not a leak).
    assert "hunter2secret" in _env_file(sandbox)
