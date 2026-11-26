/**
 * Back button and breadcrumbs above the screens (was 00-core.js updateBackbar).
 * `model` comes from app/navigation.js backbarModel: every crumb but the last
 * is clickable.
 */
export default function Backbar({ model }) {
  const { show, onBack, crumbs } = model;
  return (
    <div className={`backbar${show ? " show" : ""}`} id="backbar">
      <button className="ghost" id="backbar-btn" onClick={onBack || undefined}>
        Back
      </button>
      <div className="divider"></div>
      <span className="crumb" id="backbar-label">
        {crumbs.map((c, i) =>
          i === crumbs.length - 1 ? (
            <span key={i} className="crumb active">
              {c.label}
            </span>
          ) : (
            [
              <span key={i} className="crumb clickable" onClick={c.onClick || undefined}>
                {c.label}
              </span>,
              <span key={i + "s"} className="separator">
                ›
              </span>,
            ]
          ),
        )}
      </span>
    </div>
  );
}
