import { categoryLabel } from "../lib/validator.js";

export const QCARD =
  "mb-[18px] rounded-[10px] border border-solid border-line bg-panel2 px-5 py-[18px]";
export const CATEGORY =
  "mb-1.5 text-[10px] font-semibold uppercase tracking-[0.05em] text-accent";
export const QTEXT = "mb-3 text-[14px] font-semibold";

const OPT =
  "w-full cursor-pointer rounded-lg border border-solid px-3 py-2.5 text-left text-[12.5px] text-text transition-[border-color,background] duration-150";
const OPT_IDLE = "border-line bg-panel hover:border-accent hover:bg-panel2";
const OPT_SELECTED = "border-accent2 bg-[rgba(77,159,255,0.08)]";

const CONF =
  "flex h-[30px] w-[30px] cursor-pointer items-center justify-center rounded-md border border-solid text-[12px] transition-[background,color] duration-150";
const CONF_IDLE = "border-line bg-panel text-muted";
const CONF_SELECTED = "border-accent bg-accent font-semibold text-[#1a1205]";

function Question({ q, index, answer, onOption, onConfidence, onComment }) {
  return (
    <div className={QCARD}>
      <div className={CATEGORY}>{categoryLabel(q.category)}</div>
      <div className={QTEXT}>
        {index + 1}. {q.question}
      </div>
      <div className="mb-3 grid grid-cols-1 gap-2">
        {q.options.map((opt, i) => (
          <button
            key={i}
            type="button"
            aria-pressed={answer.selectedIndex === i}
            className={`${OPT} ${answer.selectedIndex === i ? OPT_SELECTED : OPT_IDLE}`}
            onClick={() => onOption(q.id, i)}
          >
            {opt}
          </button>
        ))}
      </div>
      <div className="mt-2.5 flex flex-wrap items-center justify-between gap-3">
        <div className="m-0 flex items-center gap-1.5">
          <span className="text-[12.5px] text-muted">Confidence:</span>
          {[1, 2, 3, 4, 5].map((lvl) => (
            <button
              key={lvl}
              type="button"
              aria-pressed={answer.confidence === lvl}
              className={`${CONF} ${answer.confidence === lvl ? CONF_SELECTED : CONF_IDLE}`}
              onClick={() => onConfidence(q.id, lvl)}
            >
              {lvl}
            </button>
          ))}
        </div>
        <div className="min-w-[180px] flex-1">
          <input
            aria-label={`Clarifying comment for question ${index + 1}`}
            placeholder="Clarifying comment (optional)…"
            value={answer.comment}
            onChange={(e) => onComment(q.id, e.target.value)}
            className="!px-2.5 !py-1.5 !text-[12.5px]"
          />
        </div>
      </div>
    </div>
  );
}

/** The question cards and the Submit button (compat renderValidatorQuestions). */
export default function ValidatorQuestions({
  questions,
  answers,
  submitting,
  selectOption,
  selectConfidence,
  setComment,
  submit,
}) {
  return (
    <>
      {questions.map((q, i) => (
        <Question
          key={q.id}
          q={q}
          index={i}
          answer={answers[q.id] || { selectedIndex: null, confidence: 3, comment: "" }}
          onOption={selectOption}
          onConfidence={selectConfidence}
          onComment={setComment}
        />
      ))}
      <button type="button" className="go mt-5 w-full" disabled={submitting} onClick={submit}>
        {submitting ? "Submitting..." : "Submit Answers"}
      </button>
    </>
  );
}
