"""PowerShell launcher regression tests for issue #284."""
import os
import shutil
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]


def _powershell():
    executable = shutil.which("pwsh") or shutil.which("powershell")
    if not executable:
        pytest.skip("PowerShell is not installed")
    return executable


def test_run_ps1_stops_immediately_when_compose_build_fails(tmp_path):
    executable = _powershell()
    if os.name == "nt":
        docker_path = tmp_path / "fakebin" / "docker.cmd"
        docker_content = "@echo off\r\nexit /b %FAKE_COMPOSE_EXIT_CODE%\r\n"
    else:
        docker_path = tmp_path / "fakebin" / "docker"
        docker_content = "#!/bin/sh\nexit \"$FAKE_COMPOSE_EXIT_CODE\"\n"

    bin_dir = docker_path.parent
    bin_dir.mkdir()
    docker_path.write_text(docker_content, encoding="ascii")
    if os.name != "nt":
        docker_path.chmod(0o755)

    shutil.copy(REPO_ROOT / "run.ps1", tmp_path / "run.ps1")
    (tmp_path / "config").mkdir()
    (tmp_path / ".env").write_text(
        "MONGO_URI=mongodb://external.invalid/?directConnection=true\n"
        "COMPOSE_FILE=docker-compose.app.yml:docker-compose.ollama.yml\n",
        encoding="ascii",
    )

    env = os.environ.copy()
    env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")
    env["FAKE_COMPOSE_EXIT_CODE"] = "23"
    result = subprocess.run(
        [executable, "-NoProfile", "-File", str(tmp_path / "run.ps1")],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    output = result.stdout + result.stderr
    assert result.returncode == 1, output
    assert "build/start failed, see above" in output
    assert "waiting for wardenIQ to become ready" not in output


def test_run_ps1_checks_build_exit_code_before_readiness_loop():
    source = (REPO_ROOT / "run.ps1").read_text(encoding="ascii")
    compose_start = source.index("docker @Compose up -d --build")
    exit_check = source.index("if ($LASTEXITCODE -ne 0)", compose_start)
    error_message = source.index("build/start failed, see above", exit_check)
    readiness_marker = "==> waiting for wardenIQ to become ready"
    readiness_wait = source.index(readiness_marker, error_message)

    assert compose_start < exit_check < error_message < readiness_wait
    assert "exit 1" in source[exit_check:readiness_wait]
