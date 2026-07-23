import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../app")))

from testgen.service import (  # noqa: E402
    _budget_suites,
    _deduplicate,
    _derive_ui_components,
    _ensure_api_endpoint_coverage,
    _filter_api_tests,
    _clean_requirement_narrative,
    _parse_raw_api_spec,
    _semantic_reuse_compatible,
    generate_fresh_testcases_pipeline,
)


class FakeCollection:
    def __init__(self, rows=None):
        self.rows = rows or []

    def find(self, query):
        return list(self.rows)

    def find_one(self, query):
        return None


class FakeStore:
    def __init__(self):
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
        self.fchunks = FakeCollection([{"source": "prd", "text": text}])
        self.created = []
        self.associations = []
        self.identity = {}
        self.step_number = 0

    def get_feature(self, feature_id):
        return dict(self.feature) if feature_id == "feature-1" else None

    def build_unified_context(self, feature_id, version_number):
        return {
            "metadata": {
                "featureName": self.feature["name"],
                "versionNumber": version_number,
            },
            "featureDescription": self.feature["summary"],
            "summaries": {
                "prd": self.feature["text"],
            },
            "businessContext": {
                "prd": {
                    "requirements": [self.feature["text"]],
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


def progress_log(target, stage, value):
    target.append((stage, value))


if __name__ == "__main__":
    unittest.main()
