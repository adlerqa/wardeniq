"""The one-shot setup containers must be able to read the mongot password file (#285).

run.sh and install.sh keep config/pwfile (and config/pwfile-percona) at mode 400, owned
by whoever ran them. A container running as a different uid cannot read it:

    /setup-replica-set.sh: line 82: /run/secrets/mongot-pw: Permission denied

The bundled MongoDB image's default user is uid 1000 and the Percona image's is uid 1001,
so on any Linux host whose user is not that uid (root, a second user, most CI runners) the
setup container died, mongot never started and boot stayed at "indexing" forever.

The setup services therefore run as root. PyYAML is not a project dependency, so these
tests read each service's block from the compose file directly instead of parsing YAML.
"""
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

# (compose file, setup service, secret file it mounts at /run/secrets/mongot-pw)
SETUP_SERVICES = [
    ("docker-compose.mongodb.yml", "mongod-setup", "config/pwfile"),
    ("docker-compose.mongodb-percona.yml", "mongod-percona-setup", "config/pwfile-percona"),
]


def service_block(compose_file: str, service: str) -> list[str]:
    """Lines of one top-level service (indented two spaces) up to the next service."""
    lines = (REPO_ROOT / compose_file).read_text().splitlines()
    start = next(i for i, ln in enumerate(lines) if re.fullmatch(rf"  {re.escape(service)}:\s*", ln))
    block = []
    for ln in lines[start + 1:]:
        if re.match(r"  \S", ln) or re.match(r"\S", ln):   # next service or next top-level key
            break
        block.append(ln)
    return block


def active(lines: list[str]) -> list[str]:
    """Drop comment-only lines so a commented-out `user:` can't satisfy a test."""
    return [ln for ln in lines if not ln.lstrip().startswith("#")]


@pytest.mark.parametrize("compose_file,service,secret", SETUP_SERVICES)
def test_setup_service_mounts_the_secret(compose_file, service, secret):
    block = "\n".join(active(service_block(compose_file, service)))
    assert f"./{secret}:/run/secrets/mongot-pw:ro" in block


@pytest.mark.parametrize("compose_file,service,secret", SETUP_SERVICES)
def test_setup_service_runs_as_root_so_it_can_read_the_secret(compose_file, service, secret):
    block = active(service_block(compose_file, service))
    users = [re.fullmatch(r"    user:\s*[\"']?([^\"'\s#]+)[\"']?\s*(#.*)?", ln) for ln in block]
    users = [m.group(1) for m in users if m]
    assert users == ["0:0"], f"{service} must set exactly one `user: \"0:0\"`, found {users}"


@pytest.mark.parametrize("compose_file,service,secret", SETUP_SERVICES)
def test_setup_service_stays_a_one_shot(compose_file, service, secret):
    # Running as root is only acceptable because the container is short-lived.
    block = "\n".join(active(service_block(compose_file, service)))
    assert re.search(r'restart:\s*"?no"?', block)


def test_service_block_helper_stops_at_the_next_service():
    block = "\n".join(service_block("docker-compose.mongodb.yml", "mongod-setup"))
    assert "setup-replica-set.sh" in block
    assert "wardeniq-mongot-entrypoint.sh" not in block      # that is the mongot service


def test_mongot_is_not_changed_it_already_reads_the_secret_as_root():
    # mongot's own entrypoint copies the secret to a private path; its image runs as root.
    block = "\n".join(active(service_block("docker-compose.mongodb.yml", "mongot")))
    assert "user:" not in block
