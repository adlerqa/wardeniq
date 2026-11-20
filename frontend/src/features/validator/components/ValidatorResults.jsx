import { NO_WEAK_NOTE, WEAK_NOTE, resultsView } from "../lib/validator.js";
import { CATEGORY, QCARD, QTEXT } from "./ValidatorQuestions.jsx";

const H3 =
  "mt-5 [border-bottom:1px_solid_var(--line)] pb-1.5 text-[14px] text-accent";
const BADGE =
  "rounded-[20px] border border-solid border-transparent px-[11px] py-1 text-[10.5px] font-medium";

/**
 * Score tiles, weak areas and per-question results (compat
 * renderValidatorResults). The tiles keep the shared `kpis` / `kpi` classes
 * that the Gap Analysis screen also uses.
 */
export default function ValidatorResults({ score }) {
  const r = resultsView(score);
  return (
    <div>
      <div className="kpis mb-5">
        <div className="kpi">
          <div className="v accent">{r.clarity}</div>
          <div className="l">Clarity Score</div>
        </div>
        <div className="kpi">
          <div className={`v ${r.ratingOk ? "ok" : "err"}`}>{r.rating}</div>
          <div className="l">Rating</div>
        </div>
        <div className="kpi">
          <div className="v">{r.weakCount}</div>
          <div className="l">Weak Categories</div>
        </div>
      </div>
      <h3 className={H3}>Weak Requirement Areas</h3>
      <div className="my-2.5 text-[12px] text-muted">
        {r.weakAreas.length ? (
          <>
            {r.weakAreas.map((w, i) => (
              <span key={i} className={`${BADGE} mr-1.5 bg-white/[0.06] text-red`}>
                {w}
              </span>
            ))}
            <div className="mt-2 text-[12.5px] text-red">{WEAK_NOTE}</div>
          </>
        ) : (
          <>
            <span className={`${BADGE} bg-[rgba(52,211,153,0.16)] text-green`}>None</span>{" "}
            <span className="ml-1.5 text-[12px] text-muted">{NO_WEAK_NOTE}</span>
          </>
        )}
      </div>
      <h3 className={H3}>Detailed Question Results</h3>
      <div className="mt-2.5">
        {r.questions.map((q) => (
          <div
            key={q.key}
            className={`${QCARD} border-l-4 ${q.correct ? "border-l-green" : "border-l-red"}`}
          >
            <div className={CATEGORY}>{q.category}</div>
            <div className={QTEXT}>{q.text}</div>
            <div className="mb-1.5 text-[12.5px]">
              <b>Your Answer:</b>{" "}
              <span className={q.correct ? "text-green" : "text-red"}>{q.selected}</span>
              {!q.correct && (
                <>
                  <br />
                  <b>Correct Answer:</b> <span className="text-green">{q.correctOption}</span>
                </>
              )}
            </div>
            {q.comment && (
              <div className="mt-1.5 rounded-md bg-panel px-2.5 py-1.5 text-[12px] text-muted">
                <b>Note:</b> {q.comment}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
