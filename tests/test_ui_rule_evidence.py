"""A UI validation must cite the numbered document lines that state its rule (#249 follow-up).

Found by running a real feature (e-commerce Product Search, qwen2.5:3b, three identical
PRD/HLD/LLD PDFs). The documents name a "Sort by" dropdown and "Multi-brand checkbox
filters" and state NO rule about either, yet three UI validations were kept:
"Sort by is required", "Other brands must be unchecked", "select at least one brand".
They passed because the field name was in the documents and because the grounding filter
accepts a case when ONE word of it appears anywhere. Replaying the prompt showed that the
cause is partly the model (every model tried, qwen2.5 3b and 7b, gemma3 4b, llama3.2 3b,
wrote rules the documents never state) and partly us: the prompt demanded at least 4 to 8
validations, its worked example (an "Event Title" field) leaked into answers, and the check
never looked at the rule.

How it works now, and what is pinned here:
  * the PROGRAM numbers the document lines ([E1] [E2] ...) and the prompt asks for the
    numbers of the lines that state a rule. Every model can cite a number; few can copy a
    sentence exactly
  * the check keeps a validation only when it cites real lines, those lines mention its
    field, contain its numbers, and contain nearly all the words of its intent
  * the invented rules above, with the citations models actually gave, are dropped
  * the prompt has no minimum, allows an empty answer, and its example is placeholders
  * through the real pipeline, a dropped case is counted under its own reason and a kept
    case stores the lines it cited
"""
import os
import sys

import pytest

APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../app"))
sys.path.insert(0, APP_DIR)

import testgen.service as svc  # noqa: E402
from testgen.prompt_builder import (  # noqa: E402
    EVIDENCE_LINE_CAP,
    REASON_UI_RULE_NOT_IN_DOCUMENTS,
    build_evidence_lines_block,
    build_repair_prompt,
    build_ui_agent_prompt,
    collect_evidence_lines,
)

# The relevant lines of the documents in the real run, as a PDF gives them: wrapped at the
# page width (the Sort-by sentence continues on the next line) with a bullet character.
SEARCH_DOC = """### Document: v2_advanced_search_HLD (1).pdf
E-Commerce Product Search
Version 2.0: Advanced Search
2. Features
\x7f Fuzzy matching for spell corrections, Auto-suggestions, Multi-brand checkbox filters, Sort by
price/relevance, Search history tracking.
3. API Endpoints
\x7f GET /api/v2/search?q=phone&brands;[]=Apple&brands;[]=Samsung&sort;=price&page;=1 and GET
/api/v2/suggest?q=pho returns 5 suggestions.
4. Database Schema
\x7f Redis for caching frequent queries.
7. Test Cases
\x7f TC-001: Type pho shows phone/photo suggestions.
\x7f TC-003: Multi-brand Apple+Samsung filter works.
\x7f TC-004: Sort by price changes order.
\x7f TC-005: Suggestions return in <100ms.
### Document: v2_advanced_search_LLD (1).pdf
E-Commerce Product Search
2. Features
\x7f Fuzzy matching for spell corrections, Auto-suggestions, Multi-brand checkbox filters, Sort by
price/relevance, Search history tracking.
"""

LINES = collect_evidence_lines([SEARCH_DOC])
BY_ID = {line["id"]: line["text"] for line in LINES}


def eid(phrase):
    """The number of the evidence line that contains `phrase`."""
    found = [line["id"] for line in LINES if phrase in line["text"]]
    assert len(found) == 1, f"{phrase!r} matches {found}"
    return found[0]


def check(case):
    return svc._ui_rule_evidence_problem(case, BY_ID)


def keep(cases, lines=LINES):
    return svc._filter_ui_rules_with_reasons(cases, lines)


