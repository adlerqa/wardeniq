import { SkeletonBlockLines, SkeletonState } from "../../../components/feedback/Skeleton.jsx";
import { NO_CASES, NO_EXPECTED, stepBase, stepType, typeLabel } from "../lib/steps.js";

const BADGE = {
  given: "border-[rgba(188,140,255,0.25)] bg-[rgba(188,140,255,0.15)] text-[#d1b3ff]",
  when: "border-[rgba(246,166,35,0.25)] bg-[rgba(246,166,35,0.15)] text-[#ffca7b]",
  then: "border-[rgba(52,211,153,0.25)] bg-[rgba(52,211,153,0.15)] text-[#a7f3d0]",
  and: "border-[rgba(88,166,255,0.25)] bg-[rgba(88,166,255,0.15)] text-[#a5d6ff]",
  other: "border-[rgba(138,151,168,0.25)] bg-[rgba(138,151,168,0.15)] text-[#cbd5e1]",
};
const SECTION_LABEL = "block text-[9.5px] font-semibold uppercase tracking-[0.1em] text-slate-600";

/** Detail drawer for the selected step: type, text, expected result and the cases using it. */
export default function StepDetailPane({ step, detail, onClose, onOpenCase }) {
  const type = stepType(step.action);
  return (
    <aside className="flex w-[360px] shrink-0 flex-col overflow-hidden rounded-xl border border-slate-800 bg-[#0D151F] max-[1100px]:w-[320px]">
      <div className="flex min-h-[60px] items-center justify-between border-b border-slate-800 px-5">
        <div>
          <div className="text-[10px] font-medium uppercase tracking-[0.1em] text-slate-600">
            Selected step
          </div>
          <h3 className="mt-0.5 text-[14px] font-semibold text-slate-200">Step details</h3>
        </div>
        <button
          className="ghost !flex !h-8 !w-8 !items-center !justify-center !rounded-lg !border !border-transparent !bg-transparent !p-0 !text-slate-500 transition-all hover:!border-slate-700 hover:!bg-slate-800 hover:!text-slate-200"
          type="button"
          title="Close details"
          aria-label="Close step details"
          onClick={onClose}
        >
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
            <path d="M18 6 6 18" />
            <path d="m6 6 12 12" />
          </svg>
        </button>
      </div>

      <div className="flex flex-1 flex-col gap-6 p-5">
        <div>
          <span className={SECTION_LABEL}>Type</span>
          <div className="mt-2">
            <span
              className={`inline-block rounded border border-solid px-2 py-[3px] text-[10px] font-bold uppercase tracking-[0.05em] ${BADGE[type]}`}
            >
              {typeLabel(type)}
            </span>
          </div>
        </div>
        <div>
          <span className={SECTION_LABEL}>Action / Description</span>
          <div className="mt-2 break-words text-[13px] font-medium leading-5 text-slate-200">
            {stepBase(step.action)}
          </div>
        </div>
        <div>
          <span className={SECTION_LABEL}>Expected result</span>
          <div className="mt-2 break-words text-[12px] leading-5 text-slate-400">
            {step.expected || NO_EXPECTED}
          </div>
        </div>
        <div className="border-t border-slate-800 pt-5">
          <div className="flex items-center gap-2 text-[11px] font-semibold text-slate-400">
            {detail.title}
          </div>
          <div className="mt-3 flex max-h-[320px] flex-col gap-2 overflow-y-auto">
            {detail.status === "loading" && (
              <SkeletonState label="Loading cases…">
                <SkeletonBlockLines count={3} />
              </SkeletonState>
            )}
            {detail.status === "error" && (
              <span className="mt-2 text-[12px] text-red">{detail.error}</span>
            )}
            {detail.status === "ready" &&
              (detail.cases.length ? (
                detail.cases.map((c) => (
                  <div
                    key={c.id}
                    className="flex items-center justify-between gap-2.5 rounded-md border border-solid border-[#1E2A40] bg-white/[0.02] px-2 py-1.5 text-[12.5px]"
                  >
                    <span className="font-medium text-[#e2e8f0]">
                      {c.display_id && (
                        <code className="mr-1.5 rounded-[3px] border border-solid border-line bg-white/[0.06] px-[5px] py-px text-[10.5px] text-[#94a3b8]">
                          {c.display_id}
                        </code>
                      )}
                      {c.title}
                    </span>
                    <button
                      type="button"
                      className="ghost !px-1.5 !py-0.5 !text-[11px]"
                      onClick={() => onOpenCase(c.id, c.feature_id)}
                    >
                      Open ↗
                    </button>
                  </div>
                ))
              ) : (
                <span className="text-[12px] text-muted">{NO_CASES}</span>
              ))}
          </div>
        </div>
      </div>
    </aside>
  );
}
