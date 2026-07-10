import os
import sys

# Ensure app directory is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../app')))

import validator
import test_plan
from testgen import lineage, prompt_builder

def test_validator_scoring_and_weak_areas():
    # Setup mock questions
    questions = [
        {
            "id": "q1",
            "category": "business_rules",
            "question": "What is the OTP expiration limit?",
            "options": ["1 minute", "3 minutes", "5 minutes", "10 minutes"],
            "correct_answer_index": 2  # 5 minutes
        },
        {
            "id": "q2",
            "category": "business_rules",
            "question": "What is the maximum login retry limit?",
            "options": ["3 times", "5 times", "10 times", "No limit"],
            "correct_answer_index": 1  # 5 times
        },
        {
            "id": "q3",
            "category": "state_transitions",
            "question": "What state does the version transition to on ready?",
            "options": ["DRAFT", "READY", "FAILED", "ARCHIVED"],
            "correct_answer_index": 1  # READY
        },
        {
            "id": "q4",
            "category": "state_transitions",
            "question": "What state does the version transition to on failure?",
            "options": ["DRAFT", "READY", "FAILED", "ARCHIVED"],
            "correct_answer_index": 2  # FAILED
        }
    ]

    # Setup mock answers
    answers = [
        {
            "question_id": "q1",
            "selected_index": 2,  # Correct (5 minutes)
            "confidence": "high",
            "comment": "As specified in PRD section 2.1"
        },
        {
            "question_id": "q2",
            "selected_index": 0,  # Incorrect (3 times, correct is 5 times)
            "confidence": "medium",
            "comment": "Guessing based on typical standards"
        },
        {
            "question_id": "q3",
            "selected_index": 1,  # Correct (READY)
            "confidence": "high"
        },
        {
            "question_id": "q4",
            "selected_index": 0,  # Incorrect (DRAFT, correct is FAILED)
            "confidence": "low"
        }
    ]

    # Test scoring computation
    score_report = validator.compute_validator_score(questions, answers)
    
    assert score_report["totalQuestions"] == 4
    assert score_report["answeredCount"] == 4
    assert score_report["completionPercent"] == 100
    assert score_report["correctCount"] == 2
    assert score_report["wrongCount"] == 2
    assert score_report["clarityScore"] == 50  # 2/4 = 50%
    assert score_report["rating"] == "Average"

    # Test weak areas detection (accuracy < 60%)
    # business_rules: 1 correct, 1 wrong = 50% (Weak)
    # state_transitions: 1 correct, 1 wrong = 50% (Weak)
    weak_areas = validator.detect_weak_areas(questions, answers)
    assert "business_rules" in weak_areas
    assert "state_transitions" in weak_areas

    # If state_transitions has 100% correct, it shouldn't be a weak area
    answers_strong = [
        {"question_id": "q1", "selected_index": 2, "confidence": "high"},
        {"question_id": "q2", "selected_index": 0, "confidence": "medium"},
        {"question_id": "q3", "selected_index": 1, "confidence": "high"},
        {"question_id": "q4", "selected_index": 2, "confidence": "high"} # Correct now
    ]
    weak_areas_strong = validator.detect_weak_areas(questions, answers_strong)
    assert "business_rules" in weak_areas_strong
    assert "state_transitions" not in weak_areas_strong


def test_validator_option_shuffling():
    options = ["Alpha", "Beta", "Gamma", "Delta"]
    correct_option = "Gamma"

    # Verify that option shuffling returns correct index mapping
    shuffled, correct_idx = validator.shuffle_question_options(options, correct_option)
    
    assert len(shuffled) == 4
    assert shuffled[correct_idx] == correct_option
    assert set(shuffled) == set(options)


def test_validator_question_normalization():
    # Normalize question key
    q1 = "What should the system do when the user requests an OTP?"
    q2 = "Which action occurs when a user requests an OTP?"
    
    # Check stop words are filtered and alphanumeric lowercased tokens remain
    norm1 = validator.normalize_question_key(q1)
    norm2 = validator.normalize_question_key(q2)
    
    assert "system" in norm1
    assert "user" in norm1
    assert "requests" in norm1
    assert "otp" in norm1
    assert "what" not in norm1
    assert "should" not in norm1
    assert "action" in norm2
    assert "occurs" in norm2
    assert "user" in norm2
    assert "requests" in norm2
    assert "otp" in norm2
    assert "which" not in norm2


def test_validator_parses_top_level_json_array():
    class FakeLLM:
        def _raw_chat(self, *args, **kwargs):
            return 'Here is the result: [{"category":"constraints","question":"Which limit applies to this operation?","options":["A","B","C","D"],"correct_option_text":"A"}]'

    parsed = validator.call_llm_json_with_repair(FakeLLM(), "system", "user")
    assert isinstance(parsed, list)
    assert parsed[0]["category"] == "constraints"