# ------------------------------------------------------------------ the numbered lines
class TestEvidenceLines:
    def test_lines_are_numbered_in_document_order(self):
        assert [line["id"] for line in LINES] == [f"E{n}" for n in range(1, len(LINES) + 1)]
        assert LINES[0]["text"] == "E-Commerce Product Search"
        texts = [line["text"] for line in LINES]
        assert texts.index("TC-001: Type pho shows phone/photo suggestions.") < texts.index("TC-004: Sort by price changes order.")

    def test_a_sentence_wrapped_over_two_lines_is_one_line(self):
        line = BY_ID[eid("Sort by price/relevance")]
        assert line.startswith("Fuzzy matching") and line.endswith("Search history tracking.")

    def test_each_bullet_is_its_own_line(self):
        assert BY_ID[eid("TC-003")] == "TC-003: Multi-brand Apple+Samsung filter works."
        assert BY_ID[eid("TC-004")] == "TC-004: Sort by price changes order."

    def test_headings_and_document_headers_are_not_evidence(self):
        texts = " | ".join(BY_ID.values())
        assert "### Document" not in texts
        assert "2. Features" not in texts and "Database Schema" not in texts

    def test_the_same_text_in_several_documents_is_one_line(self):
        # HLD, LLD and PRD were identical in the real run
        assert sum("Multi-brand checkbox filters" in text for text in BY_ID.values()) == 1

    def test_the_bullet_character_is_removed(self):
        assert not any("\x7f" in text for text in BY_ID.values())

    def test_a_design_files_text_leaves_become_lines(self):
        figma = {"screens": [{"name": "Search", "notes": ["The Quantity field accepts at most 10 units."]}]}
        lines = collect_evidence_lines([figma])
        assert [line["text"] for line in lines] == ["The Quantity field accepts at most 10 units."]

    def test_empty_sources_give_no_lines(self):
        assert collect_evidence_lines([None, "", {}, []]) == []

    def test_a_long_line_is_cut_at_a_word(self):
        lines = collect_evidence_lines(["word " * 200])
        assert len(lines[0]["text"]) <= 300 and not lines[0]["text"].endswith(" ")

    def test_over_the_cap_lines_that_can_state_a_rule_are_kept_first(self):
        filler = [f"Plain narrative sentence number {i} about nothing in particular." for i in range(EVIDENCE_LINE_CAP + 20)]
        rule = "The Quantity field must be a positive integer."
        lines = collect_evidence_lines(["\n".join([*filler[:70], rule, *filler[70:]])])
        assert len(lines) == EVIDENCE_LINE_CAP
        assert rule in [line["text"] for line in lines]

    def test_the_block_shows_the_numbers(self):
        block = build_evidence_lines_block(LINES)
        assert f"[{eid('TC-004')}] TC-004: Sort by price changes order." in block
        assert "numbered by the program" in block
        assert build_evidence_lines_block([]) == "EVIDENCE LINES: none."


# ------------------------------------------------------------------ the prompts
def ui_prompt(lines=LINES, **ctx):
    context = {"featureName": "Product Search", "featureDescription": "",
               "summaries": {"prd": SEARCH_DOC, "hld": "", "figma": {}}, "flags": ctx.pop("flags", {}),
               "graphContext": {}}
    return build_ui_agent_prompt(context, ctx.pop("chunk", []), {}, top_k=4, evidence_lines=lines)["messages"][1]["content"]


