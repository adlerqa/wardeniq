"""Consistency checks for the Percona validation config (issue #41) — mirrors
tests/test_mongodb_config.py's string-based approach (no YAML parser dependency;
none is declared in app/requirements*.txt) for the default MongoDB Community config.
No Docker/network required; these assert the files agree with each other and with
the compose file, not that Percona is actually reachable (see
docs/percona-search-validation.md for the real, live-Percona validation results).
"""
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_percona_compose_does_not_touch_the_default_stack():
    """The Percona compose file must be additive-only: it must not redefine any
    service/network name the default MongoDB Community stack
    (docker-compose.mongodb.yml) uses, so the two can never collide if both are
    referenced on the same `docker compose -f ... -f ...` command line."""
    default_compose = (ROOT / "docker-compose.mongodb.yml").read_text(encoding="utf-8")
    percona_compose = (ROOT / "docker-compose.mongodb-percona.yml").read_text(encoding="utf-8")

    default_services = set(re.findall(r"^  ([\w-]+):\s*$", default_compose, re.MULTILINE))
    percona_services = set(re.findall(r"^  ([\w-]+):\s*$", percona_compose, re.MULTILINE))
    assert default_services, "sanity check: should have found the default stack's services"
    assert percona_services, "sanity check: should have found the Percona stack's services"
    assert not (default_services & percona_services), (
        f"service name collision: {default_services & percona_services}"
    )

    assert 'name: warden-net-percona' in percona_compose
    assert 'name: warden-net-percona' not in default_compose
    assert "name: warden-net\n" in default_compose

    # The Percona file must not expose host ports by default (matches the default
    # stack's security posture: no port published without the explicit db-ports
    # overlay).
    assert "ports:" not in percona_compose


def test_mongod_percona_config_uses_percona_specific_parameters():
    config = (ROOT / "config" / "mongod-percona.conf").read_text(encoding="utf-8")

    assert "useGrpcForSearch: true" in config
    # These two exist on Percona but not on official MongoDB Community mongod (#29) —
    # the whole point of this file being separate from config/mongod.conf.
    assert "skipAuthenticationToSearchIndexManagementServer: false" in config
    assert "searchTLSMode: disabled" in config


def test_mongot_percona_config_matches_the_images_actual_schema():
    """Percona's mongot config nests auth under syncSource.replicaSet.scramAuth,
    unlike MongoDB Community mongot (config/mongot.conf), which puts
    username/passwordFile directly under syncSource.replicaSet. Confirmed by reading
    percona/percona-search-mongodb:1.70.4's own shipped default config — see
    docs/percona-search-validation.md."""
    percona_mongot = (ROOT / "config" / "mongot-percona.yml").read_text(encoding="utf-8")
    community_mongot = (ROOT / "config" / "mongot.conf").read_text(encoding="utf-8")

    assert "scramAuth" in percona_mongot, "Percona mongot config must nest auth under scramAuth"
    assert "username: mongotUser" in percona_mongot
    assert "scramAuth" not in community_mongot, (
        "Community mongot config should NOT use Percona's scramAuth nesting "
        "(this test would need updating if that ever changes)"
    )


def test_mongod_and_mongot_percona_agree_on_the_grpc_address():
    mongod_config = (ROOT / "config" / "mongod-percona.conf").read_text(encoding="utf-8")
    mongot_config = (ROOT / "config" / "mongot-percona.yml").read_text(encoding="utf-8")

    host_match = re.search(r"mongotHost:\s*(\S+)", mongod_config)
    seaidx_match = re.search(r"searchIndexManagementHostAndPort:\s*(\S+)", mongod_config)
    grpc_match = re.search(r'address:\s*"([^"]+)"\s*\n\s*tls:', mongot_config)

    assert host_match and seaidx_match and grpc_match, "could not locate all three addresses"
    assert host_match.group(1) == seaidx_match.group(1) == grpc_match.group(1), (
        "mongod's mongotHost/searchIndexManagementHostAndPort must match mongot's own "
        "advertised gRPC address, or mongod can't reach it"
    )


def test_percona_images_are_pinned_not_floating_latest():
    compose = (ROOT / "docker-compose.mongodb-percona.yml").read_text(encoding="utf-8")
    mongod_match = re.search(r"MONGO_IMAGE_PERCONA:-percona/percona-server-mongodb:([\w.\-]+)", compose)
    mongot_match = re.search(r"MONGOT_IMAGE_PERCONA:-percona/percona-search-mongodb:([\w.\-]+)", compose)
    assert mongod_match and mongod_match.group(1) not in ("latest", ""), (
        "mongod-percona image tag should be pinned"
    )
    assert mongot_match and mongot_match.group(1) not in ("latest", ""), (
        "mongot-percona image tag should be pinned"
    )
