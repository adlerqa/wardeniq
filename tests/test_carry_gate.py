"""A test carried over from another feature must be about this feature (#249 follow-up).

Found by running a real feature (e-commerce Product Search: Elasticsearch, brand filters,
sort, suggestions) in a project whose Login feature already had 16 Google-login tests. Nine
of them were attached to Product Search, next to its own seven tests. `INHERIT_EXACT`
attached whatever the model named, with no check at all.

Replaying the real Fusion step with those 16 tests, four models carried over 14
(qwen2.5:3b), 0 (qwen2.5:7b), 3 (gemma3:4b) and 8 (llama3.2:3b); the right answer is none.
The model's `already_covered_summary` was worse than useless: two models copied the prompt's
placeholder ("Endpoints A and B are fully covered") and two claimed this feature's own
`/api/v2/search` was already covered. That text goes to the agents that write the feature's
tests as "do not write tests for X".

What is pinned here:
  * the gate keeps every one of the 16 Login tests out of Product Search, and keeps most of
    them in a Login feature that really is a variation (documents about the same OAuth flow)
  * an endpoint rule (same endpoint; another API version is another endpoint) and a word rule
    (most of the test's words, and two, are in the documents)
  * through the real pipeline: an unrelated test is not carried, the rejection is reported, a
    related one still is, the feature's own previous version is not gated, and the "already
    covered" text only reaches the other agents when something was really carried
"""
import os
import sys

import pytest

APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../app"))
sys.path.insert(0, APP_DIR)

import carry_gate  # noqa: E402

# The project's Login tests (14 of the 16 in the real run; steps trimmed), as the Fusion step offers them.
LOGIN_TESTS = [
    ("api", "Race condition when linking Google account to existing user account",
     ["Given a user with an existing account and a Google account to link -> The user is authenticated",
      "When POST /oauth/link is called concurrently -> Duplicate account linking should not create multiple entries"]),
    ("api", "User is redirected to Google login",
     ["When GET /oauth/google is called -> The user is redirected to the Google consent screen"]),
    ("api", "User profile is synced and account is created after OAuth callback",
     ["When GET /oauth/callback is called with a code -> The profile is fetched and the account is created"]),
    ("api", "User successfully links Google account to existing account",
     ["When POST /oauth/link is called -> The Google account is linked"]),
    ("ui", "Users must initiate the login process through the Google login button.",
     ["Click the Google login button -> The Google consent page opens"]),
    ("ui", "Users must approve the Google OAuth consent to proceed with login.",
     ["Decline the consent -> The user is returned to the login page"]),
    ("ui", "New users must have their accounts automatically created upon successful authentication.",
     ["Log in with a new Google account -> An account is created"]),
    ("ui", "User profiles must be synced after successful authentication.",
     ["Log in with Google -> The profile name and email are saved"]),
    ("functional", "Redirect to Google OAuth consent",
     ["Click Login with Google -> The browser is redirected to the Google OAuth consent screen"]),
    ("functional", "Fetch profile, create/link account, create session",
     ["After the code exchange, fetch the profile, create or link the account and create a session -> The user is logged in"]),
    ("e2e", "User logs in with Google and account is auto-created",
     ["Click Login with Google and approve the consent -> A new account and session are created"]),
    ("e2e", "User logs in with Google and existing account is linked",
     ["Log in with Google using an email that has an account -> The Google account is linked to it"]),
    ("nfr", "User cancels Google OAuth consent",
     ["Cancel on the Google consent page -> The user returns to the login page without an account"]),
    ("nfr", "User attempts to log in with an invalid Google account",
     ["Log in with a Google account that is suspended -> Login is rejected with an error"]),
]


def login_case(i):
    kind, title, steps = LOGIN_TESTS[i]
    return {"id": f"login-{i}", "title": title, "type": kind, "steps": steps}


SEARCH_DOC = """E-Commerce Product Search
Version 2.0: Advanced Search
Advanced search with Elasticsearch for fuzzy matching, spell-check with synonym dictionary,
multi-brand filtering, and Redis caching for performance.
Fuzzy matching for spell corrections, Auto-suggestions, Multi-brand checkbox filters, Sort by
price/relevance, Search history tracking.
GET /api/v2/search?q=phone&brands[]=Apple&brands[]=Samsung&sort=price&page=1 and GET
/api/v2/suggest?q=pho returns 5 suggestions.
Elasticsearch Products index with id, name, price, category, brand fields.
PostgreSQL SearchHistory table with user_id, query, timestamp.
"""

LOGIN_V4_DOC = """E-commerce Login V4
Architecture: Frontend, API, OAuth Service, Google OAuth API and Apple Sign in.
OAuth Handler manages the Google OAuth flow and the Apple sign in flow.
Profile Sync fetches and saves the Google profile after a successful login.
Account Linker links Google to an existing account.
OAuth Flow: the user clicks Login with Google, is redirected to the Google OAuth consent screen,
approves, and Google sends a code. The code is exchanged for an access token; the profile is
fetched, the account is created or linked and a session is created.
If the user cancels the OAuth consent they return to the login page.
"""


