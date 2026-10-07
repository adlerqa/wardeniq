"""First-start terminal database/backend selection in run.sh (issue #109).

run.sh is a real shell script with no --dry-run mode, so these tests run the
ACTUAL, unmodified, committed script end-to-end in an isolated temp directory,
with fake `docker`, `curl`, and `mongosh` binaries placed first on PATH so no
real container, network, or MongoDB connection is ever touched -- everything
up to (and including) the point where run.sh would hand off to real Docker is
exercised for real; only Docker/network/Mongo itself is faked.

This intentionally does NOT re-implement or copy run.sh's logic -- it drives
the real file, the same way a user's terminal would, and asserts on the
resulting .env content and exit code. Interactive-menu scenarios (typing 1/2/3
at the prompt) were verified manually with a real pty (`expect`), per the
issue's own testing plan, which calls this primarily manual/Docker-based
work -- this suite covers everything reasonably automatable non-interactively.
"""
import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

FAKE_DOCKER = """#!/usr/bin/env bash
# Deterministic stand-in for `docker` -- never touches real containers/network.
if [ "$1" = "info" ]; then
  echo "${FAKE_KERNEL_VERSION:-6.1.0-generic}"
  exit 0
fi
if [ "$1" = "compose" ]; then
  # Swallow every compose subcommand (up/down/-f ... up -d --build, etc).
  exit 0
fi
exit 0
"""

FAKE_CURL = """#!/usr/bin/env bash
# run.sh only uses curl for the readiness-gate boot-status poll -- report
# ready immediately so the script doesn't sit in that 5-minute loop.
echo '{"ready":true}'
exit 0
"""

FAKE_MONGOSH = """#!/usr/bin/env bash
# Deterministic stand-in for `mongosh` -- "reachable-test-host" in the URI
# simulates a real, connectable server; anything else simulates a real,
# unreachable one. No network is ever touched.
case "$1" in
  *reachable-test-host*) exit 0 ;;
  *) exit 1 ;;
esac
"""


