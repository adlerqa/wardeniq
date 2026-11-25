import { goToProjectFeatures } from "../../../lib/compatBridge.js";

/**
 * Project settings. The header (name, stats, rename / delete) is React
 * (useProjects); the repository part below is still driven by
 * 02-projects.js until it moves (#257).
 */
export default function ProjectDetailPanel({ pj }) {
  return (
    <div id="project-detail-page" className="stage-page stage-shell" hidden={pj.page !== "detail"}>
      <div className="stage-header">
        <button className="ghost" id="project-detail-back" onClick={pj.showProjectList}>
          ← All projects
        </button>
        <div className="stage-header-actions">
          <button className="go" id="proj-features-btn" onClick={() => goToProjectFeatures()}>
            View features
          </button>
          <button className="ghost" id="proj-rename-btn" onClick={pj.renameActive}>
            Rename
          </button>
          <button className="danger" id="proj-del-btn" onClick={pj.deleteActive}>
            Delete project
          </button>
        </div>
      </div>
      <div className="card">
        <h2 id="active-proj-title" style={{ fontSize: "21px" }}>
          {pj.activeTitle}
        </h2>
        <div className="sub" id="active-proj-stats">
          {pj.activeStats}
        </div>
        <div className="project-summary">
          <div className="summary-box">
            <b id="project-feature-count">{pj.active ? pj.active.feature_count : 0}</b>
            <span>Features</span>
          </div>
          <div className="summary-box">
            <b id="project-repo-count">{pj.active ? pj.active.repo_count : 0}</b>
            <span>Repositories</span>
          </div>
          <div className="summary-box">
            <b id="project-case-count">{pj.caseCount}</b>
            <span>Linked test cases</span>
          </div>
        </div>
        <div className="card" style={{ background: "var(--panel2)", marginBottom: "16px" }}>
          <h3 style={{ margin: "0", fontSize: "14px" }}>Connect repository</h3>
          <div className="sub">Add code to monitor pull requests, analyze changes, and map coverage. Repositories are connected via this project&apos;s own GitHub/GitLab PAT.</div>
          <div style={{ display: "flex", gap: "12px", alignItems: "center", margin: "4px 0 14px", flexWrap: "wrap" }}>
            <label style={{ margin: "0", fontSize: "12px", color: "var(--muted)" }}>Git provider for this project:</label>
            <div className="cp-provider-toggle" style={{ margin: "0" }}>
              <button type="button" data-pd-provider="github" className="cp-prov active">GitHub</button>
              <button type="button" data-pd-provider="gitlab" className="cp-prov">GitLab</button>
            </div>
            <span className="muted" id="pd-pat-status" style={{ fontSize: "11px" }}></span>
          </div>
          <div className="row" style={{ marginBottom: "10px" }}>
            <div style={{ flex: "2" }}>
              <label>
                Project PAT
                <span className="muted" style={{ fontWeight: "400" }}>(saved encrypted; leave blank to keep current)</span>
              </label>
              <input id="pd-pat" type="password" placeholder="ghp_..." />
            </div>
            <div style={{ flex: "0 0 auto", alignSelf: "flex-end", display: "flex", gap: "8px", paddingBottom: "0" }}>
              <button className="ghost" id="pd-pat-save" type="button">Save PAT</button>
              <button className="ghost" id="pd-pat-clear" type="button">Clear</button>
            </div>
          </div>
          <div style={{ display: "flex", gap: "10px", alignItems: "flex-end", flexWrap: "wrap" }}>
            <div style={{ flex: "2", minWidth: "220px", position: "relative" }} data-repo-suggest-wrap>
              <label>Repository URL or Owner/Name</label>
              <input id="repo-url" placeholder="https://github.com/org/backend-api" autoComplete="off" />
              <div
                id="repo-url-suggest"
                hidden
                style={{
                  position: "absolute",
                  top: "100%",
                  left: 0,
                  right: 0,
                  zIndex: 50,
                  maxHeight: "220px",
                  overflow: "auto",
                  background: "#0d151f",
                  border: "1px solid var(--line)",
                  borderRadius: "8px",
                  marginTop: "4px",
                  boxShadow: "0 8px 20px rgba(0,0,0,.35)",
                }}
              ></div>
            </div>
            <div style={{ width: "115px" }}>
              <label>Type</label>
              <select id="repo-type">
                <option value="app">App (with webhook)</option>
                <option value="test">Test (no webhook)</option>
              </select>
            </div>
            <div style={{ width: "135px" }}>
              <label>Kind</label>
              <select id="repo-kind">
                <option value="BE">Backend</option>
                <option value="FE">Frontend</option>
                <option value="test">Test</option>
                <option value="infra">Infrastructure</option>
              </select>
            </div>
            <button className="go" id="repo-add">Connect</button>
          </div>
          <button className="ghost" id="repo-pick" style={{ marginTop: "10px" }}>Load my repositories</button>
        </div>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "8px" }}>
          <h3 style={{ margin: "0", fontSize: "14px" }}>Repositories</h3>
          <div className="muted" id="sync-status"></div>
        </div>
        <div id="repo-list" style={{ display: "flex", flexDirection: "column", gap: "8px" }}></div>
      </div>
    </div>
  );
}
