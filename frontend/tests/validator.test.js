import assert from "node:assert/strict";
import test from "node:test";

import {
  categoryLabel,
  hasUnanswered,
  initialAnswers,
  jobLogLines,
  resultsView,
  submitPayload,
} from "../src/features/validator/lib/validator.js";

test("category label replaces only the first underscore, like the compat code", () => {
  assert.equal(categoryLabel("business_rules"), "business rules");
  assert.equal(categoryLabel("edge_case_rules"), "edge case_rules");
  assert.equal(categoryLabel(undefined), "");
});

test("initial answers: saved answers first, defaults for the rest", () => {
  const answers = initialAnswers(
    [{ id: "q1" }, { id: "q2" }],
    [{ question_id: "q1", selected_index: 2, confidence: 5, comment: null }],
  );
  assert.deepEqual(answers, {
    q1: { selectedIndex: 2, confidence: 5, comment: "" },
    q2: { selectedIndex: null, confidence: 3, comment: "" },
  });
  assert.equal(hasUnanswered(answers), true);
  answers.q2.selectedIndex = 0;
  assert.equal(hasUnanswered(answers), false);
});

test("submit payload", () => {
  assert.deepEqual(
    submitPayload({ q1: { selectedIndex: 1, confidence: 4, comment: "x" } }),
    { answers: [{ questionId: "q1", selectedIndex: 1, confidence: 4, comment: "x" }] },
  );
});

test("results view", () => {
  const r = resultsView({
    clarityScore: 38,
    rating: "Poor",
    weakAreas: ["data_validation"],
    questionResults: [
      { category: "business_rules", question: "Q?", isCorrect: true, selectedOption: "A", comment: "n" },
      { category: "edge_cases", question: "R?", isCorrect: false, selectedOption: null, correctOption: "B" },
    ],
  });
  assert.equal(r.clarity, "38%");
  assert.equal(r.ratingOk, false);
  assert.equal(r.weakCount, 1);
  assert.deepEqual(r.weakAreas, ["data validation"]);
  assert.equal(r.questions[0].text, "1. Q?");
  assert.equal(r.questions[0].comment, "n");
  assert.equal(r.questions[1].selected, "unanswered");
  assert.equal(r.questions[1].correctOption, "B");
  assert.equal(resultsView({ clarityScore: 75, weakAreas: [] }).ratingOk, true);
});

test("job log lines match the compat renderJobLog", () => {
  const lines = jobLogLines(
    { logs: [{ progress: 0, stage: "starting" }, { progress: 40, stage: "Generating" }, { stage: "x" }], error: "boom" },
    () => ["", "TOTAL"],
  );
  assert.deepEqual(lines, ["  0%  starting", " 40%  Generating", "     x", "ERR  boom", "", "TOTAL"]);
  assert.deepEqual(jobLogLines({}), []);
});
