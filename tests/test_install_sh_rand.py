"""Coverage for install.sh's rand() on a host without openssl (#271).

Without openssl the function reads /dev/urandom, and `tr` dies of SIGPIPE
once `head` has its bytes. Under `set -euo pipefail` that failed the whole
pipeline, so the installer stopped with a bare status 141 and no message.
"""
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def rand_function() -> str:
    """The rand() function of install.sh, as the shell reads it."""
    source = (REPO_ROOT / "install.sh").read_text(encoding="utf-8")
    start = source.index("rand() {")
    end = source.index("\n}\n", start) + len("\n}\n")
    return source[start:end]


@pytest.fixture()
def tools_without_openssl(tmp_path):
    """A PATH with the tools rand() needs, and without openssl.

    Only tr and head are linked into it, so `command -v openssl` finds
    nothing and rand() reads /dev/urandom, the way it does on a host that
    has no openssl.
    """
    missing = [name for name in ("bash", "tr", "head") if shutil.which(name) is None]
    if missing:
        pytest.skip(f"{', '.join(missing)} not on PATH on this machine")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name in ("tr", "head"):
        (bin_dir / name).symlink_to(shutil.which(name))
    for name in ("tr", "head"):
        probe = subprocess.run(
            [shutil.which("bash"), "-c", f'PATH="{bin_dir}" {name} --version'],
            capture_output=True,
        )
        if probe.returncode != 0:
            pytest.skip(f"{name} does not run from the sandbox on this machine")
    return bin_dir


def run_rand(function: str, tools: Path, *args: str) -> subprocess.CompletedProcess:
    """Runs rand() with the given arguments under the installer's shell options."""
    script = f'set -euo pipefail\n{function}\nrand "$@"\n'
    return subprocess.run(
        [shutil.which("bash"), "-c", script, "rand", *args],
        env={"PATH": str(tools), "LC_ALL": "C"},
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_rand_succeeds_without_openssl(tools_without_openssl):
    result = run_rand(rand_function(), tools_without_openssl, "32")

    assert result.returncode == 0, (
        f"rand() failed with {result.returncode}: {result.stderr!r}"
    )
    assert len(result.stdout) == 32
    assert result.stdout.isalnum()


def test_rand_reports_a_host_without_any_random_source(tools_without_openssl):
    # Point the reader at a path that does not exist: that is what a host
    # without /dev/urandom looks like to the function.
    function = rand_function().replace("/dev/urandom", "/nonexistent/urandom")

    result = run_rand(function, tools_without_openssl, "32")

    assert result.returncode != 0
    assert "openssl" in result.stderr
    assert "urandom" in result.stderr
