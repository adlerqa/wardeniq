import { SkeletonCards, SkeletonState } from "../../../components/feedback/Skeleton.jsx";
import { cardMeta } from "../lib/projects.js";

const stop = (e) => e.stopPropagation();

/** Contents of #project-cards-container. */
export default function ProjectCards({ pj }) {
  if (pj.loading && !pj.loaded)
    return (
      <SkeletonState label="Loading projects">
        <SkeletonCards count={6} />
      </SkeletonState>
    );
  if (!pj.loaded) return null;
  if (!pj.projects.length)
    return (
      <div className="empty-state" style={{ gridColumn: "1 / -1" }}>
        <div className="empty-state-icon">+</div>
        <h3>No projects yet</h3>
        <p>Create your first project to continue.</p>
        <button className="go" onClick={pj.showProjectCreate}>
          Create project
        </button>
      </div>
    );
  return pj.projects.map((p) => (
    <div
      key={p.id}
      className={`entity-card${pj.openMenu === p.id ? " menu-open" : ""}`}
      data-project-card={p.id}
      onClick={() => pj.openFeatures(p.id)}
    >
      <button
        className="entity-menu-btn"
        title="Project options"
        onClick={(e) => {
          e.stopPropagation();
          pj.toggleMenu(p.id);
        }}
      >
        <svg viewBox="0 0 24 24" fill="currentColor" style={{ width: "16px", height: "16px", display: "block" }}>
          <circle cx="12" cy="5" r="2"></circle>
          <circle cx="12" cy="12" r="2"></circle>
          <circle cx="12" cy="19" r="2"></circle>
        </svg>
      </button>
      <div className="entity-menu" onClick={stop}>
        <button onClick={() => pj.openSettings(p.id)}>Settings &amp; repositories</button>
        <button onClick={() => pj.renameFromCard(p.id)}>Rename</button>
        <button className="danger-option" onClick={() => pj.deleteFromCard(p.id)}>
          Delete
        </button>
      </div>
      <div className="entity-name">{p.name}</div>
      <div className="entity-meta">{cardMeta(p)}</div>
      <div className="entity-foot">
        <span>Open features</span>
        <span className="entity-arrow">›</span>
      </div>
    </div>
  ));
}
