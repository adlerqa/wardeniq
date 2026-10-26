import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_mongod_config_documents_grpc_requirement():
    config = (ROOT / "config" / "mongod.conf").read_text(encoding="utf-8")
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")
    configuration_doc = (ROOT / "docs" / "configuration.md").read_text(encoding="utf-8")

    assert "useGrpcForSearch: true" in config

    # Assert the underlying facts (the pinned bundled MongoDB image meets the
    # 8.1+ floor useGrpcForSearch requires, and that floor is documented near
    # the pin) rather than exact comment prose, so a future rewording of the
    # explanatory comments doesn't red the build for a reason unrelated to
    # what this test actually protects.
    match = re.search(
        r"MONGO_IMAGE=mongodb/mongodb-community-server:(\d+)\.(\d+)", env_example
    )
    assert match, "MONGO_IMAGE in .env.example should pin a mongodb-community-server version"
    pinned_version = (int(match.group(1)), int(match.group(2)))
    assert pinned_version >= (8, 1), (
        f"MONGO_IMAGE pins MongoDB {pinned_version[0]}.{pinned_version[1]}, "
        "but useGrpcForSearch requires 8.1 or newer"
    )

    env_lines = env_example.splitlines()
    mongo_image_idx = next(
        i for i, line in enumerate(env_lines) if line.startswith("MONGO_IMAGE=")
    )
    preceding_comment = "\n".join(env_lines[max(0, mongo_image_idx - 5):mongo_image_idx])
    assert "8.1" in preceding_comment, (
        ".env.example should document the 8.1+ floor in a comment near MONGO_IMAGE"
    )

    assert "MongoDB must be **8.1+**" in configuration_doc
    assert "do NOT set the Percona-specific flags" not in config