class TestUiPrompt:
    def test_there_is_no_minimum_and_empty_is_allowed(self):
        p = ui_prompt()
        assert "Generate at least" not in p
        assert "NO minimum" in p
        assert '{"ui_validations": []}' in p and "correct answer" in p

    @pytest.mark.parametrize("flags,chunk", [
        ({}, []), ({"smokeMode": True}, []), ({}, [{"field": "Search", "type": "input"}]),
    ])
    def test_no_minimum_in_any_mode(self, flags, chunk):
        assert "Generate at least" not in ui_prompt(flags=flags, chunk=chunk)

    def test_the_maximum_is_kept(self):
        assert "Output at most" in ui_prompt()

    def test_the_prompt_shows_the_numbered_lines_and_asks_for_citations(self):
        p = ui_prompt()
        assert f"[{eid('TC-004')}] TC-004: Sort by price changes order." in p
        assert 'The "evidence" value is a list of 1 to 3 evidence line numbers' in p
        assert '"evidence": ["E<line number>"]' in p

    def test_the_example_is_placeholders_not_a_domain(self):
        p = ui_prompt()
        assert "Event Title" not in p and "5 and 100 characters" not in p
        assert "<exact label of the control" in p and "<the rule, in the words" in p

    def test_no_evidence_still_means_an_empty_list(self):
        context = {"featureName": "X", "summaries": {"prd": "", "hld": "", "figma": {}}, "flags": {},
                   "graphContext": {}}
        p = build_ui_agent_prompt(context, [], {}, top_k=4)["messages"][1]["content"]
        assert 'Output exactly {"ui_validations":[]}' in p
        assert "EVIDENCE LINES: none." in p

    def test_the_repair_prompt_shows_the_lines_and_asks_ui_additions_to_cite(self):
        p = build_repair_prompt({"unifiedContext": {"summaries": {"prd": SEARCH_DOC}}, "evidenceLines": LINES})
        assert f"[{eid('TC-004')}] TC-004: Sort by price changes order." in p
        assert 'ui_validations_delta must have an "evidence" list' in p


# ------------------------------------------------------------------ the check
def case(field, intent, cites, **extra):
    return {"field": field, "intent": intent, "evidence": cites, "validation_type": "state", **extra}


class TestTheRealRunsInventedRules:
    """What the models wrote for these documents, with the lines they cited."""

    SORT_REQUIRED = case(  # qwen2.5:3b, citing the line that only names Sort by
        "Sort By", "Sorting by price or relevance must be selected for a search.",
        [eid("Sort by price/relevance")], validation_type="required",
        expected_behavior="The message 'Sort by is required' is shown.")
    OTHER_BRANDS = case(
        "Multi-Brand Filter - Other Brands", "The multi-brand filter for other brands must be unchecked to apply the filter.",
        [eid("Multi-brand checkbox filters")], validation_type="required")
    SELECT_A_BRAND = case(  # qwen2.5:3b and llama3.2:3b
        "Brand Filter", "At least one brand filter must be selected to trigger the search results.",
        [eid("Multi-brand checkbox filters")], validation_type="required")
    RESPONSE_TIME = case(  # llama3.2:3b, citing a line about something else
        "Response Time", "The response time must be less than 500ms to trigger the search results.",
        [eid("TC-005")])
    PLACEHOLDER = case(  # gemma3:4b copied the placeholders of the example
        "<exact label of the control, as written in the evidence>", "<the rule, in the words of the cited evidence line>",
        [eid("TC-004")])

    @pytest.mark.parametrize("name", ["SORT_REQUIRED", "OTHER_BRANDS", "SELECT_A_BRAND", "RESPONSE_TIME", "PLACEHOLDER"])
    def test_each_invented_rule_is_dropped(self, name):
        kept, rejected = keep([getattr(self, name)])
        assert kept == []
        assert [reason for _, reason in rejected] == [REASON_UI_RULE_NOT_IN_DOCUMENTS]

    def test_the_reasons_are_the_right_ones(self):
        assert check(self.SORT_REQUIRED) == "the cited lines do not state this rule"
        assert check(self.RESPONSE_TIME) == "the cited lines do not mention the field"
        assert check(self.PLACEHOLDER) == "the cited lines do not mention the field"

    def test_rules_the_documents_do_state_are_kept(self):
        # qwen2.5:7b, citing the test-case lines of the document
        sorting = case("Sort by Price", "Sort by price changes the order of the results.", [eid("TC-004")])
        multi = case("Multi-brand filter", "The Multi-brand Apple and Samsung filter works.", [eid("TC-003")])
        suggest = case("Suggestions", "Typing pho shows phone and photo suggestions.", [eid("TC-001")])
        kept, rejected = keep([sorting, multi, suggest])
        assert kept == [sorting, multi, suggest] and rejected == []

    def test_only_the_supported_ones_survive_a_mixed_batch(self):
        good = case("Sort by Price", "Sort by price changes the order of the results.", [eid("TC-004")])
        kept, rejected = keep([self.SORT_REQUIRED, good, self.OTHER_BRANDS, self.PLACEHOLDER])
        assert kept == [good] and len(rejected) == 3


