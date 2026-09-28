"""Global RAG readiness coverage: per-category evidence sufficiency, across all five
suites, on features that have nothing to do with Authentication.

The live validation finding this closes was NOT "Authentication's UI tests are wrong".
It was structural: a category whose source documents contain no evidence for it still
had its generation worker invoked, and a model asked to produce UI validations with
nothing to ground against answers with standard-looking invented form rules. Filtering
after the fact only catches the mechanically checkable subset of those inventions (a
number with a unit); the fix has to also stop the pipeline from ASKING for content it
has no evidence for. That is what this file exercises.

Every fixture here is a different, ordinary product domain -- parcel delivery tracking,
warehouse returns intake, ledger export -- specifically so that nothing about the
behavior can be Authentication-shaped, or even API-shaped. The same verdict logic is
exercised for api, ui, e2e, edge and business.

Companion files (already present, still green):
  tests/test_generation_pipeline.py  -- category retrieval plumbing, call counts, the
                                        fallback paths' RAG context
  tests/test_grounding_guard.py      -- the content-level numeric-claim guard
  tests/test_feature_chunk_retrieval.py -- the store's own retrieval + dimension-
                                        mismatch degradation
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../app")))

from testgen.service import (  # noqa: E402
    _business_narrative_lines,
    _category_evidence_sufficiency,
    generate_fresh_testcases_pipeline,
)
from tests.test_generation_pipeline import FakeEmbedder, FakeLLM, FakeStore  # noqa: E402


# --------------------------------------------------------------------------------
# Harness: one configurable feature + one configurable model, so a scenario is just
# "these documents, these chunks, this business context, this model output".
# --------------------------------------------------------------------------------

class ScenarioStore(FakeStore):
    def __init__(self, *, name, summary, text, chunks, business_context,
                 raw_api_spec="", llm_provider="openai"):
        super().__init__(fchunk_rows=[], llm_provider=llm_provider)
        self.feature = {
            **self.feature,
            "name": name,
            "summary": summary,
            "text": text,
            "raw_api_spec": raw_api_spec,
        }
        self.fchunks.rows = [
            {
                "_id": f"chunk-{index}",
                "chunk_index": index,
                "feature_id": "feature-1",
                "source": "prd",
                "category": category,
                "text": chunk_text,
            }
            for index, (category, chunk_text) in enumerate(chunks)
        ]
        self._business_context = business_context

    def build_unified_context(self, feature_id, version_number):
        context = super().build_unified_context(feature_id, version_number)
        context["featureName"] = self.feature["name"]
        context["metadata"]["featureName"] = self.feature["name"]
        context["featureDescription"] = self.feature["summary"]
        context["summaries"] = {"prd": self.feature["text"]}
        context["businessContext"] = self._business_context
        return context


class ScenarioLLM(FakeLLM):
    """Records every prompt the pipeline actually sends and answers each generation
    stage from a supplied payload, so a test can both (a) inject content a well-behaved
    model would never produce and (b) assert which calls were made at all."""

    def __init__(self, *, entities=None, apis=None, ui_components=None,
                 api_tests=None, ui_validations=None, e2e_payload=None,
                 business_fallback=None, inherited_tests=None, adapted_case=None):
        self._inherited_tests = inherited_tests or []
        self._adapted_case = adapted_case or {}
        self.calls = []
        self._entities = entities or []
        self._apis = apis or []
        self._ui_components = ui_components or []
        self._api_tests = api_tests
        self._ui_validations = ui_validations or []
        self._e2e_payload = e2e_payload or {
            "e2e_tests": [], "edge_cases": [], "business_tests": [],
        }
        self._business_fallback = business_fallback or []

    def _raw_chat(self, system, user, num_ctx, temperature, max_tokens,
                  timeout_seconds=None):
        import json
        self.calls.append(user)
        return json.dumps(self.chat_json(system, user))

    def calls_matching(self, marker):
        return [call for call in self.calls if marker in call]

    def chat_json(self, system, user, **kwargs):
        if "Extract API entities and endpoints" in user:
            return {
                "grounded_entities": self._entities,
                "apis": self._apis,
                "ui_components": self._ui_components,
            }
        if "CRUD inference" in user or "Infer REST CRUD endpoints" in user:
            return {"apis": []}
        if "Analyze Cross-Feature Overlap" in user:
            return {"inherited_tests": list(self._inherited_tests),
                    "covered_endpoints": [], "covered_flows": [],
                    "already_covered_summary": ""}
        if "Repair a specific test case" in user:
            return dict(self._adapted_case)
        if "Generate focused API worker test cases" in user:
            if self._api_tests is not None:
                return {"api_tests": list(self._api_tests)}
            return super().chat_json(system, user, **kwargs)
        if "Generate UI validations" in user:
            return {"ui_validations": list(self._ui_validations)}
        if "Generate E2E flows, edge cases, and business rule tests" in user:
            return {key: list(value) for key, value in self._e2e_payload.items()}
        if "Generate focused E2E flow test cases" in user:
            return {"e2e_tests": []}
        if "Generate one business rule test" in user:
            return {"business_tests": list(self._business_fallback)}
        if "Generate a minimal delta patch" in user:
            # A well-formed "nothing to patch" response. An empty dict would be treated
            # as an unparseable model reply and send the repair pass into its retry path.
            return {f"{suite}_delta": {"tests_to_add": [], "tests_to_remove": []}
                    for suite in ("api_tests", "ui_validations", "e2e_tests",
                                  "edge_cases", "business_tests")}
        raise AssertionError(f"Unexpected prompt: {user[:120]}")


def _run(store, llm, embedder=None, **params):
    return generate_fresh_testcases_pipeline(
        store, llm, embedder or FakeEmbedder(),
        {"feature_id": "feature-1", "total": 40,
         "focus": {"functional": 20, "e2e": 20, "api": 20, "nfr": 20, "ui": 20},
         **params},
    )


def _titles(store):
    return {case["title"] for case in store.created}


# --------------------------------------------------------------------------------
# Scenario A -- parcel delivery tracking. Real, substantial backend documents; zero
# UI content anywhere in them. This is the generic shape of the live finding.
# --------------------------------------------------------------------------------

DELIVERY_TEXT = (
    "The parcel tracking service exposes shipment status to carrier partners.\n"
    "GET /v1/shipments/{id} returns the current status of a shipment.\n"
    "POST /v1/shipments records a new shipment handed over by a carrier.\n"
    "The recipient phone number is stored on the shipment record for carrier handoff "
    "and is never exposed to partner integrations.\n"
    "A shipment status transition must be rejected when the shipment is already "
    "marked delivered.\n"
    "Carrier partners must authenticate with a partner token before any call.\n"
)

DELIVERY_CHUNKS = [
    ("api", "GET /v1/shipments/{id} returns the current status of a shipment."),
    ("api", "POST /v1/shipments records a new shipment handed over by a carrier."),
    ("e2e", "A shipment status transition must be rejected when the shipment is "
            "already marked delivered."),
    ("business", "Carrier partners must authenticate with a partner token before any "
                 "call."),
]

DELIVERY_BUSINESS_CONTEXT = {
    "prd": {"requirements": [
        "A shipment status transition must be rejected when the shipment is already "
        "marked delivered.",
        "Carrier partners must authenticate with a partner token before any call.",
    ]},
}


def _delivery_store():
    return ScenarioStore(
        name="Parcel tracking",
        summary="Expose parcel shipment status to carrier partners",
        text=DELIVERY_TEXT,
        chunks=DELIVERY_CHUNKS,
        business_context=DELIVERY_BUSINESS_CONTEXT,
        raw_api_spec="GET /v1/shipments/{id}\nPOST /v1/shipments",
    )


# The UI content a model invents when asked for UI validations on documents that have
# none. Note the field name IS a real word in the corpus ("recipient phone number" is a
# stored data attribute) -- which is exactly why a subject-level field filter alone does
# not stop this, and why the fix has to act before the call rather than after it.
FABRICATED_UI = [
    {
        "title": "Submit button must remain disabled until the recipient phone number "
                 "is valid",
        "field": "recipient phone number",
        "steps": [{"content": "Open the form", "expectedResult": "Submit is disabled"}],
    },
    {
        "title": "Recipient phone number must not exceed 15 characters",
        "field": "recipient phone number",
        "steps": [{"content": "Enter 16 characters", "expectedResult": "Rejected"}],
    },
]


class UiWithoutEvidenceTests(unittest.TestCase):
    """Requirement: a feature with no UI evidence must not have UI specifics invented
    for it -- and must not be asked to invent them."""

    def test_no_ui_generation_call_is_made_when_no_ui_evidence_exists(self):
        store, llm = _delivery_store(), ScenarioLLM(ui_validations=FABRICATED_UI)
        _run(store, llm)
        self.assertEqual(
            [], llm.calls_matching("Generate UI validations"),
            "with no UI evidence anywhere in the documents the UI worker must not be "
            "invoked at all -- there is nothing for it to ground against",
        )

    def test_invented_ui_details_never_reach_persistence(self):
        store, llm = _delivery_store(), ScenarioLLM(ui_validations=FABRICATED_UI)
        _run(store, llm)
        titles = _titles(store)
        for fabricated in FABRICATED_UI:
            self.assertNotIn(fabricated["title"], titles)

    def test_ui_insufficiency_is_reported_explicitly_not_silently_empty(self):
        store, llm = _delivery_store(), ScenarioLLM(ui_validations=FABRICATED_UI)
        result = _run(store, llm)
        self.assertIn("ui", result.get("evidence_insufficient", []))
        self.assertTrue(
            any("ui:" in warning for warning in result.get("warnings", [])),
            "an empty suite is indistinguishable from 'the model returned nothing' -- "
            "the reason must be stated on the job result",
        )

    def test_the_other_four_categories_are_unaffected(self):
        """Skipping UI must not be collateral damage on the rest of the run."""
        store = _delivery_store()
        llm = ScenarioLLM(
            ui_validations=FABRICATED_UI,
            e2e_payload={
                "e2e_tests": [{
                    "title": "A shipment already marked delivered rejects a further "
                             "status transition",
                    "steps": [{"content": "Transition a delivered shipment",
                               "expectedResult": "The transition is rejected"}],
                }],
                "edge_cases": [{
                    "title": "Recording a shipment twice must not create a duplicate",
                    "steps": [{"content": "POST the same shipment twice",
                               "expectedResult": "Only one record exists"}],
                }],
                "business_tests": [{
                    "title": "Carrier partners must authenticate with a partner token "
                             "before any call",
                    "steps": [{"content": "Call without a partner token",
                               "expectedResult": "The call is refused"}],
                }],
            },
        )
        result = _run(store, llm)
        titles = _titles(store)
        self.assertTrue(any("further status transition" in title for title in titles))
        self.assertTrue(any("duplicate" in title for title in titles))
        self.assertTrue(any("partner token" in title for title in titles))
        self.assertGreater(result["cases_new"], 0)

    def test_category_retrieval_architecture_is_unchanged_by_the_skip(self):
        """All four category retrievals still happen exactly once each. The verdict
        gates GENERATION, not retrieval -- no pipeline was removed or duplicated."""
        store, llm = _delivery_store(), ScenarioLLM(ui_validations=FABRICATED_UI)
        _run(store, llm)
        categories = sorted(call["category"] for call in store.search_feature_chunks_calls)
        self.assertEqual(["api", "business", "e2e", "ui"], categories)


# --------------------------------------------------------------------------------
# Scenario B -- warehouse returns intake. Genuine UI evidence, including one specific
# numeric UI rule stated in the source. The UI category must work normally here.
# --------------------------------------------------------------------------------

RETURNS_TEXT = (
    "The returns intake screen lets a warehouse operator log a returned item.\n"
    "The intake form shows a Delivery notes field that accepts at most 240 characters.\n"
    "The operator must select a return reason before the intake can be saved.\n"
    "POST /v1/returns records an accepted return.\n"
)

RETURNS_CHUNKS = [
    ("ui", "The intake form shows a Delivery notes field that accepts at most 240 "
           "characters."),
    ("ui", "The operator must select a return reason before the intake can be saved."),
    ("api", "POST /v1/returns records an accepted return."),
    ("business", "The operator must select a return reason before the intake can be "
                 "saved."),
]


def _returns_store():
    return ScenarioStore(
        name="Returns intake",
        summary="Log a returned item at the warehouse",
        text=RETURNS_TEXT,
        chunks=RETURNS_CHUNKS,
        business_context={"prd": {"requirements": [
            "The operator must select a return reason before the intake can be saved.",
        ]}},
        raw_api_spec="POST /v1/returns",
    )


GROUNDED_UI_TITLE = "Delivery notes field must not exceed 240 characters"
FABRICATED_UI_TITLE = "Delivery notes field must not exceed 12 characters"


class UiWithEvidenceTests(unittest.TestCase):
    """Requirement: do NOT solve this by suppressing UI tests. A feature with real UI
    evidence must still generate UI tests, and must use the source's own specifics."""

    def _llm(self):
        return ScenarioLLM(
            ui_components=[{
                "screen": "Returns intake",
                "element": "Delivery notes",
                "type": "input",
                "evidence_quote": "The intake form shows a Delivery notes field",
            }],
            ui_validations=[
                {"title": GROUNDED_UI_TITLE, "field": "Delivery notes",
                 "steps": [{"content": "Enter 241 characters",
                            "expectedResult": "The value is rejected"}]},
                {"title": FABRICATED_UI_TITLE, "field": "Delivery notes",
                 "steps": [{"content": "Enter 13 characters",
                            "expectedResult": "The value is rejected"}]},
            ],
        )

    def test_ui_generation_still_runs_when_ui_evidence_exists(self):
        store, llm = _returns_store(), self._llm()
        _run(store, llm)
        self.assertTrue(
            llm.calls_matching("Generate UI validations"),
            "UI generation must be evidence-conditioned, not switched off",
        )

    def test_ui_requirement_stated_in_the_source_is_used(self):
        store, llm = _returns_store(), self._llm()
        _run(store, llm)
        self.assertIn(GROUNDED_UI_TITLE, _titles(store))

    def test_a_ui_limit_the_source_never_states_is_still_dropped(self):
        store, llm = _returns_store(), self._llm()
        _run(store, llm)
        self.assertNotIn(FABRICATED_UI_TITLE, _titles(store))

    def test_ui_is_not_reported_as_insufficient_when_evidence_exists(self):
        store, llm = _returns_store(), self._llm()
        result = _run(store, llm)
        self.assertNotIn("ui", result.get("evidence_insufficient", []))

    def test_ui_evidence_living_only_in_a_retrieved_chunk_still_counts(self):
        """The derivation fallback reads the feature's own `text` field, but a feature
        can be backed by several separately-ingested documents. UI evidence present in
        the corpus but not in that one field must still count as UI evidence, or a
        multi-document feature would have its UI suite wrongly skipped."""
        store = ScenarioStore(
            name="Returns intake",
            summary="Log a returned item at the warehouse",
            text="POST /v1/returns records an accepted return.",  # no UI in `text`
            chunks=RETURNS_CHUNKS,                                 # UI lives here
            business_context={"prd": {"requirements": ["A return reason is required."]}},
            raw_api_spec="POST /v1/returns",
        )
        llm = ScenarioLLM(ui_validations=[])
        result = _run(store, llm)
        self.assertNotIn("ui", result.get("evidence_insufficient", []))
        self.assertTrue(llm.calls_matching("Generate UI validations"))


