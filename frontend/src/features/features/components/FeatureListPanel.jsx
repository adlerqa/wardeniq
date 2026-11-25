import { SkeletonCards, SkeletonState } from "../../../components/feedback/Skeleton.jsx";
import { goToProjects } from "../../../lib/compatBridge.js";
import { cardMeta, featureCountText } from "../lib/features.js";

const stop = (e) => e.stopPropagation();

function FeatureCards({ fs, cf }) {
  const { list } = fs;
  if (list.status === "loading")
    return (
      <SkeletonState label="Loading features">
        <SkeletonCards count={6} />
      </SkeletonState>
    );
  if (list.status === "error")
    return (
      <div className="empty-state">
        <div className="empty-state-icon">!</div>
        <h3>Couldn&apos;t load features</h3>
        <p>{list.error}</p>
        <button className="ghost" onClick={fs.loadFeatures}>
          Retry
        </button>
      </div>
    );
  if (list.status !== "ready") return null;
  if (!list.features.length)
    return (
      <div className="empty-state">
        <div className="empty-state-icon">+</div>
        <h3>No features yet</h3>
        <p>Create your first feature to continue.</p>
        <button className="go" onClick={cf.showFeatureCreate}>
          Create feature
        </button>
      </div>
    );
  return list.features.map((f) => (
    <div
      key={f.id}
      className={`entity-card${fs.openMenu === f.id ? " menu-open" : ""}`}
      data-feature-card={f.id}
      onClick={() => fs.open(f.id)}
    >
      <button
        className="entity-menu-btn"
        title="Feature options"
        onClick={(e) => {
          e.stopPropagation();
          fs.toggleMenu(f.id);
        }}
      >
        <svg viewBox="0 0 24 24" fill="currentColor" style={{ width: "16px", height: "16px", display: "block" }}>
          <circle cx="12" cy="5" r="2"></circle>
          <circle cx="12" cy="12" r="2"></circle>
          <circle cx="12" cy="19" r="2"></circle>
        </svg>
      </button>
      <div className="entity-menu" onClick={stop}>
        <button onClick={() => fs.renameFromCard(f.id)}>Rename</button>
        <button onClick={() => fs.importSheet(f)}>Import Sheet</button>
        <button className="danger-option" onClick={() => fs.deleteFromCard(f.id)}>
          Delete
        </button>
      </div>
      <div className="entity-name">{f.name}</div>
      <div className="entity-meta">{cardMeta(f)}</div>
      <div className="entity-foot">
        <span>Open workspace</span>
        <span className="entity-arrow">›</span>
      </div>
    </div>
  ));
}

/** Feature cards for the current project (useFeatures). */
export default function FeatureListPanel({ fs, cf }) {
  const p = fs.projects;
  // Before the first project-list load the title reads "Features".
  const title = p.synced ? (fs.active ? fs.active.name : "") : "Features";
  return (
    <div id="feature-list-page" className="stage-page" hidden={fs.page !== "list"}>
      <div className="page-toolbar">
        <div>
          <button className="ghost" id="features-back-project" style={{ marginBottom: "12px" }} onClick={() => goToProjects()}>
            Back to projects
          </button>
          <h2 id="features-page-title">{title}</h2>
          <div className="sub" id="features-project-context">
            {fs.active ? featureCountText(fs.active) : ""}
          </div>
        </div>
        <button
          className="go"
          id="feature-new-btn"
          style={{ display: fs.showNewBtn ? "" : "none" }}
          onClick={cf.showFeatureCreate}
        >
          + New feature
        </button>
      </div>
      <div id="feat-list" className="entity-grid">
        <FeatureCards fs={fs} cf={cf} />
      </div>
    </div>
  );
}
