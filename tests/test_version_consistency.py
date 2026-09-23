import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _canonical_version() -> str:
    config = (ROOT / "app" / "core" / "config.py").read_text(encoding="utf-8")
    match = re.search(r'^VERSION = "([^"]+)"', config, re.MULTILINE)
    assert match, "app/core/config.py should define VERSION"
    return match.group(1)


def test_readme_version_matches_canonical_source():
    version = _canonical_version()
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert f"`v{version}`" in readme, (
        f"README.md's version line should match app/core/config.py's VERSION ({version})"
    )


def test_docker_compose_app_image_default_matches_canonical_source():
    version = _canonical_version()
    compose = (ROOT / "docker-compose.app.yml").read_text(encoding="utf-8")
    assert f"wardeniq:{version}" in compose, (
        "docker-compose.app.yml's APP_IMAGE default should match "
        f"app/core/config.py's VERSION ({version})"
    )


def test_no_stale_beta_version_string_in_user_facing_files():
    # refactor-baseline/ is an intentional historical snapshot and excluded.
    for relative in ("README.md", "CONTRIBUTING.md", "SECURITY.md", "PROJECT_CONTEXT.md"):
        text = (ROOT / relative).read_text(encoding="utf-8")
        assert "0.1.0-beta" not in text, f"{relative} still references the stale 0.1.0-beta version"
