/**
 * Small building blocks shared by the Users screen panels. Styles reproduce the
 * legacy classes they replace (.badge, .u-action, .access-cell, .chip,
 * .proj-checklist, .radio-inline) so the screen looks the same.
 */

const BADGE_BASE =
  "rounded-[20px] border border-solid border-transparent px-[11px] py-1 text-[10.5px] font-medium";

/** Pill badge. tone: "neutral" | "green" | "amber" | "red". */
export function Badge({ tone = "neutral", children }) {
  const tones = {
    neutral: "bg-white/[0.06] text-muted",
    green: "bg-[rgba(52,211,153,0.16)] text-[#7eecc0]",
    amber: "bg-[rgba(216,158,44,0.18)] text-[#e9c46a]",
    red: "bg-white/[0.06] text-red",
  };
  return <span className={`${BADGE_BASE} ${tones[tone]}`}>{children}</span>;
}

const ACTION =
  "inline-flex cursor-pointer items-center gap-[5px] whitespace-nowrap text-[12px] font-medium [&>svg]:opacity-75";
const ACTION_NORMAL =
  "rounded-[7px] border border-solid border-line bg-white/[0.03] px-[11px] py-[5px] text-text transition-[background,border-color] duration-[120ms] hover:border-accent2 hover:bg-white/[0.07]";
const ACTION_DANGER =
  "rounded-[9px] border-none border-[rgba(239,68,68,0.28)] bg-transparent bg-[linear-gradient(135deg,#fb7185,#ef4444)] px-[13px] py-2 text-[#f4a3a3] transition-[background,border-color] duration-[120ms] hover:bg-none hover:bg-[rgba(239,68,68,0.14)] hover:text-[#fca5a5]";

/** Row action button (legacy .u-action / .u-action.danger). */
export function ActionButton({ icon, label, title, danger = false, onClick }) {
  return (
    <button
      type="button"
      title={title}
      onClick={onClick}
      className={`${ACTION} ${danger ? ACTION_DANGER : ACTION_NORMAL}`}
    >
      {icon}
      {label}
    </button>
  );
}

/** Access column contents. access: result of userAccess() / tokenAccess(). */
export function AccessCell({ access }) {
  const cls = "text-[11.5px] text-muted";
  if (access.kind === "admin")
    return (
      <span className={cls}>
        All projects <span className="text-[12px] text-muted">(admin)</span>
      </span>
    );
  if (access.kind === "all") return <span className={cls}>All projects</span>;
  if (access.kind === "none") return <span className={`${cls} !text-red`}>No projects</span>;
  return (
    <span className={cls}>
      {access.names.map((n, i) => (
        <span
          key={`${n}-${i}`}
          className="mx-0.5 my-px inline-block rounded-xl border border-solid border-line bg-white/[0.06] px-2 py-px text-text"
        >
          {n}
        </span>
      ))}
    </span>
  );
}

/** Radio with its label (legacy .radio-inline). */
export function RadioOption({ name, value, checked, disabled, onChange, children }) {
  return (
    <label className="inline-flex cursor-pointer items-center gap-1.5 text-[13px] text-text">
      <input
        type="radio"
        name={name}
        value={value}
        checked={checked}
        disabled={disabled}
        onChange={() => onChange(value)}
        className="m-0 w-auto"
      />
      {children}
    </label>
  );
}

/** Project checkboxes (legacy .proj-checklist). */
export function ProjectChecklist({ projects, selected, onToggle, emptyText }) {
  return (
    <div className="flex max-h-[180px] flex-wrap gap-2 overflow-auto rounded-lg border border-solid border-line bg-panel2 p-2.5">
      {projects.length ? (
        projects.map((p) => (
          <label
            key={p.id}
            className="inline-flex cursor-pointer items-center gap-1.5 rounded-md border border-solid border-line bg-white/[0.04] px-[9px] py-[5px] text-[12.5px] hover:border-accent2"
          >
            <input
              type="checkbox"
              value={p.id}
              checked={selected.includes(p.id)}
              onChange={(e) => onToggle(p.id, e.target.checked)}
              className="m-0 w-auto"
            />{" "}
            {p.name || p.id}
          </label>
        ))
      ) : (
        <span className="text-[12px] text-muted">{emptyText}</span>
      )}
    </div>
  );
}
