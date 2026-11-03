"""Tests for `contracts.extract_key_writes_from_lines`: which literal keys a set of source
lines writes, and in which bucket (dict vs attr)."""
import contracts


def test_dict_call_records_every_keyword_argument():
    # Regression: only the first keyword of dict(...) was captured, so `role` never
    # counted as written and a later read of it looked orphaned.
    assert contracts.extract_key_writes_from_lines(["claims = dict(user_id=uid, role=r)"]) == {
        "user_id": {"dict"}, "role": {"dict"}}


def test_dict_call_ignores_keywords_of_nested_calls():
    assert contracts.extract_key_writes_from_lines(["d = dict(name=fmt(x, upper=True), age=a)"]) == {
        "name": {"dict"}, "age": {"dict"}}


def test_comparison_is_not_a_keyword():
    assert contracts.extract_key_writes_from_lines(["ok = dict(flag=a == b)"]) == {"flag": {"dict"}}
