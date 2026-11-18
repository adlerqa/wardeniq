import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../app")))

from testgen.service import (  # noqa: E402
    _api_adjacent_requirement_lines,
    _budget_suites,
    _build_api_retrieval_query,
    _build_business_retrieval_query,
    _build_e2e_retrieval_query,
    _build_ui_retrieval_query,
    _category_top_k,
    _clean_endpoint,
    _deduplicate,
    _derive_ui_components,
    _ensure_api_endpoint_coverage,
    _evidence_corpus,
    _filter_api_tests,
    _clean_requirement_narrative,
    _merge_api_candidates,
    _parse_raw_api_spec,
    _semantic_reuse_compatible,
    generate_fresh_testcases_pipeline,
)
from testgen.prompt_builder import (  # noqa: E402
    build_api_agent_prompt,
    build_business_test_prompt,
    build_e2e_agent_prompt,
    build_ui_agent_prompt,
)
from testgen.lineage import normalize_endpoint  # noqa: E402


class FakeCollection:
    def __init__(self, rows=None):
        self.rows = rows or []

    def find(self, query):
        return list(self.rows)

    def find_one(self, query):
        return None


class FakeStore:
    def __init__(self, fchunk_rows=None, llm_provider="ollama"):
        text = (
            "The order service must allow an authenticated customer to create an order. "
            "POST /v1/orders accepts a valid order payload and returns the created order. "
            "Only authenticated customers may create orders. "
        ) * 3
        self.feature = {
            "id": "feature-1",
            "name": "Create order",
            "summary": "Create a customer order",
            "text": text,
            "raw_api_spec": "POST /v1/orders",
            "project_id": "project-1",
            "group_id": "feature-1",
            "version": 1,
            "version_diff": {},
        }
        self.features = FakeCollection()
        default_rows = [
            {
                "_id": "chunk-api-1",
                "chunk_index": 0,
                "feature_id": "feature-1",
                "source": "prd",
                "category": "api",
                "text": "POST /v1/orders accepts a valid order payload and returns the created order.",
            },
            {
                "_id": "chunk-ui-1",
                "chunk_index": 1,
                "feature_id": "feature-1",
                "source": "prd",
                "category": "ui",
                "text": "The order form shows a Quantity field that must be a positive integer.",
            },
            {
                "_id": "chunk-e2e-1",
                "chunk_index": 2,
                "feature_id": "feature-1",
                "source": "prd",
                "category": "e2e",
                "text": "Only authenticated customers may create orders; guests are redirected to sign in.",
            },
            {
                "_id": "chunk-business-1",
                "chunk_index": 3,
                "feature_id": "feature-1",
                "source": "prd",
                "category": "business",
                "text": "Only one promo code may be applied per order; a second code is rejected.",
            },
            # Belongs to a DIFFERENT feature -- used to assert no cross-feature leakage.
            {
                "_id": "chunk-other-1",
                "chunk_index": 0,
                "feature_id": "feature-2",
                "source": "prd",
                "category": "api",
                "text": "The refund service issues a partial refund when a return is approved.",
            },
        ]
        self.fchunks = FakeCollection(fchunk_rows if fchunk_rows is not None else default_rows)
        self.created = []
        self.associations = []
        self.identity = {}
        self.step_number = 0
        self._llm_provider = llm_provider
        self.search_feature_chunks_calls = []

    def get_settings(self):
        return {"llm_provider": self._llm_provider}

    def search_feature_chunks(self, query_embedding, feature_id, limit=8, category=None):
        """Test double for store.features.Store.search_feature_chunks(). Real semantic
        ranking quality can only be verified against a live Atlas cluster (mongomock has
        no $vectorSearch support -- see tests/test_feature_chunk_retrieval.py for the
        real store method's own fallback/shape tests); this fake instead verifies the
        SERVICE-layer plumbing -- that each category's retrieval call is scoped to the
        right feature_id, is made exactly once per category, and that whatever it
        returns actually reaches that category's prompt. It ranks each feature's own
        fixture rows by whether their `category` tag matches the caller's `category`,
        which is enough to prove category-specific chunks flow into the matching
        category's worker without depending on a real embedding model.
        """
        self.search_feature_chunks_calls.append(
            {"feature_id": feature_id, "limit": limit, "category": category}
        )
        rows = [row for row in self.fchunks.rows if row.get("feature_id") == feature_id]
        if not rows:
            return []
        if category:
            rows = sorted(rows, key=lambda row: 0 if row.get("category") == category else 1)
        return [
            {
                "chunk_id": str(row.get("_id")),
                "chunk_index": row.get("chunk_index"),
                "source": row.get("source"),
                "text": row.get("text"),
                "score": round(1.0 - 0.01 * index, 4),
            }
            for index, row in enumerate(rows[: int(limit)])
        ]

    def get_feature(self, feature_id):
        return dict(self.feature) if feature_id == "feature-1" else None

    def build_unified_context(self, feature_id, version_number):
        return {
            "featureName": self.feature["name"],
            "metadata": {
                "featureName": self.feature["name"],
                "versionNumber": version_number,
            },
            "featureDescription": self.feature["summary"],
            "summaries": {
                "prd": self.feature["text"],
            },
            # Realistic shape: extract_business_context() (store/features.py) always
            # returns short, distinct extracted LINES here, never the full raw document
            # as a single blob -- kept short and separate from self.feature["text"] so
            # tests can assert the raw PRD text is genuinely absent from a prompt
            # without that assertion being trivially defeated by this fixture.
            "businessContext": {
                "prd": {
                    "requirements": ["Only authenticated customers may create orders"],
                }
            },
            "flags": {
                "hasBusiness": True,
                "hasTechnical": False,
                "hasFunctional": True,
                "hasBusinessOnly": True,
                "figmaOk": False,
                "hasUI": False,
                "hasScreens": False,
                "smokeMode": False,
            }
        }

    def list_test_cases(self, **kwargs):
        return {"items": []}

    def get_case(self, case_id):
        return None

    def get_feature_cases(self, feature_id):
        return []

    def resolve_case_reference(self, reference_key=None, title=None, project_id=None):
        return None

    def find_case_by_identity(self, project_id, identity_hash=None, test_slug=None):
        return self.identity.get((project_id, identity_hash)) or self.identity.get((project_id, test_slug))

    def get_or_create_step(self, action, expected, embedding, auto_reuse):
        self.step_number += 1
        return {"step_id": f"step-{self.step_number}", "origin": "new", "score": 0}

    def find_similar_cases(self, embedding, suggest, exclude_id=None, top=5, project_id=None):
        return []

    def create_case(self, title, ctype, priority, preconditions, step_ids, tags,
                    embedding, feature_id, similar_to=None, project_id=None,
                    identity_hash=None, test_slug=None, metadata=None):
        case_id = f"case-{len(self.created) + 1}"
        row = {
            "id": case_id,
            "title": title,
            "type": ctype,
            "project_id": project_id,
            "identity_hash": identity_hash,
            "test_slug": test_slug,
            "metadata": metadata or {},
        }
        self.created.append(row)
        self.identity[(project_id, identity_hash)] = row
        self.identity[(project_id, test_slug)] = row
        return case_id

    def associate(self, feature_id, case_id, origin, score=None):
        self.associations.append((feature_id, case_id, origin, score))


