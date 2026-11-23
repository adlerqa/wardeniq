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
import http.server
import os
import re
import shutil
import socket
import subprocess
import threading
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
        if [ "$c" = "warden-ollama" ]; then
          echo "log line from $c"; echo "Picked up JAVA_TOOL_OPTIONS: -XX:UseSVE=0" >&2; exit 0
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


# --- #286 follow-ups: stderr wording and the app status file ---------------------------------

@needs_pwsh
def test_a_containers_stderr_line_is_kept_as_plain_text(tmp_path):
    # Windows PowerShell 5.1 wrote a "NativeCommandError / CategoryInfo / At line:" block around
    # the first stderr line of each log. PowerShell 7 does not reproduce that wrapper, so on this
    # runner the test guards the text staying intact; the wrapper itself was confirmed on 5.1.
    _, logs = run_collect(tmp_path, PARENT_STOP)
    text = (logs / "warden-ollama.log").read_text(encoding="utf-8-sig")
    assert "Picked up JAVA_TOOL_OPTIONS: -XX:UseSVE=0" in text
    assert "log line from warden-ollama" in text
    for wrapper in ("NativeCommandError", "CategoryInfo", "FullyQualifiedErrorId", "At line:", "collect-logs.ps1:"):
        assert wrapper not in text, text


def test_logs_are_written_through_tostring_not_a_raw_redirect():
    code = "\n".join(ln for ln in SCRIPT.read_text().splitlines() if not ln.strip().startswith("#"))
    assert re.search(r"docker logs --tail 400 \$c 2>&1 \| ForEach-Object \{ \$_\.ToString\(\) \}", code)
    assert "docker compose ps 2>&1 | ForEach-Object { $_.ToString() }" in code
    assert not re.search(r"docker (logs|compose ps)[^\n]*\*>", code)


def test_both_collectors_ask_the_public_boot_status_endpoint():
    # /api/status needs a login: an unauthenticated call returns 401.
    for path in (SCRIPT, REPO_ROOT / "collect-logs.sh"):
        code = "\n".join(ln for ln in path.read_text().splitlines() if not ln.strip().startswith("#"))
        assert "/api/auth/boot-status" in code, path.name
        assert "/api/status" not in code, path.name


def _port_8001_is_free():
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", 8001)) != 0


class _App:
    """A stand-in for the app on :8001 (the port collect-logs.ps1 queries)."""

    def __init__(self, routes):
        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                code, body = routes.get(self.path, (404, b'{"detail":"Not Found"}'))
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                pass

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 8001), H)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


@needs_pwsh
def test_status_file_holds_the_boot_status_when_the_app_answers(tmp_path):
    if not _port_8001_is_free():
        pytest.skip("port 8001 is in use (is the app running?)")
    app = _App({"/api/auth/boot-status": (200, b'{"stage":"indexing","ready":false}')})
    try:
        _, logs = run_collect(tmp_path, PARENT_STOP)
    finally:
        app.close()
    assert '"stage":"indexing"' in (logs / "app_status.json").read_text(encoding="utf-8-sig")


@needs_pwsh
def test_an_http_error_is_not_reported_as_unreachable(tmp_path):
    if not _port_8001_is_free():
        pytest.skip("port 8001 is in use (is the app running?)")
    app = _App({"/api/auth/boot-status": (401, b'{"detail":"Not authenticated"}')})
    try:
        _, logs = run_collect(tmp_path, PARENT_STOP)
    finally:
        app.close()
    text = (logs / "app_status.json").read_text(encoding="utf-8-sig")
    assert "401" in text and "unreachable" not in text


@needs_pwsh
def test_no_answer_at_all_is_reported_as_unreachable(tmp_path):
    if not _port_8001_is_free():
        pytest.skip("port 8001 is in use (is the app running?)")
    _, logs = run_collect(tmp_path, PARENT_STOP)
    assert "app unreachable" in (logs / "app_status.json").read_text(encoding="utf-8-sig")
