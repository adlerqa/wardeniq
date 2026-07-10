"""Prompt templates for generating each test-case type from a requirement doc."""

SYSTEM = (
    "You are a meticulous senior QA engineer. You read software requirement documents "
    "(PRD/HLD/LLD) and produce thorough, concrete, non-redundant test cases. "
    "You ALWAYS respond with a single valid JSON object and nothing else."
)

# Each type gets tailored guidance.
TYPE_GUIDANCE = {
    "functional": (
        "Functional test cases: verify each individual requirement/behavior works as specified. "
        "Cover happy paths, validation rules, boundary values, and error handling for distinct functions."
    ),
    "e2e": (
        "End-to-end test cases covering complete user journeys. For each, make the focus explicit in "
        "tags using one of: 'ui-validation' (screen/field/UX checks), 'business-logic' (rules/calculations/"
        "state transitions), or 'cross-system' (integration across services/components). Steps should walk "
        "through a full flow from the user's perspective."
    ),
    "api": (
        "API test cases: verify endpoints/contracts. Cover request/response schemas, status codes, auth, "
        "validation errors, pagination/filtering, and idempotency where relevant. Reference endpoints, "
        "methods, and payloads concretely in the steps."
    ),
    "nfr": (
        "Non-functional test cases: performance/latency/throughput, scalability, security, reliability/"
        "failover, observability, and accessibility where applicable. Include measurable acceptance criteria."
    ),
}

OUTPUT_SHAPE = """
Return JSON of exactly this shape:
{
  "test_cases": [
    {
      "title": "short imperative title",
      "priority": "P1" | "P2" | "P3",
      "preconditions": "one line, or empty string",
      "tags": ["lowercase-tag", ...],
      "steps": [
        {"action": "what the tester/system does", "expected": "the expected result"}
      ]
    }
  ]
}
Rules:
- 3 to 8 test cases for this type (fewer if the requirement is small).
- 2 to 7 steps per case. Each step must have BOTH action and expected.
- Be specific to the requirement; do not invent unrelated features.
- Make steps atomic and reusable (one action + one verifiable expectation each).
"""


def build_prompt(test_type: str, requirement_text: str, target: int | None = None) -> str:
    guidance = TYPE_GUIDANCE[test_type]
    # keep the doc within a sane token budget for a 7B model
    doc = requirement_text[:8000]
    count_rule = (f"Generate approximately {target} {test_type.upper()} test cases"
                  if target else f"Generate {test_type.upper()} test cases")
    return (
        f"{guidance}\n\n"
        f"REQUIREMENT DOCUMENT:\n\"\"\"\n{doc}\n\"\"\"\n\n"
        f"{count_rule} for the above requirement.\n"
        f"{OUTPUT_SHAPE}"
    )
