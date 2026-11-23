"""Coverage for the category-agnostic content-grounding guard.

Origin: manual RAG validation from the real product UI (Authentication feature,
2026-09-01) found that generated ui_validations cases stated specific numeric
requirements -- "Phone number must not exceed 15 characters", "One-time code must be
exactly 6 digits" -- that had zero textual support anywhere in the retrieved OR the
full evidence corpus (verified against all 12 chunks of the source document). The
existing grounding checks (_filter_api_tests / _filter_ui_tests / _grounded_item_
supported) only verify a case's SUBJECT is real (a real endpoint, a real field name);
none of them verify a case's CONTENT (a specific number/limit/value) is actually
backed by evidence.

Per explicit instruction this is NOT an Authentication-specific fix. Every fixture
below uses feature domains unrelated to Authentication (grocery checkout, hotel
booking) to prove the guard carries no feature- or category-specific keywords, and
exercises all five suite types (api_tests/ui_validations/e2e_tests/edge_cases/
business_tests).
"""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from testgen.service import (  # noqa: E402
    _filter_ungrounded_claims,
    _unsupported_numeric_claims,
    generate_fresh_testcases_pipeline,
)
from tests.test_generation_pipeline import (  # noqa: E402
    FakeEmbedder, FakeLLM, FakeStore, ui_cases_with_citations,
)


# --------------------------------------------------------------------------------
# Part 1: pure unit tests on the guard functions themselves -- no pipeline, no LLM,
# no store. Fast, precise, and the clearest place to prove the exact properties the
# task asked for.
# --------------------------------------------------------------------------------

# A grocery-checkout PRD corpus. Deliberately unrelated to Authentication, and
# deliberately contains a number (30) in an UNRELATED unit context (minutes, for
# order-expiry) alongside real, grounded numeric requirements the guard should
# recognize as supported.
GROCERY_CORPUS = (
    "an abandoned cart with items reserved expires after 30 minutes and the "
    "reserved inventory is released. a promo code discount must not exceed 20 "
    "percent of the order subtotal. delivery orders require a minimum subtotal of "
    "25 dollars. a single order may contain at most 40 line items."
).lower()

# A hotel-booking PRD corpus, again unrelated to Authentication, used to prove the
# guard generalizes across a second, independent domain.
HOTEL_CORPUS = (
    "a reservation may be cancelled free of charge up to 48 hours before check-in. "
    "guests must be at least 18 years old to book a room. a room may be held for "
    "15 minutes during checkout before the hold expires."
).lower()


class UnsupportedNumericClaimsTests(unittest.TestCase):
    def test_grounded_numeric_requirement_is_not_flagged(self):
        """A category with relevant evidence: a case restating a real, sourced
        number must survive untouched -- existing well-grounded behavior must not
        regress."""
        case = {
            "title": "Promo code discount must not exceed 20 percent of the subtotal",
            "steps": [],
        }
        self.assertEqual(_unsupported_numeric_claims(case, GROCERY_CORPUS), [])

    def test_ungrounded_numeric_requirement_is_flagged(self):
        """A category with no relevant evidence for this specific claim: a
        plausible-sounding but wholly invented limit must be caught, not fabricated
        into the delivered suite."""
        case = {
            "title": "Gift message must not exceed 500 characters",
            "steps": [],
        }
        flagged = _unsupported_numeric_claims(case, GROCERY_CORPUS)
        self.assertTrue(flagged, "an unsupported '500 characters' claim must be flagged")

    def test_unrelated_number_elsewhere_in_corpus_is_not_treated_as_evidence(self):
        """The corpus contains '30 minutes' (cart expiry) -- a fabricated claim that
        happens to reuse the same digits for a DIFFERENT unit ('30 items') must
        still be flagged. A naive "is this digit anywhere in the corpus" check
        would wrongly treat the unrelated fact as support; this must not."""
        case = {
            "title": "A single wishlist must not contain more than 30 items",
            "steps": [],
        }
        flagged = _unsupported_numeric_claims(case, GROCERY_CORPUS)
        self.assertTrue(
            flagged,
            "'30 items' must not be considered grounded just because '30' appears "
            "elsewhere in the corpus for an unrelated fact (minutes, not items)",
        )

    def test_reasonable_derived_scenario_without_a_specific_number_is_not_flagged(self):
        """A general, unnumbered scenario reasonably derived from the feature intent
        (no specific value asserted) is not fabrication and must never be flagged --
        this is the middle 'reasonable derived scenario' tier, distinct from both
        grounded facts and unsupported assumptions."""
        case = {
            "title": "Ensure a delivery address is provided before checkout completes",
            "steps": [{"content": "Submit checkout without an address",
                       "expectedResult": "Checkout is prevented"}],
        }
        self.assertEqual(_unsupported_numeric_claims(case, GROCERY_CORPUS), [])

    def test_paraphrased_and_hyphenated_grounded_numbers_still_match(self):
        """Real PRD prose often hyphenates a number and its unit ('10-minute
        window'); generated case text often doesn't. The guard must not
        false-positive on this kind of harmless paraphrase."""
        case = {
            "title": "A room hold must expire after 15 minutes during checkout",
            "steps": [],
        }
        self.assertEqual(_unsupported_numeric_claims(case, HOTEL_CORPUS), [])

    def test_works_on_a_second_unrelated_domain(self):
        """Same guard, a completely different feature domain (hotel booking, not
        grocery, not Authentication) -- proves there is nothing domain-specific
        baked into the guard itself."""
        grounded = {"title": "Guests must be at least 18 years old to book a room", "steps": []}
        fabricated = {"title": "A reservation must be cancelled at least 72 hours before check-in", "steps": []}
        self.assertEqual(_unsupported_numeric_claims(grounded, HOTEL_CORPUS), [])
        self.assertTrue(_unsupported_numeric_claims(fabricated, HOTEL_CORPUS))


