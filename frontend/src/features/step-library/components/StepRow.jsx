import { stepLine, usagePill } from "../lib/steps.js";

const KW_COLOR = { given: "text-[#a78bfa]", when: "text-[#fbbf24]", then: "text-[#34d399]" };

const ROW =
  "group relative flex min-h-[78px] cursor-pointer items-center justify-between gap-6 [border-bottom:1px_solid_rgba(148,163,184,0.08)] px-[18px] py-[14px] transition-[background-color,box-shadow] duration-[140ms] ease-[ease] last:[border-bottom:0] max-[800px]:items-start max-[800px]:gap-3 max-[800px]:p-[14px]";
const ROW_IDLE = "bg-transparent hover:bg-white/[0.018]";
const ROW_SELECTED = "bg-[rgba(34,211,238,0.045)] [box-shadow:inset_2px_0_0_#22d3ee]";

const ACTIONS =
  "flex items-center gap-[5px] transition-[opacity,transform] duration-[140ms] ease-[ease] max-[800px]:pointer-events-auto max-[800px]:translate-x-0 max-[800px]:opacity-100";
const ACTIONS_HIDDEN =
  "pointer-events-none translate-x-1 opacity-0 group-hover:pointer-events-auto group-hover:translate-x-0 group-hover:opacity-100";
const ACTIONS_SHOWN = "pointer-events-auto translate-x-0 opacity-100";

const ACT_BTN =
  "inline-flex h-[31px] w-[31px] cursor-pointer items-center justify-center rounded-[7px] border border-solid border-transparent bg-transparent p-0 text-[#718197] transition-[color,background-color,border-color,transform] duration-[140ms] ease-[ease] hover:-translate-y-px [&>svg]:h-[15px] [&>svg]:w-[15px] [&>svg]:fill-none [&>svg]:stroke-current [&>svg]:[stroke-linecap:round] [&>svg]:[stroke-linejoin:round] [&>svg]:[stroke-width:1.8]";
const EDIT_HOVER = "hover:border-[rgba(56,189,248,0.18)] hover:bg-[rgba(34,211,238,0.07)] hover:text-[#67e8f9]";
const DELETE_HOVER = "hover:border-[rgba(248,113,113,0.2)] hover:bg-[rgba(248,113,113,0.07)] hover:text-[#fb7185]";

const USAGE =
  "inline-flex min-h-[25px] items-center justify-center whitespace-nowrap rounded-[999px] border border-solid px-[9px] text-[10.5px] font-medium";
const USAGE_USED = "border-[rgba(56,189,248,0.18)] bg-[rgba(56,189,248,0.07)] text-[#7dd3fc]";
const USAGE_UNUSED = "border-[rgba(148,163,184,0.1)] bg-[rgba(148,163,184,0.035)] text-[#64748b]";

/** One step in the library list (legacy .step-item). */
export default function StepRow({ step, selected, onSelect, onEdit, onDelete }) {
  const line = stepLine(step.action);
  const expected = (step.expected || "").trim();
  const usage = usagePill(step.used_in_cases);
  return (
    <div
      role="option"
      aria-selected={selected}
      tabIndex={0}
      className={`${ROW} ${selected ? ROW_SELECTED : ROW_IDLE}`}
      onClick={() => onSelect(step.id)}
      onKeyDown={(e) => {
        if (e.target === e.currentTarget && (e.key === "Enter" || e.key === " ")) {
          e.preventDefault();
          onSelect(step.id);
        }
      }}
    >
      <div className="min-w-0 flex-1">
        <div className="flex min-w-0 items-baseline text-[13px] font-medium leading-[1.5] text-[#dbe3ec] [word-break:break-word]">
          {line.keyword && (
            <span className={`mr-[7px] flex-[0_0_auto] font-semibold tracking-normal ${KW_COLOR[line.type]}`}>
              {line.keyword}
            </span>
          )}
          <span className="min-w-0">{line.text}</span>
        </div>
        {expected && (
          <div className="mt-1.5 flex items-start gap-2 text-[11.5px] leading-[1.45] text-[#718197] [word-break:break-word]">
            <span className="m-0 inline-flex h-[18px] flex-[0_0_auto] items-center rounded border border-solid border-[rgba(148,163,184,0.14)] bg-[rgba(148,163,184,0.035)] px-[5px] text-[8.5px] font-semibold uppercase tracking-[0.06em] text-[#64748b]">
              Expected
            </span>
            <span>{expected}</span>
          </div>
        )}
      </div>
      {/* Clicks here do not select the row. */}
      <div
        className="flex flex-[0_0_auto] items-center gap-3 max-[800px]:flex-col max-[800px]:items-end"
        onClick={(e) => e.stopPropagation()}
      >
        <span className={`${USAGE} ${usage.unused ? USAGE_UNUSED : USAGE_USED}`} title={usage.title}>
          {usage.label}
        </span>
        <div className={`${ACTIONS} ${selected ? ACTIONS_SHOWN : ACTIONS_HIDDEN}`}>
          <button
            type="button"
            className={`${ACT_BTN} ${EDIT_HOVER}`}
            title="Edit step"
            aria-label="Edit step"
            onClick={() => onEdit(step)}
          >
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="M12 20h9" />
              <path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L8 18l-4 1 1-4Z" />
            </svg>
          </button>
          <button
            type="button"
            className={`${ACT_BTN} ${DELETE_HOVER}`}
            title="Delete step"
            aria-label="Delete step"
            onClick={() => onDelete(step)}
          >
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="M3 6h18" />
              <path d="M8 6V4h8v2" />
              <path d="M19 6l-1 14H6L5 6" />
              <path d="M10 11v5" />
              <path d="M14 11v5" />
            </svg>
          </button>
        </div>
      </div>
    </div>
  );
}
