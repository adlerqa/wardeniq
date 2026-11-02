"""Password-policy failure messages read as grammatical sentences (#173).

The password-change routes used to build the message as
`"Password must have " + ", ".join(errs) + "."`, which is ungrammatical
whenever the default-password rule is among the failures: a password that
fails only that rule produced "Password must have must not be the default
password." These tests pin the formatter the routes now use, including the
exact case from the issue.
"""

import auth


def test_single_default_rule_reads_grammatically():
    assert auth.password_policy_message(
        ["must not be the default password"]
    ) == "Password must not be the default password."


def test_issue_example_end_to_end():
    # admin123 fails only the default-password rule.
    errs = auth.password_policy_errors("admin123")
    assert errs == ["must not be the default password"]
    message = auth.password_policy_message(errs)
    assert message == "Password must not be the default password."
    assert "must have must" not in message


def test_two_rules_join_with_and():
    assert auth.password_policy_message(
        ["at least 8 characters", "must not be the default password"]
    ) == "Password must be at least 8 characters, and not be the default password."


def test_all_four_rules_join_with_commas_and_and():
    assert auth.password_policy_message(
        [
            "at least 8 characters",
            "at least one letter",
            "at least one number",
            "must not be the default password",
        ]
    ) == (
        "Password must be at least 8 characters, contain at least one letter, "
        "contain at least one number, and not be the default password."
    )


def test_fragments_unchanged_for_log_and_cli_consumers():
    # password_policy_errors() itself keeps returning bare fragments: the
    # bootstrap log and the reset CLI join them as lists, and only the
    # user-facing route message goes through the formatter.
    assert auth.password_policy_errors("short") == [
        "at least 8 characters",
        "at least one number",
    ]