class ClaimSegmentTests(unittest.TestCase):
    """What counts as a CLAIM. A case is not one undifferentiated blob of text: a step's
    action is an input the tester supplies, while titles, intents and expectations
    assert something about the product. Judging them all together produced a false
    positive on exactly the kind of case this pipeline should be best at -- a boundary
    probe of a documented limit (found by tests/test_rag_evidence_sufficiency.py's
    end-to-end UI scenario, where a grounded 240-character limit was dropped because its
    negative step typed 241 characters)."""

    def test_boundary_probe_of_a_grounded_limit_is_not_flagged(self):
        """The corpus states a 20 percent cap. A negative test for it necessarily uses a
        value the corpus never states (21 percent) as its INPUT. That is a correct,
        well-grounded test, not a fabricated requirement."""
        case = {
            "title": "A promo discount above the maximum is rejected",
            "steps": [{
                "content": "Apply a promo code worth 21 percent of the subtotal",
                "expectedResult": "The discount is rejected",
            }],
        }
        self.assertEqual(_unsupported_numeric_claims(case, GROCERY_CORPUS), [])

    def test_a_fabricated_limit_asserted_in_a_step_expectation_is_still_flagged(self):
        """Excluding step ACTIONS must not blunt the guard: an expectation is an
        assertion about the product, and a fabricated limit stated there is caught."""
        case = {
            "title": "Checkout handles a large gift message",
            "steps": [{
                "content": "Enter a long gift message",
                "expectedResult": "The message must not exceed 500 characters",
            }],
        }
        self.assertTrue(_unsupported_numeric_claims(case, GROCERY_CORPUS))

    def test_segments_are_judged_independently_of_one_another(self):
        """Generated case text rarely ends in a period, so joined into one string a whole
        case became a single marker-matching 'sentence': one step's "rejected" licensed
        judging every number anywhere else in the case. Here the title carries a grounded
        number and the action an ungrounded one; neither may contaminate the other."""
        case = {
            "title": "A promo code discount must not exceed 20 percent of the subtotal",
            "steps": [{
                "content": "Apply a promo code worth 37 percent",
                "expectedResult": "The discount is rejected",
            }],
        }
        self.assertEqual(_unsupported_numeric_claims(case, GROCERY_CORPUS), [])


class FilterUngroundedClaimsTests(unittest.TestCase):
    """The same checks as above, but through the list-level filter that actually
    gets wired into the pipeline, and across all five suite shapes -- api_tests,
    ui_validations, e2e_tests, edge_cases, business_tests -- to prove the guard is
    applied uniformly rather than being category-specific."""

    def test_uniform_across_all_five_categories(self):
        grounded_by_category = {
            "api_tests": {"title": "Applying a promo code must not exceed 20 percent off", "method": "POST", "endpoint": "/checkout/promo"},
            "ui_validations": {"title": "Promo field must not exceed 20 percent discount", "field": "Promo Code"},
            "e2e_tests": {"title": "Checkout enforces the 20 percent maximum promo discount", "steps": []},
            "edge_cases": {"title": "A stacked promo attempt must not exceed 20 percent total discount", "steps": []},
            "business_tests": {"title": "Business rule: discount must not exceed 20 percent of subtotal", "steps": []},
        }
        fabricated_by_category = {
            "api_tests": {"title": "API rate limit must not exceed 500 requests per minute", "method": "POST", "endpoint": "/checkout/promo"},
            "ui_validations": {"title": "Promo field must not exceed 12 characters", "field": "Promo Code"},
            "e2e_tests": {"title": "Checkout session must expire after 90 seconds of inactivity", "steps": []},
            "edge_cases": {"title": "At most 7 promo attempts may be made per session", "steps": []},
            "business_tests": {"title": "Business rule: refunds must be processed within 3 hours", "steps": []},
        }
        for category in grounded_by_category:
            with self.subTest(category=category):
                kept = _filter_ungrounded_claims(
                    [grounded_by_category[category], fabricated_by_category[category]],
                    GROCERY_CORPUS,
                )
                titles = [case["title"] for case in kept]
                self.assertIn(
                    grounded_by_category[category]["title"], titles,
                    f"a well-grounded {category} case must not regress",
                )
                self.assertNotIn(
                    fabricated_by_category[category]["title"], titles,
                    f"a fabricated {category} case must be dropped",
                )

    def test_non_dict_entries_are_ignored_not_raised(self):
        self.assertEqual(_filter_ungrounded_claims([None, "not a case", 42], GROCERY_CORPUS), [])


