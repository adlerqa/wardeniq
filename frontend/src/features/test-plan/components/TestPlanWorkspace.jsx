import { SkeletonLines, SkeletonState } from "../../../components/feedback/Skeleton.jsx";
import { exportUrls } from "../lib/testPlan.js";
import TestPlanContent from "./TestPlanContent.jsx";

const BAR_WIDTH = { 20: "w-[20%]", 30: "w-[30%]", 60: "w-[60%]" };

/**
 * Test Plan workspace card. Stays mounted (hidden when no feature is open) and
 * keeps the Generate button mounted, because the compat viewer read-only pass
 * (enforceViewerReadOnly in 10-auth.js) marks buttons in the visible view by
 * adding a class to them when the screen opens.
 */
export default function TestPlanWorkspace({ state, onGenerate }) {
  const { content } = state;
  const urls = state.exportRunId ? exportUrls(state.exportRunId) : null;
  return (
    <div className="card" hidden={!state.hasFeature}>
      <div className="flex items-center justify-between">
        <h2>{state.title}</h2>
        <div className="flex gap-1.5">
          <button
            className="go"
            hidden={!state.generateVisible}
            disabled={state.generateDisabled}
            onClick={onGenerate}
          >
            Generate Test Plan
          </button>
          {urls && (
            <>
              <a className="ghost inline-block no-underline" href={urls.csv}>
                Export CSV
              </a>
              <a className="ghost inline-block no-underline" href={urls.pdf}>
                Export PDF
              </a>
            </>
          )}
        </div>
      </div>
      <div className="sub">
        Comprehensive feature-specific QA test plan, generated dynamically from requirements.
      </div>
      {state.progress != null && (
        <div className="mb-1 mt-2.5 h-2 overflow-hidden rounded-lg border border-solid border-line bg-panel2">
          <div
            className={`h-full rounded-lg bg-[linear-gradient(90deg,var(--accent),var(--accent2))] transition-[width] duration-300 ${BAR_WIDTH[state.progress]}`}
          />
        </div>
      )}
      <div className="mb-3 text-xs text-muted" aria-live="polite">
        {state.status.error ? (
          <span className="text-[12.5px] text-red">{state.status.text}</span>
        ) : (
          state.status.text
        )}
      </div>
      {content && (
        <div
          className={`mt-[15px] max-h-[600px] overflow-y-auto whitespace-pre-wrap rounded-lg border border-solid border-line bg-panel2 p-4 text-xs leading-[1.6] text-text ${
            state.mono ? "font-[monospace]" : "[font-family:inherit]"
          }`}
        >
          {content.kind === "skeleton" ? (
            <SkeletonState label={content.label}>
              <div className="grid gap-[18px]">
                {content.blocks.map((n, i) => (
                  <SkeletonLines key={i} count={n} />
                ))}
              </div>
            </SkeletonState>
          ) : (
            <TestPlanContent plan={content.plan} />
          )}
        </div>
      )}
    </div>
  );
}
