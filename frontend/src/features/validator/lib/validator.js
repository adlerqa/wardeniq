/**
 * Pure logic for the MCQ Validator screen (ported from the compat
 * 12-validator.js). Unit-tested in frontend/tests/validator.test.js.
 */

export const MSG_ANSWER_ALL = "Please answer all questions before submitting.";
export const RETAKE_CONFIRM =
  "Are you sure you want to retake the validator? This will generate completely fresh questions.";
export const WEAK_NOTE =
  "These categories scored below 60% accuracy, indicating requirement gaps.";
export const NO_WEAK_NOTE = "Strong requirement clarity across all categories.";

/** Category label: the first "_" becomes a space (same as the compat code). */
export function categoryLabel(category) {
  return (category ?? "").toString().replace("_", " ");
}

/**
 * Answers keyed by question id: saved answers from the server first, then a
 * default (no option, confidence 3, no comment) for every question without one.
 */
export function initialAnswers(questions, saved) {
  const answers = {};
  for (const a of saved || []) {
    answers[a.question_id] = {
      selectedIndex: a.selected_index,
      confidence: a.confidence,
      comment: a.comment || "",
    };
  }
  for (const q of questions || []) {
    answers[q.id] = answers[q.id] || { selectedIndex: null, confidence: 3, comment: "" };
  }
  return answers;
}

/** True when any answer still has no option selected. */
export function hasUnanswered(answers) {
  return Object.values(answers).some((a) => a.selectedIndex === null || a.selectedIndex === undefined);
}

/** Body for POST /api/validator/runs/{id}/submit. */
export function submitPayload(answers) {
  return {
    answers: Object.keys(answers).map((id) => ({
      questionId: id,
      selectedIndex: answers[id].selectedIndex,
      confidence: answers[id].confidence,
      comment: answers[id].comment,
    })),
  };
}

/** Score tiles and lists for the results view. */
export function resultsView(score) {
  return {
    clarity: `${score.clarityScore}%`,
    rating: score.rating,
    ratingOk: score.clarityScore >= 75,
    weakCount: score.weakAreas.length,
    weakAreas: score.weakAreas.map(categoryLabel),
    questions: (score.questionResults || []).map((q, i) => ({
      key: q.questionId || q.id || i,
      category: categoryLabel(q.category),
      text: `${i + 1}. ${q.question}`,
      correct: !!q.isCorrect,
      selected: q.selectedOption || "unanswered",
      correctOption: q.correctOption,
      comment: q.comment || "",
    })),
  };
}

/** Lines of the job log (lib/jobs.js). */
export { jobLogLines } from "../../../lib/jobs.js";