class FakeEmbedder:
    def embed(self, text, task="document"):
        return [float(len(text) % 17), 1.0, 0.5]


class FakeLLM:
    def _raw_chat(self, system, user, num_ctx, temperature, max_tokens):
        import json
        res = self.chat_json(system, user)
        return json.dumps(res)

    def chat_json(self, system, user, **kwargs):
        if "Extract API entities and endpoints" in user:
            return {
                "grounded_entities": [{
                    "entity": "order",
                    "entity_type": "api_resource",
                    "evidence_quote": "customer to create an order",
                }],
                "apis": [{
                    "method": "POST",
                    "endpoint": "/v1/orders",
                    "complexity": "medium",
                    "evidence_quote": "POST /v1/orders",
                }],
                "ui_components": [],
            }
        if "Analyze Cross-Feature Overlap" in user:
            return {
                "inherited_tests": [],
                "covered_endpoints": [],
                "covered_flows": [],
                "already_covered_summary": "",
            }
        if "Generate focused API worker test cases" in user:
            if "HAPPY PATH TESTS ONLY" in user:
                status, suffix = 201, "accepts a valid order"
            elif "NEGATIVE AND VALIDATION TESTS ONLY" in user:
                status, suffix = 401, "rejects an unauthenticated customer"
            else:
                status, suffix = 503, "handles a dependency outage"
            return {
                "api_tests": [
                    {
                        "title": f"Create order {suffix}",
                        "intent": suffix,
                        "method": "POST",
                        "endpoint": "/v1/orders",
                        "priority": "High",
                        "steps": [{
                            "content": "Call POST /v1/orders",
                            "expectedResult": f"The response status is {status}",
                        }],
                        "expected_result": {"status_code": status},
                    },
                    {
                        "title": "Hallucinated endpoint is ignored",
                        "intent": "should not survive",
                        "method": "POST",
                        "endpoint": "/v1/invented",
                        "steps": [],
                    },
                ]
            }
        if "Generate UI validations" in user:
            return {"ui_validations": []}
        if "Generate E2E flows, edge cases, and business rule tests" in user:
            return {"e2e_tests": [], "edge_cases": [], "business_tests": []}
        if "Generate one business rule test" in user:
            return {"business_tests": []}
        raise AssertionError(f"Unexpected prompt: {user[:120]}")


class SpyLLM(FakeLLM):
    """Wraps FakeLLM to record every (system, user) prompt pair actually sent to the
    model, so tests can inspect which evidence each generation call received without
    reimplementing FakeLLM's response logic."""

    def __init__(self):
        self.calls = []

    def _raw_chat(self, system, user, num_ctx, temperature, max_tokens, timeout_seconds=None):
        self.calls.append({"system": system, "user": user})
        return super()._raw_chat(system, user, num_ctx, temperature, max_tokens)

    def calls_matching(self, marker: str) -> list:
        return [call for call in self.calls if marker in call["user"]]


