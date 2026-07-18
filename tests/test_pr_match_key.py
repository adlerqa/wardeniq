"""Unit tests for the manual PR match-tag fallback in coverage.map_pr_to_feature.

Uses a duck-typed fake store (the function only calls feature_by_epic and
features_with_match_key), so no MongoDB is required.
"""
import coverage


class FakeStore:
    def __init__(self, epics=None, match_keys=None):
        self._epics = epics or {}          # epic key -> feature id
        self._mk = match_keys or []        # list of (feature_id, match_key)

    def feature_by_epic(self, project_id, key):
        return self._epics.get(key)

    def features_with_match_key(self, project_id):
        return list(self._mk)


def _map(store, title, body=""):
    return coverage.map_pr_to_feature(store, None, {"title": title, "body": body}, "p1")


def test_bracketed_tag_maps_when_no_jira_key():
    fid, conf, method = _map(FakeStore(match_keys=[("f1", "HOLDS")]),
                             "feat: add holds queue [HOLDS]")
    assert (fid, conf, method) == ("f1", 1.0, "tag:[HOLDS]")


def test_tag_match_is_case_insensitive():
    fid, _, _ = _map(FakeStore(match_keys=[("f1", "HOLDS")]), "[holds] fix positions")
    assert fid == "f1"


def test_unbracketed_keyword_does_not_match():
    # Explicit [KEY] tag rule: 'feat(HOLDS):' contains HOLDS but not '[HOLDS]'.
    fid, _, method = _map(FakeStore(match_keys=[("f1", "HOLDS")]), "feat(HOLDS): add holds")
    assert fid is None and method == "unmapped"


def test_no_tag_and_no_key_is_unmapped():
    fid, _, method = _map(FakeStore(match_keys=[("f1", "HOLDS")]), "chore: bump deps")
    assert fid is None and method == "unmapped"


def test_jira_epic_takes_precedence_over_tag():
    store = FakeStore(epics={"ABC-12": "fepic"}, match_keys=[("f1", "HOLDS")])
    fid, _, method = _map(store, "ABC-12 wire up [HOLDS]")
    assert fid == "fepic" and method == "epic:ABC-12"