@pytest.fixture()
def sandbox(tmp_path):
    """A temp directory with the REAL run.sh plus everything it touches, and
    fake docker/curl/mongosh placed first on PATH."""
    shutil.copy(REPO_ROOT / "run.sh", tmp_path / "run.sh")
    os.chmod(tmp_path / "run.sh", 0o755)
    shutil.copy(REPO_ROOT / ".env.example", tmp_path / ".env.example")
    (tmp_path / "config").mkdir()
    (tmp_path / "collect-logs.sh").write_text("#!/usr/bin/env bash\nexit 0\n")
    os.chmod(tmp_path / "collect-logs.sh", 0o755)

    bin_dir = tmp_path / "fakebin"
    bin_dir.mkdir()
    for name, content in (("docker", FAKE_DOCKER), ("curl", FAKE_CURL),
                          ("mongosh", FAKE_MONGOSH)):
        p = bin_dir / name
        p.write_text(content)
        p.chmod(p.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return tmp_path, bin_dir


def _run(sandbox, env=None, kernel_version=None):
    tmp_path, bin_dir = sandbox
    # Inherit the real environment (bash/tr/sed etc. may depend on locale, HOME,
    # ... vars we have no reason to strip) but put the fakes first on PATH, and
    # clear any WARDENIQ_*/FAKE_KERNEL_VERSION this test process itself might
    # have inherited so each test's env dict is the complete, exact picture.
    full_env = {k: v for k, v in os.environ.items()
               if not k.startswith("WARDENIQ_") and k != "FAKE_KERNEL_VERSION"}
    full_env["PATH"] = f"{bin_dir}:{os.environ['PATH']}"
    if kernel_version:
        full_env["FAKE_KERNEL_VERSION"] = kernel_version
    full_env.update(env or {})
    return subprocess.run(
        ["./run.sh"], cwd=tmp_path, env=full_env,
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
def test_noninteractive_default_is_community_with_no_db_changes(sandbox):
    r = _run(sandbox, env={"WARDENIQ_ASSUME_YES": "1"})
    assert r.returncode == 0, r.stderr
    env_text = _env_file(sandbox)
    assert not _has_env_key(env_text, "MONGO_URI")
    assert not _has_env_key(env_text, "COMPOSE_FILE")


def test_existing_install_is_never_reprompted_or_changed(sandbox):
    # First run picks a backend (external here); a second run must be a no-op.
    _run(sandbox, env={"WARDENIQ_ASSUME_YES": "1", "WARDENIQ_DB": "external",
                       "WARDENIQ_MONGO_URI": "mongodb://reachable-test-host/"})
    before = _env_file(sandbox)
    r = _run(sandbox, env={"WARDENIQ_ASSUME_YES": "1"})
    assert r.returncode == 0, r.stderr
    assert _env_file(sandbox) == before


# ------------------------------------------------------------------- percona
def test_percona_selection_persists_uri_and_compose_file(sandbox):
    r = _run(sandbox, env={"WARDENIQ_ASSUME_YES": "1", "WARDENIQ_DB": "percona"})
    assert r.returncode == 0, r.stderr
    env_text = _env_file(sandbox)
    assert _has_env_line(env_text, "MONGO_URI=mongodb://mongod-percona:27017/?replicaSet=rs0")
    assert _has_env_line(env_text, "COMPOSE_FILE=docker-compose.app.yml:docker-compose.mongodb-percona.yml:docker-compose.ollama.yml")
    pwfile = sandbox[0] / "config" / "pwfile-percona"
    assert pwfile.exists()
    assert oct(pwfile.stat().st_mode)[-3:] == "400"


def test_percona_still_hits_the_kernel_guard(sandbox):
    r = _run(sandbox, env={"WARDENIQ_ASSUME_YES": "1", "WARDENIQ_DB": "percona"},
             kernel_version="6.19.0-generic")
    assert r.returncode == 1
    assert "kernel >= 6.19" in r.stderr


def test_percona_passes_the_kernel_guard_on_an_older_kernel(sandbox):
    r = _run(sandbox, env={"WARDENIQ_ASSUME_YES": "1", "WARDENIQ_DB": "percona"},
             kernel_version="6.10.0-generic")
    assert r.returncode == 0, r.stderr


def test_existing_percona_install_still_hits_kernel_guard_on_rerun(sandbox):
    # First run (good kernel) selects Percona and succeeds.
    r1 = _run(sandbox, env={"WARDENIQ_ASSUME_YES": "1", "WARDENIQ_DB": "percona"},
              kernel_version="6.10.0-generic")
    assert r1.returncode == 0, r1.stderr
    # A LATER run, on a since-upgraded (bad) kernel, must still be caught --
    # this is the exact gap #109 flagged: MONGO_URI alone must not silently
    # bypass the guard for an already-configured Percona install.
    r2 = _run(sandbox, env={"WARDENIQ_ASSUME_YES": "1"}, kernel_version="6.19.0-generic")
    assert r2.returncode == 1
    assert "kernel >= 6.19" in r2.stderr


# ------------------------------------------------------------------- external
def test_external_reachable_uri_is_saved(sandbox):
    r = _run(sandbox, env={"WARDENIQ_ASSUME_YES": "1", "WARDENIQ_DB": "external",
                           "WARDENIQ_MONGO_URI": "mongodb://reachable-test-host/"})
    assert r.returncode == 0, r.stderr
    env_text = _env_file(sandbox)
    assert _has_env_line(env_text, "MONGO_URI=mongodb://reachable-test-host/")
    assert _has_env_line(env_text, "COMPOSE_FILE=docker-compose.app.yml:docker-compose.ollama.yml")
    assert _has_env_line(env_text, "OLLAMA_URL_BUNDLED=http://host.docker.internal:11434")


def test_external_skips_the_kernel_guard_even_on_a_bad_kernel(sandbox):
    # A genuine bring-your-own database isn't started by this script, so the
    # bundled-Mongo kernel bug is irrelevant to it.
    r = _run(sandbox, env={"WARDENIQ_ASSUME_YES": "1", "WARDENIQ_DB": "external",
                           "WARDENIQ_MONGO_URI": "mongodb://reachable-test-host/"},
             kernel_version="6.19.0-generic")
    assert r.returncode == 0, r.stderr


def test_external_malformed_uri_noninteractive_warns_but_does_not_block(sandbox):
    r = _run(sandbox, env={"WARDENIQ_ASSUME_YES": "1", "WARDENIQ_DB": "external",
                           "WARDENIQ_MONGO_URI": "not-a-uri"})
    assert r.returncode == 0, r.stderr
    assert "doesn't look like a valid MongoDB connection string" in r.stderr
    assert _has_env_line(_env_file(sandbox), "MONGO_URI=not-a-uri")


def test_external_with_no_uri_at_all_still_proceeds_with_a_warning(sandbox):
    r = _run(sandbox, env={"WARDENIQ_ASSUME_YES": "1", "WARDENIQ_DB": "external"})
    assert r.returncode == 0, r.stderr
    assert "no MONGO_URI provided" in r.stderr
    env_text = _env_file(sandbox)
    assert not _has_env_key(env_text, "MONGO_URI")
    assert _has_env_line(env_text, "COMPOSE_FILE=docker-compose.app.yml:docker-compose.ollama.yml")


# --------------------------------------------------------------------- errors
def test_invalid_wardeniq_db_value_fails_clearly_not_silently(sandbox):
    r = _run(sandbox, env={"WARDENIQ_ASSUME_YES": "1", "WARDENIQ_DB": "mysql"})
    assert r.returncode == 1
    assert "invalid WARDENIQ_DB value" in r.stderr
    env_text = _env_file(sandbox)
    assert not _has_env_key(env_text, "MONGO_URI")
    assert not _has_env_key(env_text, "COMPOSE_FILE")