# --------------------------------------------------------------------------------
# Scenario C -- business, e2e, edge and api sufficiency on their own terms.
# --------------------------------------------------------------------------------

LEDGER_TEXT = (
    "The ledger export job writes a daily settlement file to the finance bucket.\n"
    "GET /v1/exports/{date} returns the export status for a settlement date.\n"
)


def _ledger_store(business_context):
    return ScenarioStore(
        name="Ledger export",
        summary="Write a daily settlement export",
        text=LEDGER_TEXT,
        chunks=[("api", "GET /v1/exports/{date} returns the export status for a "
                        "settlement date.")],
        business_context=business_context,
        raw_api_spec="GET /v1/exports/{date}",
    )


class BusinessEvidenceTests(unittest.TestCase):
    def test_business_fallback_does_not_run_without_business_evidence(self):
        """The fallback's floor exists to top up thin coverage of real business rules.
        With no extracted business narrative at all it was still firing -- an extra LLM
        call whose only possible output is invented business rules."""
        store = _ledger_store({"prd": {"requirements": []}})
        llm = ScenarioLLM(business_fallback=[{
            "title": "Refunds must be approved within 3 hours",
            "steps": [{"content": "Raise a refund", "expectedResult": "Approved"}],
        }])
        result = _run(store, llm)
        self.assertEqual([], llm.calls_matching("Generate one business rule test"))
        self.assertIn("business", result.get("evidence_insufficient", []))
        self.assertNotIn("Refunds must be approved within 3 hours", _titles(store))

    def test_business_fallback_still_runs_when_business_evidence_exists(self):
        """The converse, so the fix is a condition rather than a removal."""
        store = _ledger_store({"prd": {"requirements": [
            "A settlement export must be written once per calendar day.",
        ]}})
        llm = ScenarioLLM(business_fallback=[])
        _run(store, llm)
        self.assertTrue(llm.calls_matching("Generate one business rule test"))

    def test_narrative_lines_are_read_from_both_business_context_shapes(self):
        nested = {"prd": {"requirements": ["r1"], "acceptanceCriteria": ["a1"]}}
        flat = {"requirements": ["r1"], "userStories": ["s1"]}
        self.assertEqual(["r1", "a1"], _business_narrative_lines(nested))
        self.assertEqual(["r1", "s1"], _business_narrative_lines(flat))
        self.assertEqual([], _business_narrative_lines({}))
        self.assertEqual([], _business_narrative_lines(None))