# ------------------------------------------------------------------ the gate alone
class TestTheRealRun:
    @pytest.mark.parametrize("i", range(len(LOGIN_TESTS)))
    def test_no_login_test_is_carried_into_product_search(self, i):
        assert carry_gate.relevance_problem(login_case(i), SEARCH_DOC) is not None

    def test_the_reasons_name_what_is_wrong(self):
        assert "endpoint this feature's documents do not have (POST /oauth/link)" in \
            carry_gate.relevance_problem(login_case(0), SEARCH_DOC)
        assert "words occur in this feature's documents" in carry_gate.relevance_problem(login_case(8), SEARCH_DOC)

    def test_most_of_them_are_kept_for_a_login_feature_that_really_is_a_variation(self):
        kept = [i for i in range(len(LOGIN_TESTS)) if carry_gate.relevance_problem(login_case(i), LOGIN_V4_DOC) is None]
        assert len(kept) >= 11, kept


class TestEndpointRule:
    DOC = "GET /api/v2/search returns products. GET /api/v2/suggest returns suggestions."

    def case(self, title):
        return {"id": "x", "title": title, "type": "api", "steps": []}

    def test_the_same_endpoint_is_relevant(self):
        assert carry_gate.relevance_problem(self.case("GET /api/v2/search accepts a valid request"), self.DOC) is None

    def test_the_same_endpoint_under_another_api_version_is_not(self):
        problem = carry_gate.relevance_problem(self.case("GET /api/v1/search accepts a valid request"), self.DOC)
        assert problem and "GET /api/v1/search" in problem

    def test_an_endpoint_the_documents_never_name_is_not(self):
        assert carry_gate.relevance_problem(self.case("POST /api/v2/orders creates an order"), self.DOC)

    def test_a_path_parameter_does_not_make_it_a_different_endpoint(self):
        doc = "GET /v2/items/:id returns an item"
        assert carry_gate.relevance_problem(self.case("GET /v2/items/42 returns the item"), doc) is None

    def test_when_the_documents_name_no_endpoint_the_words_decide(self):
        doc = "The shipment handover is recorded against the carrier."
        related = {"id": "r", "title": "POST /v1/shipments records the handover of a shipment by a carrier", "steps": []}
        unrelated = {"id": "u", "title": "POST /oauth/link links a Google account", "steps": []}
        assert carry_gate.relevance_problem(related, doc) is None
        assert carry_gate.relevance_problem(unrelated, doc)


class TestWordRule:
    DOC = "The parcel tracking service records every shipment handover by a carrier partner."

    def case(self, title):
        return {"id": "x", "title": title, "type": "functional", "steps": []}

    def test_a_test_about_the_documents_is_kept(self):
        assert carry_gate.relevance_problem(self.case("A shipment handover by a carrier is recorded"), self.DOC) is None

    def test_one_shared_word_is_not_enough(self):
        assert carry_gate.relevance_problem(self.case("Refund a shipment after an invoice dispute with the bank"), self.DOC)

    def test_most_of_the_words_must_be_there(self):
        assert carry_gate.relevance_problem(
            self.case("Shipment carrier invoice refund dispute ledger audit currency"), self.DOC)

    def test_a_test_with_nothing_to_compare_is_not_blocked(self):
        assert carry_gate.relevance_problem({"id": "x", "title": "OK", "steps": []}, self.DOC) is None

    def test_steps_count_as_the_tests_words(self):
        c = {"id": "x", "title": "Handover", "steps": ["Hand over a shipment to the carrier partner -> The handover is recorded"]}
        assert carry_gate.relevance_problem(c, self.DOC) is None

    def test_dict_shaped_steps_are_read_too(self):
        c = {"id": "x", "title": "Handover", "steps": [{"action": "Hand over a shipment to the carrier partner",
                                                         "expected": "The handover is recorded"}]}
        assert carry_gate.relevance_problem(c, self.DOC) is None

    def test_no_documents_blocks_everything_with_words(self):
        assert carry_gate.relevance_problem(self.case("A shipment handover by a carrier is recorded"), "")


# ------------------------------------------------------------------ the real pipeline
from tests.test_rag_evidence_sufficiency import (  # noqa: E402
    DELIVERY_CHUNKS,
    DELIVERY_BUSINESS_CONTEXT,
    DELIVERY_TEXT,
    ScenarioLLM,
    ScenarioStore,
    _run,
)

FUSION_SUMMARY = "SUMMARY-FOR-OTHER-AGENTS: shipment status endpoints are fully covered."


