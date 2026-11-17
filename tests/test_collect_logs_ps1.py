"""collect-logs.ps1 must not stop at the first container whose logs report an error (#286).

run.ps1 sets `$ErrorActionPreference = "Stop"` and calls collect-logs.ps1 with `&`, so the
script inherits it. Under "Stop" the first native `docker logs` call that errors ends the
whole script: in Windows PowerShell 5.1 that is any stderr output redirected with `*>`
(mongot prints a Java warning), so warden-ollama.log and warden-app.log were never written.

Windows PowerShell 5.1 is not available here, so these tests emulate the same failure class
with PowerShell 7's `$PSNativeCommandUseErrorActionPreference` (a failing native command
becomes a terminating error under "Stop") and a fake `docker` on PATH. They run the real,
unmodified script and are skipped where `pwsh` is not installed.
"""
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "collect-logs.ps1"

pwsh = shutil.which("pwsh")
needs_pwsh = pytest.mark.skipif(pwsh is None, reason="PowerShell (pwsh) not installed")

CONTAINERS = [
    "warden-mongod1", "warden-mongod2", "warden-mongod3", "warden-setup",
    "warden-mongot", "warden-ollama", "warden-ollama-pull", "warden-app",
]

# mongot's `docker logs` writes a Java warning to stderr and fails; everything else is fine.
FAKE_DOCKER = """#!/usr/bin/env bash
case "$1" in
  inspect) exit 0 ;;
  logs) c="${@: -1}"
        if [ "$c" = "warden-mongot" ]; then
          echo "mongot line"; echo "WARNING: Java warning on stderr" >&2; exit 1
        fi
        echo "log line from $c"; exit 0 ;;
  compose) echo "NAME STATUS"; exit 0 ;;
esac
exit 0
"""

# Mirrors run.ps1: global Stop, native failures promoted to errors, then the best-effort call.
PARENT_STOP = """param($Script)
$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $true
try { & $Script } catch { Write-Host "log collection failed: $_" }
"""

PARENT_PLAIN = """param($Script)
& $Script
"""


def run_collect(tmp_path, parent_source):
    """Run the real collect-logs.ps1 from a temp copy; return (stdout, logs dir)."""
    work = tmp_path / "work"
    work.mkdir()
    shutil.copy(SCRIPT, work / "collect-logs.ps1")
    (work / "parent.ps1").write_text(parent_source)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    docker = bin_dir / "docker"
    docker.write_text(FAKE_DOCKER)
    docker.chmod(0o755)
    env = {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"}
    r = subprocess.run(
        [pwsh, "-NoProfile", "-File", str(work / "parent.ps1"), "-Script", str(work / "collect-logs.ps1")],
        capture_output=True, text=True, timeout=120, env=env, cwd=work)
    return r.stdout + r.stderr, work / "logs"


@needs_pwsh
def test_every_container_is_logged_when_mongots_logs_fail_under_stop(tmp_path):
    out, logs = run_collect(tmp_path, PARENT_STOP)
    for c in CONTAINERS:
        assert (logs / f"{c}.log").exists(), f"{c}.log missing; output: {out}"
    # The two logs the report said were lost.
    assert "log line from warden-ollama" in (logs / "warden-ollama.log").read_text()
    assert "log line from warden-app" in (logs / "warden-app.log").read_text()
    assert "log collection failed" not in out


@needs_pwsh
def test_the_failing_containers_own_output_is_still_kept(tmp_path):
    _, logs = run_collect(tmp_path, PARENT_STOP)
    text = (logs / "warden-mongot.log").read_text()
    assert "mongot line" in text and "Java warning on stderr" in text


@needs_pwsh
def test_status_files_are_written_and_the_script_finishes(tmp_path):
    out, logs = run_collect(tmp_path, PARENT_STOP)
    assert (logs / "_status.txt").exists()
    assert (logs / "app_status.json").exists()     # real content or "app unreachable"
    assert "done -> .\\logs\\" in out


@needs_pwsh
def test_running_the_script_on_its_own_behaves_the_same(tmp_path):
    out, logs = run_collect(tmp_path, PARENT_PLAIN)
    for c in CONTAINERS:
        assert (logs / f"{c}.log").exists(), out


def test_script_relaxes_the_error_preference_before_any_docker_call():
    lines = SCRIPT.read_text().splitlines()
    code = [(i, ln.strip()) for i, ln in enumerate(lines) if not ln.strip().startswith("#")]
    eap = next(i for i, ln in code if re.fullmatch(r'\$ErrorActionPreference\s*=\s*"Continue"', ln))
    first_docker = next(i for i, ln in code if re.match(r"docker\b", ln))
    assert eap < first_docker


def test_the_web_request_still_fails_into_its_catch_under_continue():
    # With the script default now "Continue", the request must say Stop for itself.
    text = SCRIPT.read_text()
    request = next(ln for ln in text.splitlines() if "Invoke-WebRequest" in ln and not ln.strip().startswith("#"))
    assert "-ErrorAction Stop" in request