class ApiEdgeAndE2eEvidenceTests(unittest.TestCase):
    def _no_endpoint_store(self):
        return ScenarioStore(
            name="Weekly digest",
            summary="Send a weekly activity digest",
            text=("The weekly digest summarises a workspace's activity.\n"
                  "A digest must not be sent to a workspace with no activity.\n"),
            chunks=[("business", "A digest must not be sent to a workspace with no "
                                 "activity.")],
            business_context={"prd": {"requirements": [
                "A digest must not be sent to a workspace with no activity.",
            ]}},
        )

    def _grounded_digest_llm(self, **kwargs):
        """The feature's one real requirement, generated as a business test, so a run
        with no API evidence still produces something and the assertions below are about
        the API category rather than about an empty run."""
        return ScenarioLLM(e2e_payload={
            "e2e_tests": [],
            "edge_cases": kwargs.get("edge_cases", []),
            "business_tests": [{
                "title": "A digest must not be sent to a workspace with no activity",
                "steps": [{"content": "Run the digest for an idle workspace",
                           "expectedResult": "No digest is sent"}],
            }],
        })

    def test_no_api_worker_runs_and_api_is_reported_when_no_endpoint_evidence(self):
        store, llm = self._no_endpoint_store(), self._grounded_digest_llm()
        result = _run(store, llm)
        self.assertEqual([], llm.calls_matching("Generate focused API worker test cases"))
        self.assertIn("api", result.get("evidence_insufficient", []))

    def test_edge_insufficiency_drops_the_suppressed_block(self):
        """edge_cases ride the E2E call, so that call still runs. The returned
        edge block must not persist as nfr when edge evidence was insufficient."""
        store = self._no_endpoint_store()
        llm = self._grounded_digest_llm(edge_cases=[{
            "title": "An idle workspace must still record that the digest job ran",
            "steps": [{"content": "Run the digest for an idle workspace",
                       "expectedResult": "The run is recorded"}],
        }])
        result = _run(store, llm)
        self.assertIn("edge", result.get("evidence_insufficient", []))
        self.assertNotIn(
            "An idle workspace must still record that the digest job ran",
            _titles(store),
        )
        self.assertTrue(
            any(warning.startswith("edge:") for warning in result.get("warnings", [])),
        )
        self.assertTrue(
            any("no supporting evidence" in warning for warning in result.get("warnings", [])),
        )

    def test_fabricated_numeric_claims_are_dropped_in_e2e_edge_and_business_alike(self):
        """Same content-level standard applied to the three suites that share one call,
        on a feature with no Authentication content anywhere near it."""
        store = _delivery_store()
        llm = ScenarioLLM(e2e_payload={
            "e2e_tests": [
                {"title": "A shipment already marked delivered rejects a further "
                          "status transition",
                 "steps": [{"content": "Transition it", "expectedResult": "Rejected"}]},
                {"title": "A shipment must be delivered within 48 hours of handover",
                 "steps": [{"content": "Wait", "expectedResult": "Delivered"}]},
            ],
            "edge_cases": [
                {"title": "Recording the same shipment twice must not duplicate it",
                 "steps": [{"content": "POST twice", "expectedResult": "One record"}]},
                {"title": "At most 7 status transitions may be recorded per shipment",
                 "steps": [{"content": "Transition 8 times", "expectedResult": "Blocked"}]},
            ],
            "business_tests": [
                {"title": "Carrier partners must authenticate with a partner token "
                          "before any call",
                 "steps": [{"content": "Call without a token",
                            "expectedResult": "Refused"}]},
                {"title": "A carrier partner must be billed within 30 days of handover",
                 "steps": [{"content": "Wait", "expectedResult": "Billed"}]},
            ],
        })
        _run(store, llm)
        titles = _titles(store)
        # Grounded ones survive...
        self.assertTrue(any("further status transition" in title for title in titles))
        self.assertTrue(any("duplicate it" in title for title in titles))
        self.assertTrue(any("partner token" in title for title in titles))
        # ...and every fabricated specific is gone, in all three suites.
        self.assertNotIn(
            "A shipment must be delivered within 48 hours of handover", titles)
        self.assertNotIn(
            "At most 7 status transitions may be recorded per shipment", titles)
        self.assertNotIn(
            "A carrier partner must be billed within 30 days of handover", titles)