class FusionLLM(ScenarioLLM):
    """A model that picks the given tests to carry over and writes a summary."""

    def chat_json(self, system, user, **kwargs):
        result = super().chat_json(system, user, **kwargs)
        if isinstance(result, dict) and "inherited_tests" in result:
            result = {**result, "already_covered_summary": FUSION_SUMMARY}
        return result


class CarryStore(ScenarioStore):
    """A project that already has two tests: one about shipments, one about Google login."""

    CASES = {
        "ship-1": {"id": "ship-1", "title": "A shipment handover is recorded", "type": "functional",
                   "steps": [{"content": "Hand over a shipment", "expectedResult": "The handover is recorded"}]},
        "login-1": {"id": "login-1", "title": "User logs in with Google and account is auto-created",
                    "type": "e2e", "steps": [{"content": "Click Login with Google and approve the consent",
                                              "expectedResult": "A new account and session are created"}]},
    }

    def list_test_cases(self, **kwargs):
        return {"items": [{"id": key, "title": value["title"]} for key, value in self.CASES.items()]}

    def get_case(self, case_id):
        return self.CASES.get(case_id)

    def resolve_case_reference(self, reference_key=None, title=None, project_id=None):
        return self.CASES.get(reference_key)


def carry_store(**kw):
    return CarryStore(name="Parcel tracking", summary="Expose parcel shipment status to carrier partners",
                      text=DELIVERY_TEXT, chunks=DELIVERY_CHUNKS, business_context=DELIVERY_BUSINESS_CONTEXT,
                      raw_api_spec="GET /v1/shipments/{id}\nPOST /v1/shipments", **kw)


def picks(*keys, mode="INHERIT_EXACT"):
    return [{"reference_key": key, "title": CarryStore.CASES[key]["title"], "mode": mode,
             **({"repair_instructions": "adapt"} if mode == "INHERIT_ADAPTED" else {})} for key in keys]


class TestFusionPipeline:
    def carried(self, store):
        return [case_id for _, case_id, origin, _ in store.associations if origin == "carried"]

    def test_an_unrelated_test_the_model_picks_is_not_carried(self):
        store = carry_store()
        result = _run(store, FusionLLM(inherited_tests=picks("login-1")))
        assert self.carried(store) == []
        assert result["inherited_reused"] == 0

    def test_the_rejection_is_reported_with_its_reason(self):
        result = _run(carry_store(), FusionLLM(inherited_tests=picks("login-1")))
        (rejected,) = result["inherited_rejected"]
        assert rejected["title"] == "User logs in with Google and account is auto-created"
        assert "occur in this feature's documents" in rejected["reason"]

    def test_a_related_test_is_still_carried_and_an_unrelated_one_next_to_it_is_not(self):
        store = carry_store()
        result = _run(store, FusionLLM(inherited_tests=picks("ship-1", "login-1")))
        assert self.carried(store) == ["ship-1"]
        assert result["inherited_reused"] == 1 and len(result["inherited_rejected"]) == 1

    def test_an_unrelated_test_to_adapt_is_rejected_before_any_rewrite(self):
        store, llm = carry_store(), FusionLLM(inherited_tests=picks("login-1", mode="INHERIT_ADAPTED"),
                                              adapted_case={"title": "Adapted", "steps": []})
        result = _run(store, llm)
        assert result["inherited_rebuilt"] == 0 and len(result["inherited_rejected"]) == 1
        assert not llm.calls_matching("Repair a specific test case")

    def test_the_feature_own_previous_version_is_not_gated(self):
        class Versioned(CarryStore):
            def __init__(self, **kw):
                super().__init__(**kw)
                self.feature = {**self.feature, "version": 2, "group_id": "g1"}
                self.features.find_one = lambda query, *a, **k: {"_id": "prev"}

            def get_feature_cases(self, feature_id):
                return [{**CarryStore.CASES["login-1"], "steps": []}]

        store = Versioned(name="Parcel tracking", summary="Expose parcel shipment status to carrier partners",
                          text=DELIVERY_TEXT, chunks=DELIVERY_CHUNKS, business_context=DELIVERY_BUSINESS_CONTEXT,
                          raw_api_spec="GET /v1/shipments/{id}")
        result = _run(store, FusionLLM(inherited_tests=picks("login-1")))
        assert self.carried(store) == ["login-1"] and result["inherited_rejected"] == []

    def test_the_summary_reaches_the_other_agents_only_when_something_was_carried(self):
        for chosen, expected in (("ship-1", True), ("login-1", False)):
            llm = FusionLLM(inherited_tests=picks(chosen))
            _run(carry_store(), llm)
            reached = any(FUSION_SUMMARY in call for call in llm.calls)
            assert reached is expected, (chosen, reached)

    def test_a_summary_with_no_inherited_test_at_all_is_not_passed_on(self):
        llm = FusionLLM(inherited_tests=[])
        _run(carry_store(), llm)
        assert not any(FUSION_SUMMARY in call for call in llm.calls)
