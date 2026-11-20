import { useEffect, useRef } from "react";

import { SkeletonCards, SkeletonState } from "../../../components/feedback/Skeleton.jsx";
import ValidatorQuestions from "./ValidatorQuestions.jsx";
import ValidatorResults from "./ValidatorResults.jsx";

/**
 * MCQ Validator workspace card. Stays mounted (hidden when no feature is open)
 * and keeps the Generate and Retake buttons mounted, because the compat viewer
 * read-only pass (enforceViewerReadOnly in 10-auth.js) marks buttons in the
 * visible view by adding a class to them when the screen opens.
 */
export default function ValidatorWorkspace({ state, generate, retake, ...answering }) {
  const log = useRef(null);
  const logText = state.logLines.join("\n");
  useEffect(() => {
    if (log.current) log.current.scrollTop = log.current.scrollHeight;
  }, [logText, state.logVisible]);

  return (
    <div className="card" hidden={!state.hasFeature}>
      <div className="flex items-center justify-between">
        <h2>{state.title}</h2>
        <div className="flex gap-1.5">
          <button
            className="go"
            hidden={!state.generateVisible}
            disabled={state.generateDisabled}
            onClick={generate}
          >
            Generate Validator
          </button>
          <button
            className="ghost"
            hidden={!state.retakeVisible}
            disabled={state.retakeDisabled}
            onClick={retake}
          >
            ↻ Retake Validator
          </button>
        </div>
      </div>
      <div className="sub">
        Resolve requirement ambiguity, validate business intent, and detect gaps before QA begins.
      </div>
      {state.progressVisible && (
        <div className="mb-1 mt-2.5 h-2 overflow-hidden rounded-lg border border-solid border-line bg-panel2">
          {/* Width is the job's live percentage, so it stays an inline style. */}
          <div
            className="h-full rounded-lg bg-[linear-gradient(90deg,var(--accent),var(--accent2))] transition-[width] duration-300"
            style={{ width: `${state.barWidth}%` }}
          />
        </div>
      )}
      {state.logVisible && (
        <div ref={log} className="job-log !block">
          {logText}
        </div>
      )}
      <div className="mb-3 text-[12px] text-muted" aria-live="polite">
        {state.status.error ? (
          <span className="text-[12.5px] text-red">{state.status.text}</span>
        ) : (
          state.status.text
        )}
      </div>
      <div>
        {state.qa && state.qa.kind === "skeleton" && (
          <SkeletonState label={state.qa.label}>
            <SkeletonCards count={3} />
          </SkeletonState>
        )}
        {state.qa && state.qa.kind === "questions" && (
          <ValidatorQuestions
            questions={state.qa.questions}
            answers={state.answers}
            submitting={state.submitting}
            {...answering}
          />
        )}
      </div>
      {state.results && <ValidatorResults score={state.results} />}
    </div>
  );
}
