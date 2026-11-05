"""Regression coverage for install.sh when no controlling terminal is available."""
import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

FAKE_DOCKER = """#!/usr/bin/env bash
if [ "$1" = "compose" ] || [ "$1" = "pull" ] || [ "$1" = "info" ] || [ "$1" = "ps" ]; then
    exit 0
fi
exit 0
"""

FAKE_CURL = """#!/usr/bin/env bash
while [ "$#" -gt 0 ]; do
    if [ "$1" = "-o" ]; then
        shift
        mkdir -p "$(dirname "$1")"
        : > "$1"
        exit 0
    fi
    shift
done
exit 1
"""


@pytest.fixture()
def installer_sandbox(tmp_path):
    shutil.copy(REPO_ROOT / "install.sh", tmp_path / "install.sh")
    os.chmod(tmp_path / "install.sh", 0o755)
    bin_dir = tmp_path / "fakebin"
    bin_dir.mkdir()
    for name, content in (("docker", FAKE_DOCKER), ("curl", FAKE_CURL)):
        path = bin_dir / name
        path.write_text(content)
        path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return tmp_path, bin_dir


def test_installer_uses_defaults_without_a_controlling_terminal(installer_sandbox):
    tmp_path, bin_dir = installer_sandbox
    env = {
        key: value for key, value in os.environ.items()
        if not key.startswith("WARDENIQ_")
    }
    env["PATH"] = f"{bin_dir}:{os.environ['PATH']}"
    result = subprocess.run(
        ["bash", "./install.sh"],
        cwd=tmp_path,
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=30,
        start_new_session=True,
    )

    assert result.returncode == 0, result.stderr
    assert "No such device or address" not in result.stderr
    assert "How do you want to run wardenIQ?" not in result.stdout
    assert "mode:" in result.stdout
    assert (tmp_path / "wardeniq" / ".env").exists()