class GenerationPipelineTests(unittest.TestCase):
    def test_requirement_source_prefix_is_removed_from_user_facing_prose(self):
        self.assertEqual(
            _clean_requirement_narrative(
                "PRD rule: At least one interest must be selected to create an event."
            ),
            "At least one interest must be selected to create an event.",
        )
        self.assertEqual(
            _clean_requirement_narrative("PRD requires that a name is provided."),
            "A name is provided.",
        )
        self.assertEqual(
            _clean_requirement_narrative(
                "PRD indicates that at least one interest must be selected."
            ),
            "At least one interest must be selected.",
        )
        self.assertEqual(
            _clean_requirement_narrative(
                "According to checkout-requirements.pdf, a promo code may be applied once."
            ),
            "A promo code may be applied once.",
        )
        self.assertEqual(
            _clean_requirement_narrative(
                "Security specification mandates that expired sessions are rejected."
            ),
            "Expired sessions are rejected.",
        )
        self.assertEqual(
            _clean_requirement_narrative(
                "JIRA-428 states that guests cannot delete an event."
            ),
            "Guests cannot delete an event.",
        )
        self.assertEqual(
            _clean_requirement_narrative(
                "System requires that users authenticate before checkout."
            ),
            "System requires that users authenticate before checkout.",
        )

    def test_semantic_reuse_does_not_merge_distinct_api_scenarios(self):
        candidate = {
            "type": "api",
            "title": "Valid OTP request succeeds",
            "metadata": {
                "method": "POST",
                "endpoint": "/auth/send-otp",
                "expected_result": {"status_code": 200},
                "intent": "valid phone requests an OTP",
            },
        }
        negative = {
            "method": "POST",
            "endpoint": "/auth/send-otp",
            "expected_result": {"status_code": 429},
            "intent": "rate limited phone is rejected",
            "title": "OTP request is rate limited",
        }
        self.assertFalse(_semantic_reuse_compatible(candidate, negative, "api"))

    def test_budget_trims_over_represented_category_to_focus_weight(self):
        # With equal focus weights, no single category should dominate: the
        # over-represented suite (API here, 60 cases) is trimmed toward its
        # weighted share of the produced pool, while categories that are already
        # at or below their share are left untouched (we trim, never pad).
        suites = {
            "api_tests": [{"id": index} for index in range(60)],
            "ui_validations": [{"id": index} for index in range(12)],
            "business_tests": [{"id": index} for index in range(10)],
            "e2e_tests": [{"id": index} for index in range(10)],
            "edge_cases": [{"id": index} for index in range(8)],
        }
        budgeted = _budget_suites(
            dict(suites),
            24,
            {"functional": 20, "e2e": 20, "api": 20, "nfr": 20, "ui": 20},
        )
        counts = {key: len(value) for key, value in budgeted.items()}
        # Pool = 100 cases over 5 equal weights -> ~20 per category.
        self.assertEqual(20, counts["api_tests"])          # trimmed down from 60
        # Thin categories are preserved as-is, never inflated to hit the target.
        self.assertEqual(12, counts["ui_validations"])
        self.assertEqual(10, counts["business_tests"])
        self.assertEqual(10, counts["e2e_tests"])
        self.assertEqual(8, counts["edge_cases"])

    def test_budget_zero_weight_drops_category(self):
        suites = {
            "api_tests": [{"id": index} for index in range(60)],
            "ui_validations": [{"id": index} for index in range(12)],
            "business_tests": [{"id": index} for index in range(10)],
            "e2e_tests": [{"id": index} for index in range(10)],
            "edge_cases": [{"id": index} for index in range(8)],
        }
        budgeted = _budget_suites(
            dict(suites),
            24,
            {"functional": 25, "e2e": 25, "api": 0, "nfr": 25, "ui": 25},
        )
        # A zero focus weight removes the category entirely...
        self.assertEqual(0, len(budgeted["api_tests"]))
        # ...and the remaining categories are still capped by their own material,
        # not padded (each stays at its produced count here).
        self.assertEqual(10, len(budgeted["business_tests"]))
        self.assertEqual(10, len(budgeted["e2e_tests"]))
        self.assertEqual(8, len(budgeted["edge_cases"]))

    def test_ui_components_are_recovered_from_document_controls(self):
        components = _derive_ui_components(
            "OTPInput\nPhoneInput\nNameInput\nInterestSelector\nDOBPicker"
        )
        labels = {component["element"] for component in components}
        self.assertTrue({"OTP", "Phone", "Name", "Interest", "DOB"} <= labels)

    def test_raw_spec_guard_and_baseline_coverage(self):
        surface = _parse_raw_api_spec("POST /v1/orders\nGET /v1/orders/{id}")
        guarded = _filter_api_tests(
            [
                {"method": "POST", "endpoint": "/v1/orders", "title": "valid"},
                {"method": "POST", "endpoint": "/v1/invented", "title": "invalid"},
            ],
            surface,
        )
        self.assertEqual(["/v1/orders"], [case["endpoint"] for case in guarded])
        covered = _ensure_api_endpoint_coverage(guarded, surface)
        self.assertEqual(
            {"POST:/v1/orders", "GET:/v1/orders/{id}"},
            {f"{case['method']}:{case['endpoint']}" for case in covered},
        )

    def test_api_dedup_keeps_distinct_status_scenarios(self):
        cases = [
            {
                "title": "Create succeeds",
                "intent": "valid create",
                "method": "POST",
                "endpoint": "/v1/orders",
                "status_code": 201,
            },
            {
                "title": "Create rejected",
                "intent": "valid create",
                "method": "POST",
                "endpoint": "/v1/orders",
                "status_code": 401,
            },
        ]
        self.assertEqual(2, len(_deduplicate(cases, "api_tests")))

    def test_pipeline_guards_endpoints_and_persists_lineage_identity(self):
        store = FakeStore()
        progress_events = []
        result = generate_fresh_testcases_pipeline(
            store,
            FakeLLM(),
            FakeEmbedder(),
            {
                "feature_id": "feature-1",
                "total": 6,
                "focus": {"functional": 0, "e2e": 0, "api": 100, "nfr": 0},
                "smoke_mode": True,
            },
            update_job_fn=lambda stage, progress=None: progress_log(progress_events, stage, progress),
        )

        self.assertGreaterEqual(result["cases_new"], 3)
        self.assertEqual(1, result["discovered_api_count"])
        self.assertTrue(store.created)
        self.assertTrue(all(case["identity_hash"] for case in store.created))
        self.assertTrue(all(case["test_slug"] for case in store.created))
        self.assertTrue(all(
            case["metadata"].get("endpoint") == "/v1/orders"
            for case in store.created if case["type"] == "api"
        ))
        self.assertEqual(100, progress_events[-1][1])

    # --- Query construction: deterministic and testable in isolation (no pipeline run) ---

    def test_retrieval_query_construction_is_deterministic(self):
        entities = [{"entity": "order", "entity_type": "api_resource"}]
        api_surface = [{"method": "post", "endpoint": "/v1/orders"}]
        ui_components = [{"screen": "Checkout", "element": "Quantity"}]
        business_context = {"prd": {"requirements": ["Only authenticated customers may create orders"]}}

        first = _build_api_retrieval_query(entities, api_surface)
        second = _build_api_retrieval_query(entities, api_surface)
        self.assertEqual(first, second)
        self.assertIn("POST /v1/orders", first)
        self.assertIn("order", first)

        ui_first = _build_ui_retrieval_query(ui_components, "Create order")
        ui_second = _build_ui_retrieval_query(ui_components, "Create order")
        self.assertEqual(ui_first, ui_second)
        self.assertIn("Quantity", ui_first)
        self.assertIn("Checkout", ui_first)

        e2e_first = _build_e2e_retrieval_query(business_context, "Create order", "Create a customer order")
        e2e_second = _build_e2e_retrieval_query(business_context, "Create order", "Create a customer order")
        self.assertEqual(e2e_first, e2e_second)
        self.assertIn("Only authenticated customers may create orders", e2e_first)

    # --- API query broadening on endpoint-sparse documents (RAG live-eval follow-up:
    # the Authentication feature's live run found a 1-endpoint API query converging
    # with the E2E category's query on the same top retrieved chunks) --------------

    def test_api_query_broadens_with_api_adjacent_lines_when_endpoints_sparse(self):
        entities = []
        api_surface = [{"method": "post", "endpoint": "/auth/refresh"}]  # only 1 -> sparse
        business_context = {
            "prd": {
                "requirements": [
                    "The refresh endpoint must return a 401 status code for an expired token.",
                    "Support must respond to escalations within 24 hours.",  # not API-adjacent
                    "All API requests must include a valid Authorization header.",
                ]
            }
        }
        query = _build_api_retrieval_query(entities, api_surface, business_context)
        self.assertIn("POST /auth/refresh", query)
        self.assertIn("The refresh endpoint must return a 401 status code for an expired token.", query)
        self.assertIn("All API requests must include a valid Authorization header.", query)
        # The non-API-adjacent line must NOT be pulled in -- broadening is scoped,
        # not "just append the whole description" (that's what would make it
        # converge with the E2E query instead of differentiating from it).
        self.assertNotIn("Support must respond to escalations within 24 hours.", query)

    def test_api_query_does_not_broaden_when_endpoints_are_plentiful(self):
        entities = []
        api_surface = [
            {"method": "get", "endpoint": "/trust/{user_id}"},
            {"method": "post", "endpoint": "/trust/recalculate"},
        ]
        business_context = {
            "prd": {"requirements": ["The API must validate every request payload."]}
        }
        query = _build_api_retrieval_query(entities, api_surface, business_context)
        # >= 2 discovered endpoints: no broadening, matches pre-fix behavior exactly.
        self.assertEqual("GET /trust/{user_id} POST /trust/recalculate", query)

    def test_api_query_broadening_is_deterministic_and_safe_with_no_business_context(self):
        api_surface = [{"method": "post", "endpoint": "/auth/refresh"}]
        first = _build_api_retrieval_query([], api_surface, None)
        second = _build_api_retrieval_query([], api_surface, None)
        self.assertEqual(first, second)
        self.assertEqual("POST /auth/refresh", first)  # no crash, no bogus broadening

    def test_api_adjacent_requirement_lines_filters_by_keyword(self):
        business_context = {
            "requirements": [
                "The endpoint must validate the request body.",
                "Marketing needs a new landing page banner.",
            ]
        }
        lines = _api_adjacent_requirement_lines(business_context)
        self.assertEqual(["The endpoint must validate the request body."], lines)

    def test_broadened_api_query_differentiates_from_e2e_query_on_authentication_shaped_data(self):
        # Reproduces the live-evaluation Authentication scenario: 1 discovered
        # endpoint, full feature description, and a mix of API- and non-API-shaped
        # requirement lines -- the exact shape that made the API and E2E categories
        # converge on the same retrieved chunks in the live run.
        entities = []
        api_surface = [{"method": "post", "endpoint": "/auth/refresh"}]
        feature_name = "Authentication"
        feature_description = (
            "Users authenticate via phone number and one-time codes, receiving "
            "short-lived access tokens for protected endpoints and single-use "
            "refresh tokens for seamless re-authentication."
        )
        business_context = {
            "prd": {
                "requirements": [
                    "AUTH-002: Access tokens are short-lived.",
                    "AUTH-006: A refresh token that has already been used once must be rejected "
                    "with a 401-equivalent error from the endpoint.",
                    "NFR-A2: All authentication endpoints must fail closed.",
                ]
            }
        }
        api_query = _build_api_retrieval_query(entities, api_surface, business_context)
        e2e_query = _build_e2e_retrieval_query(business_context, feature_name, feature_description)

        self.assertNotEqual(api_query, e2e_query)
        # The API query stays anchored on the endpoint and only the API-adjacent
        # requirement lines -- it must not silently absorb the full description
        # text that makes the E2E query broad.
        self.assertNotIn(feature_description, api_query)
        self.assertIn("POST /auth/refresh", api_query)

    # --- Endpoint extraction/normalization formatting (RAG live-eval follow-up: a
    # markdown-wrapped endpoint like "`POST /auth/refresh`" left a stray trailing
    # backtick in the extracted endpoint AND survived as a duplicate alongside the
    # clean version, because the dedup key didn't normalize the backtick away) ----

    def test_parse_raw_api_spec_strips_stray_backtick_and_dedupes_markdown_variant(self):
        # One endpoint, appearing once wrapped in a markdown inline-code span and
        # once written plainly -- exactly how a PRD mixes "see `POST /auth/refresh`"
        # prose with a clean endpoint listing elsewhere in the same document.
        raw_spec = "See `POST /auth/refresh` for details.\nPOST /auth/refresh"
        surface = _parse_raw_api_spec(raw_spec)
        self.assertEqual(1, len(surface))
        self.assertEqual("/auth/refresh", surface[0]["endpoint"])
        self.assertNotIn("`", surface[0]["endpoint"])

    def test_merge_api_candidates_dedupes_backtick_and_clean_variants(self):
        clean = [{"method": "POST", "endpoint": "/auth/refresh"}]
        backtick_wrapped = [{"method": "POST", "endpoint": "/auth/refresh`"}]
        merged = _merge_api_candidates(clean, backtick_wrapped)
        self.assertEqual(1, len(merged))
        self.assertEqual("/auth/refresh", merged[0]["endpoint"])

    def test_clean_endpoint_strips_markdown_wrapper_characters(self):
        self.assertEqual("/auth/refresh", _clean_endpoint("/auth/refresh`"))
        self.assertEqual("/auth/refresh", _clean_endpoint("`/auth/refresh`"))
        self.assertEqual("/v1/orders", _clean_endpoint("/v1/orders."))
        self.assertEqual("/v1/orders", _clean_endpoint("/v1/orders)"))

    def test_normalize_endpoint_strips_markdown_wrapper_characters_for_dedup(self):
        self.assertEqual(normalize_endpoint("/auth/refresh"), normalize_endpoint("/auth/refresh`"))
        self.assertEqual(normalize_endpoint("/auth/refresh"), normalize_endpoint("`/auth/refresh`"))

    def test_authentication_shaped_raw_spec_produces_one_clean_api_query_entry(self):
        # End-to-end reproduction of the exact live-evaluation artifact: feeding
        # _parse_raw_api_spec()'s output straight into _build_api_retrieval_query()
        # must no longer produce "POST /auth/refresh POST /auth/refresh`".
        raw_spec = "The client calls `POST /auth/refresh` to rotate tokens.\nPOST /auth/refresh"
        api_surface = _merge_api_candidates(_parse_raw_api_spec(raw_spec))
        query = _build_api_retrieval_query([], api_surface, None)
        self.assertEqual("POST /auth/refresh", query)
        self.assertEqual(1, query.count("/auth/refresh"))
        self.assertNotIn("`", query)

    def test_category_top_k_defaults_are_ollama_aware(self):
        for category in ("api", "ui", "e2e"):
            self.assertLessEqual(_category_top_k(category, True), _category_top_k(category, False))
            self.assertGreater(_category_top_k(category, True), 0)

    # --- Grounding/extraction evidence stays broad and unranked (recall, unchanged) ---

    def test_grounding_evidence_corpus_stays_broad_and_unranked(self):
        # Mirrors exactly how generate_fresh_testcases_pipeline() builds the broad
        # rag_context used for extraction (Pass 0/1) and grounding (_evidence_corpus /
        # _grounded_item_supported): ALL of this feature's chunks, unranked, score=1.0.
        # This must keep including every chunk regardless of category -- it is NOT the
        # category-scoped top-K used by generation.
        store = FakeStore()
        chunks = [row for row in store.fchunks.rows if row.get("feature_id") == "feature-1"]
        rag_context = {
            "summary": "Create a customer order",
            "retrieved_chunks": [
                {"sourceType": item.get("source", "document"), "score": 1.0, "text": item.get("text", "")}
                for item in chunks
            ],
        }
        context = {
            "featureName": "Create order",
            "featureDescription": "Create a customer order",
            "summaries": {"prd": "", "hld": "", "lld": ""},
            "rawApiSpec": "",
        }
        corpus = _evidence_corpus(context, rag_context)
        self.assertIn("accepts a valid order payload", corpus)  # api chunk
        self.assertIn("Quantity field", corpus)                 # ui chunk
        self.assertIn("guests are redirected to sign in", corpus)  # e2e chunk

    def test_extraction_passes_still_receive_the_full_broad_chunk_corpus(self):
        store = FakeStore()
        llm = SpyLLM()
        generate_fresh_testcases_pipeline(
            store,
            llm,
            FakeEmbedder(),
            {
                "feature_id": "feature-1",
                "total": 4,
                "focus": {"functional": 0, "e2e": 0, "api": 100, "nfr": 0},
                "smoke_mode": True,
            },
        )
        extraction_calls = llm.calls_matching("Extract API entities and endpoints")
        self.assertEqual(1, len(extraction_calls))
        combined = extraction_calls[0]["system"] + extraction_calls[0]["user"]
        # Pass 1 must still see ALL three chunks (broad/unranked), not just one category.
        self.assertIn("accepts a valid order payload", combined)
        self.assertIn("Quantity field", combined)
        self.assertIn("guests are redirected to sign in", combined)

    # --- Generation evidence is category-specific (precision, the approved fix) ---

    def test_ui_generation_receives_nonempty_retrieved_rag_evidence(self):
        # This is the regression test the investigation flagged as important: the UI
        # generation path used to pass {} as its RAG context unconditionally, so its
        # prompt NEVER contained retrieved evidence. It must now contain real, retrieved
        # chunk text.
        store = FakeStore()
        llm = SpyLLM()
        generate_fresh_testcases_pipeline(
            store,
            llm,
            FakeEmbedder(),
            {
                "feature_id": "feature-1",
                "total": 4,
                "focus": {"functional": 0, "e2e": 0, "api": 100, "nfr": 0},
                "smoke_mode": True,
            },
        )
        ui_calls = llm.calls_matching("Generate UI validations")
        self.assertTrue(ui_calls, "expected at least one UI worker call")
        for call in ui_calls:
            self.assertNotIn("RAG CHUNKS: none retrieved.", call["system"])
            self.assertIn("RAG SUMMARY:", call["system"])
        combined = "\n".join(call["system"] for call in ui_calls)
        self.assertIn("Quantity field", combined)

    def test_api_generation_receives_api_relevant_retrieved_chunks(self):
        store = FakeStore()
        llm = SpyLLM()
        generate_fresh_testcases_pipeline(
            store,
            llm,
            FakeEmbedder(),
            {
                "feature_id": "feature-1",
                "total": 4,
                "focus": {"functional": 0, "e2e": 0, "api": 100, "nfr": 0},
                "smoke_mode": True,
            },
        )
        api_calls = llm.calls_matching("Generate focused API worker test cases")
        self.assertTrue(api_calls, "expected at least one API worker call")
        combined = "\n".join(call["system"] for call in api_calls)
        self.assertIn("accepts a valid order payload", combined)
        api_retrieval_calls = [
            call for call in store.search_feature_chunks_calls if call["category"] == "api"
        ]
        self.assertEqual(1, len(api_retrieval_calls))
        self.assertEqual("feature-1", api_retrieval_calls[0]["feature_id"])

    def test_e2e_generation_receives_e2e_retrieved_evidence(self):
        store = FakeStore()
        llm = SpyLLM()
        generate_fresh_testcases_pipeline(
            store,
            llm,
            FakeEmbedder(),
            {
                "feature_id": "feature-1",
                "total": 4,
                "focus": {"functional": 20, "e2e": 20, "api": 20, "nfr": 20, "ui": 20},
                "smoke_mode": True,
            },
        )
        e2e_calls = llm.calls_matching("Generate E2E flows, edge cases, and business rule tests")
        self.assertTrue(e2e_calls, "expected the E2E agent call")
        combined = "\n".join(call["user"] for call in e2e_calls)
        self.assertIn("guests are redirected to sign in", combined)
        # E2E evidence must no longer include a duplicate raw PRD block.
        self.assertNotIn("REQUIREMENT EVIDENCE:", combined)

    def test_generation_prompts_no_longer_duplicate_the_raw_prd_block(self):
        store = FakeStore()
        llm = SpyLLM()
        generate_fresh_testcases_pipeline(
            store,
            llm,
            FakeEmbedder(),
            {
                "feature_id": "feature-1",
                "total": 4,
                "focus": {"functional": 0, "e2e": 0, "api": 100, "nfr": 0},
                "smoke_mode": True,
            },
        )
        api_calls = llm.calls_matching("Generate focused API worker test cases")
        for call in api_calls:
            self.assertNotIn("REQUIREMENT EVIDENCE:", call["system"])

    def test_workers_within_one_category_share_a_single_retrieval_call(self):
        # api_surface has exactly one endpoint here, so _chunks(api_surface, 8) yields a
        # single chunk and the DAG only spawns 2-3 API workers (happy/negative[/chaos]) --
        # all of them must reuse ONE api-category retrieval, not one each.
        store = FakeStore()
        generate_fresh_testcases_pipeline(
            store,
            FakeLLM(),
            FakeEmbedder(),
            {
                "feature_id": "feature-1",
                "total": 6,
                "focus": {"functional": 0, "e2e": 0, "api": 100, "nfr": 0},
                "smoke_mode": True,
            },
        )
        # Exactly one retrieval call per category (api/ui/e2e/business), regardless of
        # how many API/UI workers the DAG fans out, and regardless of the E2E/business
        # fallback passes.
        self.assertEqual(4, len(store.search_feature_chunks_calls))
        categories = sorted(call["category"] for call in store.search_feature_chunks_calls)
        self.assertEqual(["api", "business", "e2e", "ui"], categories)

    def test_large_and_small_documents_both_build_valid_generation_prompts(self):
        # Exercise the prompt builders directly (not the full pipeline, which has its
        # own unrelated guards like InsufficientEvidenceError for short fixtures) across
        # a small and a large raw PRD, proving: (1) neither size crashes prompt
        # construction, (2) the raw PRD text never leaks into the generation prompt at
        # either size (the redundant-bulk-text removal), and (3) top_k is honored
        # regardless of how many chunks were retrieved.
        small_prd = "The order service allows a customer to create an order."
        large_prd = small_prd * 2000  # far larger than the 15000-char Ollama PRD cap
        many_chunks = [
            {"sourceType": "prd", "score": 1.0 - (index * 0.01), "text": f"Evidence chunk number {index}."}
            for index in range(20)
        ]
        for label, prd_text in (("small", small_prd), ("large", large_prd)):
            with self.subTest(label=label):
                context = {
                    "featureName": "Create order",
                    "featureDescription": "Create a customer order",
                    "summaries": {"prd": prd_text, "hld": "", "lld": "", "figma": {}},
                    "technicalContext": {},
                    "businessContext": {},
                    "flags": {"smokeMode": False},
                    "rawApiSpec": "POST /v1/orders",
                }
                rag_context = {"summary": "Create order", "retrieved_chunks": many_chunks}

                api_prompt = build_api_agent_prompt(context, rag_context, [], "happy", top_k=4)
                system_content = api_prompt["messages"][0]["content"]
                self.assertNotIn(prd_text, system_content)
                self.assertEqual(4, system_content.count("SOURCE=prd"))

                ui_prompt = build_ui_agent_prompt(context, [], rag_context, top_k=4)
                self.assertNotIn(prd_text, ui_prompt["messages"][0]["content"])

                e2e_prompt = build_e2e_agent_prompt(context, [], [], rag_context, 1, top_k=4)
                self.assertIsInstance(e2e_prompt, str)
                self.assertNotIn(prd_text, e2e_prompt)
                self.assertEqual(4, e2e_prompt.count("SOURCE=prd"))

    # --- Business RAG (primary + fallback) ------------------------------------------

    def test_business_retrieval_query_is_deterministic_and_built_from_extracted_data(self):
        business_context = {"prd": {
            "requirements": ["Only one promo code may be applied per order"],
            "acceptanceCriteria": ["Given two codes, the second is rejected"],
            "userStories": ["As a customer I want my discount applied once"],
        }}
        first = _build_business_retrieval_query(business_context, "Create order", "Create a customer order")
        second = _build_business_retrieval_query(business_context, "Create order", "Create a customer order")
        self.assertEqual(first, second)
        self.assertIn("Only one promo code may be applied per order", first)
        self.assertIn("Given two codes, the second is rejected", first)
        self.assertIn("As a customer I want my discount applied once", first)
        # Flat (non-nested) businessContext shape -- what extract_business_context()
        # actually returns in the real pipeline -- must also work.
        flat = _build_business_retrieval_query(
            {"requirements": ["Only one promo code may be applied per order"]},
            "Create order", "Create a customer order",
        )
        self.assertIn("Only one promo code may be applied per order", flat)

    def test_business_primary_generation_receives_business_specific_rag_evidence(self):
        store = FakeStore()
        llm = SpyLLM()
        generate_fresh_testcases_pipeline(
            store,
            llm,
            FakeEmbedder(),
            {
                "feature_id": "feature-1",
                "total": 4,
                "focus": {"functional": 20, "e2e": 20, "api": 20, "nfr": 20, "ui": 20},
                "smoke_mode": True,
            },
        )
        # The combined E2E/edge/business call is the PRIMARY producer of business_tests.
        primary_calls = llm.calls_matching("Generate E2E flows, edge cases, and business rule tests")
        self.assertTrue(primary_calls, "expected the combined E2E/edge/business call")
        combined = "\n".join(call["user"] for call in primary_calls)
        self.assertIn("BUSINESS RULE RETRIEVED EVIDENCE", combined)
        self.assertIn("Only one promo code may be applied per order", combined)
        # Labeled distinctly from the E2E-journey block, not merged into it.
        self.assertIn("E2E/JOURNEY RETRIEVED EVIDENCE", combined)

    def test_business_fallback_receives_the_same_business_rag_evidence(self):
        store = FakeStore()
        llm = SpyLLM()
        generate_fresh_testcases_pipeline(
            store,
            llm,
            FakeEmbedder(),
            {
                "feature_id": "feature-1",
                "total": 4,
                "focus": {"functional": 20, "e2e": 20, "api": 20, "nfr": 20, "ui": 20},
                "smoke_mode": True,
            },
        )
        # FakeLLM always returns empty business_tests from the primary call, so the
        # acceptable_business_min gate always fires the fallback in this fixture.
        fallback_calls = llm.calls_matching("Generate one business rule test per requirement rule")
        self.assertTrue(fallback_calls, "expected the business fallback call to fire")
        combined = "\n".join(call["user"] for call in fallback_calls)
        self.assertIn("Only one promo code may be applied per order", combined)
        self.assertIn("RETRIEVED EVIDENCE", combined)
        # Raw PRD text must not be duplicated into the fallback prompt either.
        self.assertNotIn(store.feature["text"], combined)

    def test_business_retrieval_occurs_once_per_generation_run(self):
        store = FakeStore()
        generate_fresh_testcases_pipeline(
            store,
            FakeLLM(),
            FakeEmbedder(),
            {
                "feature_id": "feature-1",
                "total": 6,
                "focus": {"functional": 0, "e2e": 0, "api": 100, "nfr": 0},
                "smoke_mode": True,
            },
        )
        business_calls = [c for c in store.search_feature_chunks_calls if c["category"] == "business"]
        self.assertEqual(1, len(business_calls))
        self.assertEqual("feature-1", business_calls[0]["feature_id"])
        # Total retrieval calls: exactly one per category (api/ui/e2e/business), never
        # once per worker -- unchanged rule, now covering 4 categories instead of 3.
        self.assertEqual(4, len(store.search_feature_chunks_calls))
        categories = sorted(c["category"] for c in store.search_feature_chunks_calls)
        self.assertEqual(["api", "business", "e2e", "ui"], categories)

    def test_business_test_prompt_builder_never_duplicates_raw_prd(self):
        rag_context = {"summary": "s", "retrieved_chunks": [
            {"sourceType": "prd", "score": 0.9, "text": "Only one promo code may be applied per order."},
        ]}
        context = {
            "featureName": "Create order",
            "businessContext": {"prd": {"requirements": ["Only one promo code may be applied per order"]}},
            "summaries": {"prd": "RAW FULL PRD TEXT THAT SHOULD NOT APPEAR" * 50},
        }
        prompt = build_business_test_prompt(context, rag_context, top_k=4)
        self.assertNotIn("RAW FULL PRD TEXT THAT SHOULD NOT APPEAR", prompt)
        self.assertIn("Only one promo code may be applied per order", prompt)
        # The pre-existing bug where business_rules were read only from a nested "prd"
        # shape (never what the real pipeline produces) is fixed: with a single rule
        # supplied, exactly one test is requested, not the generic fallback-to-10.
        self.assertIn("Generate exactly 1 tests", prompt)

    def test_business_test_prompt_builder_handles_flat_business_context_shape(self):
        # The real pipeline's build_unified_context() returns businessContext WITHOUT a
        # "prd" nesting -- confirm the fix in build_business_test_prompt() covers it.
        context = {
            "featureName": "Create order",
            "businessContext": {"requirements": ["A", "B", "C"]},
            "summaries": {"prd": ""},
        }
        prompt = build_business_test_prompt(context, {}, top_k=4)
        self.assertIn("Generate exactly 3 tests", prompt)

    # --- Edge-case RAG: shares E2E's call, gets E2E + API evidence, clearly labeled --

    def test_edge_case_generation_receives_both_e2e_and_api_evidence(self):
        store = FakeStore()
        llm = SpyLLM()
        generate_fresh_testcases_pipeline(
            store,
            llm,
            FakeEmbedder(),
            {
                "feature_id": "feature-1",
                "total": 4,
                "focus": {"functional": 20, "e2e": 20, "api": 20, "nfr": 20, "ui": 20},
                "smoke_mode": True,
            },
        )
        combined_calls = llm.calls_matching("Generate E2E flows, edge cases, and business rule tests")
        self.assertTrue(combined_calls)
        combined = "\n".join(call["user"] for call in combined_calls)
        # API/state-mutation evidence block (for edge_cases) is present and labeled.
        self.assertIn("API/STATE-MUTATION RETRIEVED EVIDENCE", combined)
        self.assertIn("accepts a valid order payload", combined)  # the api-tagged chunk
        # E2E/journey evidence block (for e2e_tests) is present and labeled separately.
        self.assertIn("E2E/JOURNEY RETRIEVED EVIDENCE", combined)
        self.assertIn("guests are redirected to sign in", combined)  # the e2e-tagged chunk
        # No fifth/independent retrieval query for edge cases: it reuses the SAME
        # api-category retrieval call already made for api_tests, not a new one.
        api_calls = [c for c in store.search_feature_chunks_calls if c["category"] == "api"]
        self.assertEqual(1, len(api_calls))

    def test_no_fifth_retrieval_category_was_introduced(self):
        store = FakeStore()
        generate_fresh_testcases_pipeline(
            store,
            FakeLLM(),
            FakeEmbedder(),
            {
                "feature_id": "feature-1",
                "total": 4,
                "focus": {"functional": 0, "e2e": 0, "api": 100, "nfr": 0},
                "smoke_mode": True,
            },
        )
        categories = {c["category"] for c in store.search_feature_chunks_calls}
        self.assertEqual({"api", "ui", "e2e", "business"}, categories)
        self.assertNotIn("edge", categories)
        self.assertNotIn("edge_cases", categories)

    # --- Regression: existing API/UI/E2E behavior is unchanged by this pass ---------

    def test_existing_api_ui_e2e_retrieval_behavior_is_unchanged(self):
        store = FakeStore()
        llm = SpyLLM()
        generate_fresh_testcases_pipeline(
            store,
            llm,
            FakeEmbedder(),
            {
                "feature_id": "feature-1",
                "total": 4,
                "focus": {"functional": 20, "e2e": 20, "api": 20, "nfr": 20, "ui": 20},
                "smoke_mode": True,
            },
        )
        api_calls = llm.calls_matching("Generate focused API worker test cases")
        self.assertTrue(api_calls)
        self.assertIn("accepts a valid order payload", "\n".join(c["system"] for c in api_calls))

        ui_calls = llm.calls_matching("Generate UI validations")
        self.assertTrue(ui_calls)
        for call in ui_calls:
            self.assertNotIn("RAG CHUNKS: none retrieved.", call["system"])

        e2e_calls = llm.calls_matching("Generate E2E flows, edge cases, and business rule tests")
        self.assertTrue(e2e_calls)
        self.assertIn("guests are redirected to sign in", "\n".join(c["user"] for c in e2e_calls))

    # --- Grounding/extraction still see the FULL broad chunk corpus (unchanged) -----

    def test_grounding_and_extraction_still_see_the_full_broad_corpus_after_business_edge_fix(self):
        store = FakeStore()
        chunks = [row for row in store.fchunks.rows if row.get("feature_id") == "feature-1"]
        rag_context = {
            "summary": "Create a customer order",
            "retrieved_chunks": [
                {"sourceType": item.get("source", "document"), "score": 1.0, "text": item.get("text", "")}
                for item in chunks
            ],
        }
        context = {
            "featureName": "Create order",
            "featureDescription": "Create a customer order",
            "summaries": {"prd": "", "hld": "", "lld": ""},
            "rawApiSpec": "",
        }
        corpus = _evidence_corpus(context, rag_context)
        self.assertIn("accepts a valid order payload", corpus)       # api chunk
        self.assertIn("Quantity field", corpus)                      # ui chunk
        self.assertIn("guests are redirected to sign in", corpus)    # e2e chunk
        self.assertIn("Only one promo code may be applied per order", corpus)  # business chunk

    # --- Regression: no extra LLM call was introduced for query generation ---------

    def test_no_extra_llm_call_is_introduced_for_business_or_edge_retrieval(self):
        # The business/edge retrieval queries are pure, deterministic string builders
        # (_build_business_retrieval_query() etc.) built from data Pass 0/1/2 already
        # extracted -- they must never cost an LLM call. FakeLLM.chat_json() already
        # raises AssertionError on any prompt it doesn't recognize, so an accidentally
        # added "generate a retrieval query" call would already fail this test (and
        # every other test in this file) -- this test makes that guarantee explicit and
        # pins the exact expected call count as a regression baseline.
        store = FakeStore()
        llm = SpyLLM()
        generate_fresh_testcases_pipeline(
            store,
            llm,
            FakeEmbedder(),
            {
                "feature_id": "feature-1",
                "total": 4,
                "focus": {"functional": 20, "e2e": 20, "api": 20, "nfr": 20, "ui": 20},
                "smoke_mode": True,
            },
        )
        # 1 Pass-1 extraction + 0 fusion (empty project) + 3 API workers (happy/negative/chaos) +
        # 1 UI worker + 1 combined E2E/edge/business call + 1 business fallback
        # (FakeLLM's primary call always returns empty business_tests, so the fallback
        # always fires for this fixture) = 7. No Pass-2 CRUD-inference call (Pass 0
        # already found a verbatim endpoint) and no repair call (smoke_mode=True skips
        # it) for this fixture.
        self.assertEqual(7, len(llm.calls))
        for call in llm.calls:
            self.assertNotIn("retrieval query", call["user"].lower())
            self.assertNotIn("search query", call["user"].lower())


def progress_log(target, stage, value):
    target.append((stage, value))


if __name__ == "__main__":
    unittest.main()