# A feature with substantial prose but no endpoints, no UI and no extracted business
# narrative -- long enough to clear the pipeline's pre-existing global "evidence is too
# short to generate from at all" guard, so what is under test here is the PER-CATEGORY
# verdict rather than that whole-feature one.
CLEANUP_TEXT = (
    "The nightly cleanup job removes expired temporary records from the working "
    "store.\n"
    "It runs after the daily settlement window closes and walks each tenant partition "
    "in turn, releasing records whose retention window has elapsed.\n"
    "Records still referenced by an open export are left in place and revisited on the "
    "following run.\n"
    "The job writes a summary of what it released to the operations log.\n"
)


class CallBudgetTests(unittest.TestCase):
    """Exactly the expected calls, and no others. The evidence verdict must remove the
    calls a category has no evidence for and leave every other call in place -- it is a
    trigger condition, not a new pipeline."""

    _GENERATION_MARKERS = (
        "Generate focused API worker test cases",
        "Generate UI validations",
        "Generate E2E flows, edge cases, and business rule tests",
        "Generate focused E2E flow test cases",
        "Generate one business rule test",
    )

    def _profile(self, store, llm):
        _run(store, llm)
        return {
            marker: len(llm.calls_matching(marker))
            for marker in self._GENERATION_MARKERS
        }, sorted(call["category"] for call in store.search_feature_chunks_calls)

    def test_a_fully_evidenced_feature_makes_every_generation_call(self):
        llm = ScenarioLLM(
            ui_components=[{"screen": "Returns intake", "element": "Delivery notes",
                            "evidence_quote": "The intake form shows a Delivery notes "
                                              "field"}],
            e2e_payload={"e2e_tests": [], "edge_cases": [], "business_tests": []},
        )
        calls, categories = self._profile(_returns_store(), llm)
        # Two UI workers is the established shape: one broad pass plus one per group of
        # extracted components. This asserts the count is unchanged, not that it is 1.
        self.assertEqual(2, calls["Generate UI validations"])
        self.assertEqual(1, calls["Generate E2E flows, edge cases, and business rule "
                                  "tests"])
        self.assertEqual(1, calls["Generate one business rule test"])
        self.assertGreaterEqual(calls["Generate focused API worker test cases"], 1)
        self.assertEqual(["api", "business", "e2e", "ui"], categories)

    def test_missing_evidence_removes_only_that_category_s_call(self):
        """The delivery feature has API, E2E and business evidence but no UI evidence:
        the UI call disappears and nothing else changes -- including all four category
        retrievals, which are unaffected by the generation verdict."""
        llm = ScenarioLLM(ui_validations=FABRICATED_UI)
        calls, categories = self._profile(_delivery_store(), llm)
        self.assertEqual(0, calls["Generate UI validations"])
        self.assertEqual(1, calls["Generate E2E flows, edge cases, and business rule "
                                  "tests"])
        self.assertEqual(1, calls["Generate one business rule test"])
        self.assertGreaterEqual(calls["Generate focused API worker test cases"], 1)
        self.assertEqual(["api", "business", "e2e", "ui"], categories)

    def test_no_evidence_at_all_leaves_only_the_shared_e2e_call(self):
        """A feature with neither endpoints nor UI nor business narrative: the API, UI
        and business-fallback calls all disappear. The shared E2E call remains, because
        E2E is backed by the feature's own description and edge_cases ride it."""
        store = ScenarioStore(
            name="Nightly cleanup",
            summary="Remove expired temporary records overnight",
            text=CLEANUP_TEXT,
            chunks=[("e2e", CLEANUP_TEXT)],
            business_context={"prd": {"requirements": []}},
        )
        llm = ScenarioLLM(e2e_payload={
            "e2e_tests": [{
                "title": "The nightly cleanup job removes expired temporary records",
                "steps": [{"content": "Run the job",
                           "expectedResult": "Expired records are gone"}],
            }],
            "edge_cases": [], "business_tests": [],
        })
        calls, categories = self._profile(store, llm)
        self.assertEqual(0, calls["Generate focused API worker test cases"])
        self.assertEqual(0, calls["Generate UI validations"])
        self.assertEqual(0, calls["Generate one business rule test"])
        self.assertEqual(1, calls["Generate E2E flows, edge cases, and business rule "
                                  "tests"])
        # Only three retrievals here, and that is pre-existing behavior unrelated to the
        # evidence verdict: with no endpoints and no entities the API query text comes
        # out empty, and the pipeline has always declined to run a vector search on an
        # empty query rather than retrieving noise.
        self.assertEqual(["business", "e2e", "ui"], categories)