# --------------------------------------------------------------------------------
# Part 2: through the REAL pipeline (generate_fresh_testcases_pipeline), reusing
# test_generation_pipeline.py's existing FakeStore/FakeEmbedder fixture (an
# order-creation feature -- yet another domain unrelated to Authentication) to prove
# the guard is actually wired in at the right point and doesn't disturb existing,
# already-grounded generation behavior end to end.
# --------------------------------------------------------------------------------

class GroundingGuardFakeLLM(FakeLLM):
    """FakeStore's evidence text (see test_generation_pipeline.FakeStore) never
    states any specific number, so any numeric requirement claim injected below is
    guaranteed unsupported -- an easy, unambiguous fabrication to detect, alongside
    the suite's existing, legitimately-grounded (non-numeric) cases."""

    def chat_json(self, system, user, **kwargs):
        if "Generate focused API worker test cases" in user and "HAPPY PATH TESTS ONLY" in user:
            result = super().chat_json(system, user, **kwargs)
            result["api_tests"].append({
                "title": "Order creation rate limit must not exceed 500 requests per minute",
                "intent": "fabricated -- no such limit anywhere in the evidence",
                "method": "POST",
                "endpoint": "/v1/orders",
                "priority": "Medium",
                "steps": [{
                    "content": "Call POST /v1/orders repeatedly",
                    "expectedResult": "Requests beyond 500 per minute are throttled",
                }],
                "expected_result": {"status_code": 429},
            })
            return result
        if "Generate UI validations" in user:
            return {"ui_validations": ui_cases_with_citations(user, [
                {
                    "title": "Quantity field is required to submit an order",
                    "field": "Quantity",
                    "intent": "The Quantity field must be a positive integer.",
                    "cite": "Quantity field",
                    "steps": [{
                        "content": "Submit the order form with no quantity",
                        "expectedResult": "Submission is blocked",
                    }],
                },
                {
                    "title": "Quantity field must not exceed 9999 units",
                    "field": "Quantity",
                    "cite": "Quantity field",
                    "intent": "fabricated -- no such limit anywhere in the evidence",
                    "steps": [{
                        "content": "Enter a quantity above 9999",
                        "expectedResult": "The value is rejected",
                    }],
                },
            ])}
        return super().chat_json(system, user, **kwargs)


class PipelineIntegrationTests(unittest.TestCase):
    def test_fabricated_numeric_claims_are_dropped_end_to_end_without_regressing_grounded_ones(self):
        store = FakeStore()
        result = generate_fresh_testcases_pipeline(
            store,
            GroundingGuardFakeLLM(),
            FakeEmbedder(),
            {
                "feature_id": "feature-1",
                "total": 10,
                # api-heavy weighting so _budget_suites' own count-based trimming
                # cannot coincidentally explain away the fabricated case (it already
                # has a >=min(len,3) floor per category; api's natural pool here is
                # 4 items, so its weight must be high enough that budgeting keeps
                # all 4 -- otherwise a passing assertion below could be masking a
                # missing wiring rather than proving the guard removed the
                # fabricated case specifically).
                "focus": {"functional": 0, "e2e": 0, "api": 100, "nfr": 0, "ui": 30},
            },
        )
        self.assertGreater(result["cases_new"] + result["cases_reused"], 0)
        titles = {case["title"] for case in store.created}

        # Existing, already-grounded behavior for api_tests/ui_validations: unchanged.
        self.assertTrue(
            any("accepts a valid order" in title for title in titles),
            "a well-grounded API case must still be generated and persisted",
        )
        self.assertIn(
            "Quantity field is required to submit an order", titles,
            "a well-grounded UI case (no fabricated specifics) must still be persisted",
        )

        # Fabricated, ungrounded numeric claims: must not reach persistence, in
        # EITHER category -- this is the actual regression this guard exists to
        # prevent, verified end to end through the real pipeline, not just the
        # unit-level guard function.
        self.assertNotIn(
            "Order creation rate limit must not exceed 500 requests per minute", titles,
        )
        self.assertNotIn("Quantity field must not exceed 9999 units", titles)
