"""Vector-search degradation must be observable, not just printed.

The failure this guards: mongot is down AND the case store is past the in-memory
fallback cap, so `find_similar_cases` returns `[]`. To a caller that is indistinguishable
from "no similar cases exist", and a generation run therefore creates near-duplicates and
reports itself as clean. A log line in an untailed container is not an alert.
"""
import logging

from store import Store


class _FakeCases:
    def __init__(self, n):
        self._n = n

    def estimated_document_count(self):
        return self._n


def _store(case_count):
    """A Store with no Mongo connection — only the pieces the fallback gate touches."""
    s = Store.__new__(Store)
    s._degraded = {}
    s.cases = _FakeCases(case_count)
    return s


class TestFallbackGate:
    def test_small_store_allows_the_exact_fallback(self):
        s = _store(10)
        assert s._numpy_fallback_ok("dedup") is True
        assert s.search_degraded("dedup") is None

    def test_large_store_skips_and_records_it(self, caplog):
        s = _store(50_000)
        # The "wardeniq" logger tree doesn't propagate to the root logger (see
        # core/logging_setup.py), so attach caplog's handler directly to the
        # specific logger rather than relying on caplog's default root-based capture.
        store_logger = logging.getLogger("wardeniq.store")
        store_logger.addHandler(caplog.handler)
        try:
            with caplog.at_level("WARNING", logger="wardeniq.store"):
                assert s._numpy_fallback_ok("dedup") is False
        finally:
            store_logger.removeHandler(caplog.handler)
        rec = s.search_degraded("dedup")
        assert rec is not None
        assert rec["docs"] == 50_000
        assert rec["count"] == 1
        assert "mongot unavailable" in rec["reason"]
        # the original operator-facing log line is still emitted
        assert "skipping exact numpy fallback" in caplog.text

    def test_repeated_degradation_increments_rather_than_overwrites(self):
        s = _store(50_000)
        s._numpy_fallback_ok("dedup")
        s._numpy_fallback_ok("dedup")
        s._numpy_fallback_ok("dedup")
        assert s.search_degraded("dedup")["count"] == 3

    def test_subsystems_are_tracked_separately(self):
        s = _store(50_000)
        s._numpy_fallback_ok("dedup")
        s._numpy_fallback_ok("case search")
        assert set(s.search_degraded()) == {"dedup", "case search"}

    def test_counting_error_does_not_break_the_gate(self):
        class Exploding:
            def estimated_document_count(self):
                raise RuntimeError("mongo gone")

        s = Store.__new__(Store)
        s._degraded = {}
        s.cases = Exploding()
        # Unknown size is treated as small so dev/test keeps working.
        assert s._numpy_fallback_ok("dedup") is True

    def test_clear_resets_state(self):
        s = _store(50_000)
        s._numpy_fallback_ok("dedup")
        s.clear_search_degraded("dedup")
        assert s.search_degraded("dedup") is None

    def test_clear_all(self):
        s = _store(50_000)
        s._numpy_fallback_ok("dedup")
        s._numpy_fallback_ok("case search")
        s.clear_search_degraded()
        assert s.search_degraded() == {}


class TestFindSimilarCasesIsHonest:
    def test_empty_result_is_paired_with_a_degradation_record(self):
        """`[]` plus a degradation record means "we didn't look", not "nothing found"."""
        s = _store(50_000)

        def _boom(*_a, **_k):
            raise RuntimeError("mongot down")

        s._find_similar_cases_mongot = _boom
        assert s.find_similar_cases([0.1, 0.2], 0.85) == []
        assert s.search_degraded("dedup") is not None

    def test_genuinely_empty_result_records_nothing(self):
        s = _store(10)
        s._find_similar_cases_mongot = lambda *_a, **_k: []
        assert s.find_similar_cases([0.1, 0.2], 0.85) == []
        assert s.search_degraded("dedup") is None