class FusionInheritancePathTests(unittest.TestCase):
    """The Fusion pass can carry a previous version's test forward in ADAPTED form --
    an LLM rewrite that is persisted directly, bypassing the suite filters every freshly
    generated case goes through. It was the last route by which a model-written specific
    could reach the store unchecked."""

    class _InheritStore(ScenarioStore):
        def resolve_case_reference(self, reference_key=None, title=None, project_id=None):
            return {
                "id": "old-case-1",
                "title": "A shipment handover is recorded",
                "type": "functional",
                "steps": [{"content": "Hand over a shipment",
                           "expectedResult": "The handover is recorded"}],
            }

    def _store(self):
        return self._InheritStore(
            name="Parcel tracking",
            summary="Expose parcel shipment status to carrier partners",
            text=DELIVERY_TEXT,
            chunks=DELIVERY_CHUNKS,
            business_context=DELIVERY_BUSINESS_CONTEXT,
            raw_api_spec="GET /v1/shipments/{id}\nPOST /v1/shipments",
        )

    def _llm(self, adapted_case):
        return ScenarioLLM(
            inherited_tests=[{
                "reference_key": "old-case-1",
                "title": "A shipment handover is recorded",
                "mode": "INHERIT_ADAPTED",
                "repair_instructions": "Update for the new handover flow",
            }],
            adapted_case=adapted_case,
        )

    def test_an_adapted_case_that_invents_a_specific_is_not_carried_over(self):
        store = self._store()
        llm = self._llm({
            "title": "A shipment handover must be recorded within 45 seconds",
            "steps": [{"content": "Hand over a shipment",
                       "expectedResult": "The handover must be recorded within 45 "
                                         "seconds"}],
        })
        result = _run(store, llm)
        self.assertNotIn(
            "A shipment handover must be recorded within 45 seconds", _titles(store))
        self.assertEqual(0, result["inherited_rebuilt"])
        self.assertTrue(
            any("not carried over" in error for error in result["errors"]),
            "dropping an inherited test must be reported, not silent",
        )

    def test_a_well_grounded_adapted_case_is_still_carried_over(self):
        store = self._store()
        llm = self._llm({
            "title": "A shipment handover is recorded against the shipment record",
            "steps": [{"content": "Hand over a shipment",
                       "expectedResult": "The handover is recorded"}],
        })
        result = _run(store, llm)
        self.assertEqual(1, result["inherited_rebuilt"])
        self.assertIn(
            "A shipment handover is recorded against the shipment record",
            _titles(store),
        )