def test_lineage_identity_hashing():
    # API test case representation
    api_test = {
        "category": "api_tests",
        "method": "POST",
        "endpoint": "/api/v1/auth/otp",
        "status_code": "200",
        "intent": "Verify OTP request with valid phone number",
        "steps": [
            {"action": "Send POST request to /api/v1/auth/otp with body phone=123456", "expected": "Response returns 200 OK"},
            {"action": "Check response body contains session token", "expected": "Session token present"}
        ]
    }

    # Generate hash
    hash1 = lineage.generate_test_identity_hash(api_test)
    assert len(hash1) == 32  # MD5 hex length is 32

    # UI test case representation
    ui_test = {
        "category": "ui_validations",
        "field": "otp_input",
        "validation_type": "numeric_only",
        "screen": "OTP Verification Screen",
        "intent": "Ensure input accepts digits only"
    }
    
    hash2 = lineage.generate_test_identity_hash(ui_test)
    assert len(hash2) == 32
    assert hash1 != hash2


def test_lineage_keys_and_scenario_kinds():
    api_test_happy = {
        "category": "api_tests",
        "method": "POST",
        "endpoint": "/api/v1/auth/otp",
        "status_code": "200",
        "intent": "Verify successful login flow"
    }
    
    api_test_unauthorized = {
        "category": "api_tests",
        "method": "GET",
        "endpoint": "/api/v1/user/profile",
        "status_code": "401",
        "intent": "Retrieve profile without authentication token"
    }

    # Test lineage keys
    lk1 = lineage.generate_lineage_key(api_test_happy)
    lk2 = lineage.generate_lineage_key(api_test_unauthorized)
    
    assert lk1 == "api|POST|/api/v1/auth/otp|200"
    assert lk2 == "api|GET|/api/v1/user/profile|401"

    # Test scenario kinds
    kind1 = lineage.derive_scenario_kind(api_test_happy)
    kind2 = lineage.derive_scenario_kind(api_test_unauthorized)
    
    assert kind1 == "happy_path"
    assert kind2 == "unauthorized"


def test_prompt_builder_helpers():
    # Output contract header contains instruction
    header = prompt_builder.output_contract_header("Grounded Extraction")
    assert "Grounded Extraction" in header
    assert "Your entire response must be one valid JSON object" in header

    # Enum constraint formatting
    constraint = prompt_builder.enum_constraint("priority", ["P0", "P1", "P2"])
    assert "priority" in constraint
    assert "P0" in constraint
    assert "P1" in constraint
    assert "P2" in constraint


def test_prompt_builder_entity_hallucination_filtering():
    corpus = "the system integrates with otp authentication provider. users can input phone number to request a login session."
    
    entities = [
        {"name": "otp auth provider", "complexity": "low", "evidence_quote": "integrates with otp authentication provider"},
        {"name": "phone number input", "complexity": "low", "evidence_quote": "input phone number"},
        {"name": "postgresql", "complexity": "high", "evidence_quote": "using postgresql database"},  # deny-listed
        {"name": "redis", "complexity": "high", "evidence_quote": "using redis cache"},              # deny-listed
        {"name": "random entity without quote", "complexity": "medium"}                               # missing quote
    ]
    
    filtered = prompt_builder.filter_hallucinated_entities(entities, corpus)
    
    names = [e["name"] for e in filtered]
    assert "otp auth provider" in names
    assert "phone number input" in names
    assert "postgresql" not in names
    assert "redis" not in names
    assert "random entity without quote" not in names

def test_test_plan_emoji_stripping():
    text = "Hello ✅ World! ⚠️ Test ❌ Emoji 🔴🟡🟢"
    cleaned = test_plan.strip_emoji(text)
    assert "✅" not in cleaned
    assert "⚠️" not in cleaned
    assert "❌" not in cleaned
    assert "🔴" not in cleaned
    assert "🟡" not in cleaned
    assert "🟢" not in cleaned
    assert "Hello" in cleaned
    assert "World" in cleaned
    assert "Test" in cleaned
    assert "Emoji" in cleaned

if __name__ == "__main__":
    print("Running unit tests...", flush=True)
    test_validator_scoring_and_weak_areas()
    print("✓ test_validator_scoring_and_weak_areas passed", flush=True)
    test_validator_option_shuffling()
    print("✓ test_validator_option_shuffling passed", flush=True)
    test_validator_question_normalization()
    print("✓ test_validator_question_normalization passed", flush=True)
    test_validator_parses_top_level_json_array()
    print("✓ test_validator_parses_top_level_json_array passed", flush=True)
    test_lineage_identity_hashing()
    print("✓ test_lineage_identity_hashing passed", flush=True)
    test_lineage_keys_and_scenario_kinds()
    print("✓ test_lineage_keys_and_scenario_kinds passed", flush=True)
    test_prompt_builder_helpers()
    print("✓ test_prompt_builder_helpers passed", flush=True)
    test_prompt_builder_entity_hallucination_filtering()
    print("✓ test_prompt_builder_entity_hallucination_filtering passed", flush=True)
    test_test_plan_emoji_stripping()
    print("✓ test_test_plan_emoji_stripping passed", flush=True)
    print("All tests passed successfully!", flush=True)