class TestWhatTheCheckRequires:
    GOOD = case("Sort by Price", "Sort by price changes the order of the results.", ["E1"])

    def _lines(self):
        return {"E1": "TC-004: Sort by price changes order.", "E2": "Redis for caching frequent queries."}

    def problem(self, **change):
        return svc._ui_rule_evidence_problem({**self.GOOD, **change}, self._lines())

    def test_the_good_case_passes(self):
        assert self.problem() is None

    @pytest.mark.parametrize("value", [None, [], "", "none", ["nothing"]])
    def test_no_citation_is_dropped(self, value):
        assert self.problem(evidence=value) == "no evidence cited"

    def test_citing_a_line_that_does_not_exist_is_dropped(self):
        assert self.problem(evidence=["E1", "E99"]) == "cites a line that does not exist: E99"

    @pytest.mark.parametrize("value", ["E1", "e1", 1, "1", " E 1 ", ["E1"], ["e1"], [1], "E1, E1"])
    def test_citation_formats_models_use_are_understood(self, value):
        assert self.problem(evidence=value) is None

    def test_at_most_three_citations_count(self):
        lines = {**self._lines(), "E3": "Another line about nothing relevant here.", "E4": "Yet another line, also unrelated."}
        good = {**self.GOOD}
        # the line that backs the rule is cited third: counted; cited fourth: ignored
        assert svc._ui_rule_evidence_problem({**good, "evidence": ["E2", "E3", "E1", "E4"]}, lines) is None
        assert svc._ui_rule_evidence_problem({**good, "evidence": ["E2", "E3", "E4", "E1"]}, lines) \
            == "the cited lines do not mention the field"

    def test_a_true_line_about_another_field_cannot_back_a_rule(self):
        assert self.problem(evidence=["E2"]) == "the cited lines do not mention the field"

    def test_a_number_the_cited_lines_do_not_contain_is_dropped(self):
        assert self.problem(intent="Sort by price lists at most 7 options.") == "number not in the cited lines: 7"

    def test_a_number_in_expected_behaviour_counts_too(self):
        assert self.problem(expected_behavior="Shows 12 results.") == "number not in the cited lines: 12"

    def test_a_number_the_cited_lines_contain_is_kept(self):
        lines = {"E1": "The search box accepts at most 100 characters."}
        c = case("Search box", "The search box takes at most 100 characters.", ["E1"],
                 expected_behavior="More than 100 characters is cut off.")
        assert svc._ui_rule_evidence_problem(c, lines) is None

    def test_a_decimal_is_compared_by_its_digits(self):
        lines = {"E1": "Ratings accept a value up to 4.5 stars."}
        c = case("Rating", "Rating accepts up to 4.5 stars.", ["E1"])
        assert svc._ui_rule_evidence_problem(c, lines) is None

    def test_a_line_that_only_names_the_field_does_not_state_a_rule(self):
        c = case("Sort by", "Sort by must have at least one selected option to apply sorting.", ["E1"])
        assert svc._ui_rule_evidence_problem(c, {"E1": "Sort by price/relevance"}) == \
            "the cited lines do not state this rule"

    def test_a_paraphrase_that_keeps_most_words_is_kept(self):
        lines = {"E1": "The Minimum price must not be greater than the Maximum price."}
        c = case("Minimum price", "Minimum price must never be greater than the maximum price.", ["E1"])
        assert svc._ui_rule_evidence_problem(c, lines) is None

    def test_plurals_and_case_do_not_matter(self):
        lines = {"E1": "MULTI-BRAND CHECKBOX FILTERS are shown on the page."}
        c = case("Brand filter", "Multi-brand checkbox filter is shown.", ["E1"])
        assert svc._ui_rule_evidence_problem(c, lines) is None

    def test_the_field_may_be_called_element(self):
        c = {"element": "Sort by Price", "intent": "Sort by price changes the order of the results.", "evidence": ["E1"]}
        assert svc._ui_rule_evidence_problem(c, self._lines()) is None

    def test_non_dict_entries_are_ignored_not_raised(self):
        assert keep([None, "text", 3]) == ([], [])

    def test_no_documents_means_nothing_is_kept(self):
        assert keep([self.GOOD], [])[0] == []

    def test_angle_brackets_a_model_puts_around_a_real_label_are_removed_from_the_kept_case(self):
        c = case("<Sort by Price>", "Sort by price changes the order of the results.", ["E1"])
        kept, _ = svc._filter_ui_rules_with_reasons(
            [c], [{"id": "E1", "text": "TC-004: Sort by price changes order."}]
        )
        assert kept[0]["field"] == "Sort by Price"