class EvidenceSufficiencyUnitTests(unittest.TestCase):
    """The verdict itself, isolated -- deterministic, and keyed only on extraction
    counts, never on category names, feature names or domain vocabulary."""

    def test_every_category_is_reported(self):
        verdict = _category_evidence_sufficiency([], [], {}, "", "")
        self.assertEqual(
            {"api", "ui", "e2e", "edge", "business"}, set(verdict),
        )

    def test_all_false_on_an_empty_feature(self):
        verdict = _category_evidence_sufficiency([], [], {}, "", "")
        self.assertEqual([], [name for name, ok in verdict.items() if ok])

    def test_each_signal_moves_only_its_own_categories(self):
        with_api = _category_evidence_sufficiency(
            [{"method": "GET", "endpoint": "/v1/x"}], [], {}, "", "")
        self.assertTrue(with_api["api"])
        self.assertTrue(with_api["edge"], "edge is backed by API/state-mutation evidence")
        self.assertFalse(with_api["ui"])
        self.assertFalse(with_api["business"])

        with_ui = _category_evidence_sufficiency([], [{"element": "Quantity"}], {}, "", "")
        self.assertTrue(with_ui["ui"])
        self.assertFalse(with_ui["api"])

        with_business = _category_evidence_sufficiency(
            [], [], {"requirements": ["An order must have a delivery address."]}, "", "")
        self.assertTrue(with_business["business"])
        self.assertTrue(with_business["e2e"])
        self.assertFalse(with_business["ui"])

    def test_verdict_is_identical_across_unrelated_domains(self):
        """Same shape of evidence, three unrelated domains -> same verdict. Nothing in
        the rule can be reading domain vocabulary."""
        shapes = [
            ({"requirements": ["A ride must have a pickup point."]}, "Ride booking"),
            ({"requirements": ["A payment must have a settlement account."]}, "Payments"),
            ({"requirements": ["A room must have a check-in date."]}, "Hotel booking"),
        ]
        verdicts = [
            _category_evidence_sufficiency([], [], context, description, "")
            for context, description in shapes
        ]
        self.assertEqual(1, len({tuple(sorted(v.items())) for v in verdicts}))

    def test_verdict_never_calls_an_embedder_or_a_model(self):
        """It takes plain Python values and text only -- there is no embedding, no
        retrieval and no LLM in it, which is why it behaves identically under Nomic,
        OpenAI, Voyage, Bedrock or Gemini."""
        class ExplodingEmbedder:
            def embed(self, *_a, **_k):
                raise AssertionError("the verdict must not embed anything")

        _ = ExplodingEmbedder()  # never passed in; the signature has nowhere to put it
        verdict = _category_evidence_sufficiency(
            [{"method": "GET", "endpoint": "/v1/x"}], [{"element": "Q"}],
            {"requirements": ["r"]}, "desc", "text",
        )
        self.assertTrue(all(verdict.values()))


