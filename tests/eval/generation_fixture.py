"""Initial fixed corpus and requirement labels for the generation evaluation (issue #43).

ONE document, deliberately: examples/sample-prd.md, the same simple password-reset PRD the
issue describes. It is the first fixed corpus, NOT a representative benchmark; results on it
say nothing about other kinds of documents.

Each requirement carries:
  excerpt       a verbatim fragment of the PRD (a test checks it really is in the file, so a
                reviewer can audit every label against the source)
  must_mention  groups of alternative lower-case phrases. A persisted case "covers" the
                requirement when, for every group, at least one phrase appears in the case's
                title / preconditions / steps. This is a keyword heuristic written by hand
                for review; it does not judge whether a case is correct.

Changing the PRD or any label changes what is being measured, so the runner records the
sha256 of both the corpus and this fixture in every result.
"""
import hashlib
import json

CORPUS_PATH = "examples/sample-prd.md"
FEATURE_NAME = "Self-Service Password Reset"

REQUIREMENTS = [
    {"id": "FR-1",
     "excerpt": 'On the sign-in screen, a "Forgot password?" link takes the user to a password reset request form.',
     "must_mention": [["forgot password"]]},
    {"id": "FR-2",
     "excerpt": "sends a password reset email to that address if an account with that email exists.",
     "must_mention": [["email"], ["reset email", "reset link", "sends", "sent", "send"]]},
    {"id": "FR-3",
     "excerpt": "The response to a reset request is identical regardless of whether the email address is registered",
     "must_mention": [["identical", "same message", "same response", "generic", "regardless",
                       "not reveal", "does not reveal", "enumerat"]]},
    {"id": "FR-4",
     "excerpt": 'The reset email contains a single-use link containing a reset token.',
     "must_mention": [["token", "single-use", "single use"], ["link", "set a new password"]]},
    {"id": "FR-5",
     "excerpt": "The new password must be at least 12 characters and contain at least one letter and one number.",
     "must_mention": [["12"], ["letter", "number", "digit", "character"]]},
    {"id": "FR-6",
     "excerpt": "invalidates the reset token, updates the stored password, and signs the user out of all other active sessions.",
     "must_mention": [["session", "signed out", "sign out", "signs out", "logged out"]]},
    {"id": "FR-7",
     "excerpt": "After a successful reset, the user is redirected to the sign-in screen with a confirmation message",
     "must_mention": [["redirect", "confirmation message"], ["sign-in", "sign in", "login"]]},
    {"id": "NFR-1",
     "excerpt": "A reset token expires 30 minutes after it is issued.",
     "must_mention": [["expire", "expiry", "30 minute", "30 min"]]},
    {"id": "NFR-2",
     "excerpt": "A single email address may not request more than 4 password resets within a 30-minute window",
     "must_mention": [["rate limit", "rate-limit", "throttl", "fifth", "5th", "more than 4",
                       "4 request", "four"]]},
    {"id": "NFR-3",
     "excerpt": "Reset tokens are single-use",
     "must_mention": [["single-use", "single use", "twice", "second attempt", "reuse",
                       "already used", "used"]]},
    {"id": "NFR-4",
     "excerpt": "Password reset requests and completions are written to the audit log",
     "must_mention": [["audit"]]},
]


def fixture_hash() -> str:
    """sha256 of the labels, so a changed label is visible in the recorded results."""
    return hashlib.sha256(json.dumps(REQUIREMENTS, sort_keys=True).encode()).hexdigest()
