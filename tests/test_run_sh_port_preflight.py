"""Port pre-flight + container-state checks in run.sh (issue #190).

Same harness as tests/test_run_sh_db_selection.py: the REAL run.sh runs
end-to-end in an isolated temp directory with fake `docker`/`curl` first on
PATH, so no real container or network is ever touched. Port occupancy is
real, not faked: tests bind an actual listening socket on 127.0.0.1:8001 /
:11434, which is exactly what run.sh's /dev/tcp probe sees from a host
Ollama or any other process squatting the port.
"""
import contextlib
import os
import shutil
import socket
import stat
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

FAKE_DOCKER = """#!/usr/bin/env bash
# Deterministic stand-in for `docker` -- never touches real containers.
if [ "$1" = "info" ]; then
  echo "${FAKE_KERNEL_VERSION:-6.1.0-generic}"
  exit 0
fi
if [ "$1" = "compose" ]; then
  [ -n "$FAKE_UP_MARKER" ] && touch "$FAKE_UP_MARKER"
  [ "$FAKE_COMPOSE_FAIL" = "1" ] && exit 1
  exit 0
fi
if [ "$1" = "ps" ]; then
  if [ "$2" = "-a" ]; then echo "$FAKE_PS_A"; else echo "$FAKE_PS"; fi
  exit 0
fi
if [ "$1" = "logs" ]; then
  echo "$FAKE_LOGS"
  exit 0
fi
exit 0
"""

FAKE_CURL = """#!/usr/bin/env bash
echo '{"ready":true}'
exit 0
"""


@pytest.fixture()
def sandbox(tmp_path):
    """Temp dir with the REAL run.sh plus everything it touches, and fake
    docker/curl placed first on PATH."""
    shutil.copy(REPO_ROOT / "run.sh", tmp_path / "run.sh")
    os.chmod(tmp_path / "run.sh", 0o755)
    shutil.copy(REPO_ROOT / ".env.example", tmp_path / ".env.example")
    (tmp_path / "config").mkdir()
    (tmp_path / "collect-logs.sh").write_text("#!/usr/bin/env bash\nexit 0\n")
    os.chmod(tmp_path / "collect-logs.sh", 0o755)

    bin_dir = tmp_path / "fakebin"
    bin_dir.mkdir()
    for name, content in (("docker", FAKE_DOCKER), ("curl", FAKE_CURL)):
        p = bin_dir / name
        p.write_text(content)
        p.chmod(p.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return tmp_path, bin_dir


def _run(sandbox, env=None):
    tmp_path, bin_dir = sandbox
    full_env = {k: v for k, v in os.environ.items()
                if not k.startswith("WARDENIQ_") and not k.startswith("FAKE_")}
    full_env["PATH"] = f"{bin_dir}:{os.environ['PATH']}"
    full_env["WARDENIQ_ASSUME_YES"] = "1"
    full_env.update(env or {})
    return subprocess.run(
        ["./run.sh"], cwd=tmp_path, env=full_env,
        stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=30,
    )


@contextlib.contextmanager
def _listener(port):
    """A real listening socket on 127.0.0.1:port -- a host process squatting
    it, as seen by run.sh's /dev/tcp probe."""
    s = socket.socket()
    try:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("127.0.0.1", port))
        s.listen(1)
    except OSError:
        pytest.skip(f"port {port} already occupied in this environment")
    try:
        yield
    finally:
        s.close()


# ------------------------------------------------------------ port pre-flight
def test_11434_occupied_by_host_process_fails_fast_before_up(sandbox):
    marker = sandbox[0] / "up-called"
    with _listener(11434):
        r = _run(sandbox, env={"FAKE_UP_MARKER": str(marker)})
    assert r.returncode == 1, r.stderr
    assert "port 11434" in r.stderr
    assert "host Ollama" in r.stderr
    assert not marker.exists()  # never reached `docker compose up`


def test_11434_occupied_but_by_our_own_container_proceeds(sandbox):
    with _listener(11434):
        r = _run(sandbox, env={
            "FAKE_PS": "warden-ollama 0.0.0.0:11434->11434/tcp"})
    assert r.returncode == 0, r.stderr


def test_8001_occupied_fails_fast_before_up(sandbox):
    marker = sandbox[0] / "up-called"
    with _listener(8001):
        r = _run(sandbox, env={"FAKE_UP_MARKER": str(marker)})
    assert r.returncode == 1, r.stderr
    assert "port 8001" in r.stderr
    assert not marker.exists()


def test_app_only_mode_skips_the_11434_check(sandbox):
    # .env pins a compose set without the ollama file: a host Ollama on 11434
    # is the expected configuration, not a collision.
    (sandbox[0] / ".env").write_text(
        "COMPOSE_FILE=docker-compose.app.yml:docker-compose.mongodb.yml\n")
    with _listener(11434):
        r = _run(sandbox)
    assert r.returncode == 0, r.stderr


# ------------------------------------------------------- container-state gate
def test_dead_ollama_right_after_up_fails_fast_with_its_logs(sandbox):
    r = _run(sandbox, env={
        "FAKE_PS_A": "warden-ollama Exited (1) 2 minutes ago",
        "FAKE_LOGS": "Error: listen tcp 0.0.0.0:11434: bind: address already in use"})
    assert r.returncode == 1, r.stderr
    assert "first failing container: warden-ollama" in r.stderr
    assert "bind: address already in use" in r.stderr


def test_one_shot_containers_exiting_zero_are_not_failures(sandbox):
    r = _run(sandbox, env={
        "FAKE_PS_A": "warden-setup Exited (0) 3 minutes ago\n"
                      "warden-ollama-pull Exited (0) 2 minutes ago"})
    assert r.returncode == 0, r.stderr


def test_compose_up_failure_fails_fast_instead_of_waiting_5_minutes(sandbox):
    r = _run(sandbox, env={"FAKE_COMPOSE_FAIL": "1"})
    assert r.returncode == 1, r.stderr
    assert "docker compose up failed" in r.stderr