# ------------------------------------------------------------------ the real pipeline
class TestPipeline:
    def _run(self, ui_cases):
        from tests.test_generation_pipeline import FakeEmbedder, FakeLLM, FakeStore, ui_cases_with_citations

        class UiLLM(FakeLLM):
            def __init__(self):
                self.prompts = []

            def chat_json(self, system, user, **kwargs):
                if "Generate UI validations" in user:
                    self.prompts.append(user)
                    return {"ui_validations": ui_cases_with_citations(user, ui_cases)}
                return super().chat_json(system, user, **kwargs)

        llm, store = UiLLM(), FakeStore()
        result = svc.generate_fresh_testcases_pipeline(
            store, llm, FakeEmbedder(),
            {"feature_id": "feature-1", "total": 10,
             "focus": {"functional": 0, "e2e": 0, "api": 50, "nfr": 0, "ui": 100}},
        )
        return store, result, llm

    GOOD = {"title": "Quantity must be a positive integer", "field": "Quantity", "validation_type": "format",
            "intent": "The Quantity field must be a positive integer.", "cite": "Quantity field",
            "steps": [{"content": "Enter -3 in Quantity", "expectedResult": "The value is rejected"}]}
    INVENTED = {"title": "Quantity accepts only whole numbers above zero", "field": "Quantity",
                "validation_type": "state", "intent": "Quantity may only contain whole numbers above zero.",
                "cite": "Quantity field",
                "steps": [{"content": "Enter 1.5 in Quantity", "expectedResult": "The value is rejected"}]}
    NO_CITATION = {"title": "Quantity cannot be left blank", "field": "Quantity", "validation_type": "required",
                   "intent": "Quantity cannot be left blank.",
                   "steps": [{"content": "Leave Quantity empty", "expectedResult": "Submission is blocked"}]}

    def test_only_the_cited_rule_is_persisted(self):
        store, _, _ = self._run([self.GOOD, self.INVENTED, self.NO_CITATION])
        titles = {case["title"] for case in store.created}
        assert self.GOOD["title"] in titles
        assert self.INVENTED["title"] not in titles
        assert self.NO_CITATION["title"] not in titles

    def test_the_dropped_cases_are_counted_under_their_own_reason(self):
        _, result, _ = self._run([self.GOOD, self.INVENTED, self.NO_CITATION])
        assert result["testgen_filter"]["rejected_by_reason"].get(REASON_UI_RULE_NOT_IN_DOCUMENTS) == 2

    def test_the_ui_prompt_carries_the_numbered_documents(self):
        _, _, llm = self._run([self.GOOD])
        assert llm.prompts, "the UI worker did not run"
        assert "EVIDENCE LINES (numbered by the program" in llm.prompts[0]
        assert "Quantity field that must be a positive integer" in llm.prompts[0]

    def test_the_cited_line_numbers_are_stored_with_the_kept_case(self):
        store, _, _ = self._run([self.GOOD])
        kept = next(case for case in store.created if case["title"] == self.GOOD["title"])
        cited = kept["metadata"]["evidence"]
        assert len(cited) == 1 and cited[0].startswith("E")