# --------------------------------------------------------------------------------
# Retrieval resilience: a category whose retrieval fails must degrade to no evidence,
# never take the run down. The store's own dimension-mismatch degradation is covered
# in tests/test_feature_chunk_retrieval.py; this is the service-layer half, which sits
# above it and also covers the embed() call itself.
# --------------------------------------------------------------------------------

class RetrievalFailureDegradesGracefullyTests(unittest.TestCase):
    def test_an_embedding_call_that_raises_does_not_crash_generation(self):
        """A provider timeout, a revoked key, or a model swapped through Settings
        mid-run raises out of embed() -- which sits above the store's own protection.
        One category failing must not lose the other four."""
        class FailingOnUiEmbedder(FakeEmbedder):
            def __init__(self):
                self.queries = []

            def embed(self, text, task="document"):
                if task == "query":
                    self.queries.append(text)
                    if "Returns intake" in text or "Delivery notes" in text:
                        raise RuntimeError("embedding provider unavailable")
                return super().embed(text, task=task)

        store, llm = _returns_store(), UiWithEvidenceTests()._llm()
        result = _run(store, llm, embedder=FailingOnUiEmbedder())
        self.assertGreaterEqual(result["cases_new"] + result["cases_reused"], 1)

    def test_a_store_retrieval_that_raises_does_not_crash_generation(self):
        """The dimension-mismatch shape, seen from the service layer: even if the store
        raised instead of degrading, the pipeline still completes."""
        class ExplodingSearchStore(ScenarioStore):
            def search_feature_chunks(self, *args, **kwargs):
                super().search_feature_chunks(*args, **kwargs)
                raise ValueError(
                    "embedding dimension mismatch: query has 1536, stored chunks have 768"
                )

        store = ExplodingSearchStore(
            name="Parcel tracking",
            summary="Expose parcel shipment status to carrier partners",
            text=DELIVERY_TEXT,
            chunks=DELIVERY_CHUNKS,
            business_context=DELIVERY_BUSINESS_CONTEXT,
            raw_api_spec="GET /v1/shipments/{id}\nPOST /v1/shipments",
        )
        result = _run(store, ScenarioLLM())
        self.assertEqual(4, len(store.search_feature_chunks_calls))
        self.assertGreaterEqual(result["cases_new"] + result["cases_reused"], 1)

    def test_a_failed_retrieval_is_visible_in_the_logs(self):
        """Degrading silently is indistinguishable from 'this category genuinely had no
        chunks' -- the failure must stay diagnosable after the fact."""

        class AlwaysFailingEmbedder(FakeEmbedder):
            def embed(self, text, task="document"):
                if task == "query":
                    raise RuntimeError("embedding provider unavailable")
                return super().embed(text, task=task)

        with self.assertLogs("wardeniq.testgen", level="WARNING") as cm:
            _run(_delivery_store(), ScenarioLLM(), embedder=AlwaysFailingEmbedder())
        output = "\n".join(cm.output)
        self.assertIn("retrieval_failed_degraded_to_empty", output)
        self.assertIn("embedding provider unavailable", output)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
