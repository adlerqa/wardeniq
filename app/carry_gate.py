"""A test carried over from another feature must be about THIS feature (#249 follow-up).

Why this exists. The Fusion step shows a model every test already in the project and asks
which ones the new feature can reuse. `INHERIT_EXACT` attached whatever the model named,
with no check at all. In a real run on a product-search feature (documents: Elasticsearch,
brand filters, sort, suggestions) nine Google-login tests from the project's Login feature
were attached to it, and they filled the feature's list next to its own seven tests.

Replaying the real Fusion step on the real documents with the project's 16 Login tests,
four models carried over 14 (qwen2.5:3b), 0 (qwen2.5:7b), 3 (gemma3:4b) and 8
(llama3.2:3b) of them; the correct answer is none. The prompt pushed them ("you MUST
inherit", "aim to inherit ~90%") and nothing in the code checked the choice.

A reused test only has meaning if the feature's own documents are about what the test
checks. That is something a program can check, so this module does, with plain text
comparison and no model call:

  * if the test names an endpoint and the feature's documents name endpoints, one of them
    must be the same endpoint (an API version difference, v1 vs v2, is a different one);
  * otherwise most of the test's content words, and at least two of them, must occur in
    the feature's documents.

Tests of the feature's own previous version are not checked: they are the same feature.
"""

import grounding
import hunk_evidence

MIN_SHARED_WORDS = 2
MIN_SUPPORT = 0.3          # share of the test's content words found in the feature's documents


def _case_for_endpoints(text: str) -> dict:
    return {"title": text, "steps": []}


def relevance_problem(case: dict, evidence_text: str) -> str | None:
    """None when the test is about this feature, else a short plain reason (logged)."""
    candidate_endpoints = grounding.case_endpoints(case)
    feature_endpoints = grounding.case_endpoints(_case_for_endpoints(evidence_text))
    if candidate_endpoints and feature_endpoints:
        if any(grounding.endpoints_align(c, f) in ("exact", "path")
               for c in candidate_endpoints for f in feature_endpoints):
            return None
        names = ", ".join(sorted({f"{c['method']} {c['path']}" for c in candidate_endpoints}))
        return f"it is about an endpoint this feature's documents do not have ({names})"
    words = hunk_evidence.case_words(case)
    if not words:
        return None                    # nothing to compare: do not block on it
    shared = words & hunk_evidence.code_words(evidence_text)
    if len(shared) < MIN_SHARED_WORDS or len(shared) / len(words) < MIN_SUPPORT:
        return (f"only {len(shared)} of its {len(words)} words occur in this feature's documents")
    return None
