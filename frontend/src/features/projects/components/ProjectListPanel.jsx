/** ProjectListPanel for projects. */
export default function ProjectListPanel() {
  return (
    <div id="project-list-page" className="stage-page">
      <div className="page-toolbar" id="project-list-toolbar">
        <div>
          <h2>Projects</h2>
        </div>
        <button className="go" id="proj-new-btn">+ New project</button>
      </div>
      <div id="proj-create-card" className="card create-project-card" style={{ display: "none" }}>
        <div className="page-toolbar" style={{ marginBottom: "18px" }}>
          <button className="ghost" id="proj-create-back" type="button">Back</button>
          <div></div>
        </div>
        <h2 style={{ fontSize: "17px" }}>Create project</h2>
        <div className="sub">Configure the project&apos;s basics, optional Jira/Confluence association, and connect repositories. Only the project name is required — everything else can be configured later.</div>
        <div className="cp-grid">
          <div className="cp-step">
            <div className="cp-step-head">
              <span className="cp-step-num">1</span>
              <h3>Project name</h3>
              <span className="cp-required">*</span>
            </div>
            <input id="new-proj-name" className="line-clamp-2 text-wrap" placeholder="E.g. WardenIQ Core" />
            <div className="muted cp-err" id="new-proj-name-err"></div>
          </div>
          <div className="cp-step">
            <div className="cp-step-head">
              <span className="cp-step-num">2</span>
              <h3>Description</h3>
              <span className="muted">(optional)</span>
            </div>
            <textarea id="new-proj-desc" className="line-clamp-3 text-wrap" rows="3" placeholder="What this project is about (optional)"></textarea>
          </div>
          <div className="cp-step">
            <div className="cp-step-head">
              <span className="cp-step-num">3</span>
              <h3>Jira project</h3>
              <span className="muted">(optional)</span>
            </div>
            <div className="sub" style={{ margin: "0 0 8px" }}>
              Pick from the Jira projects this workspace can see. Configure Jira in{" "}
              <b>Settings → Jira &amp; Confluence</b>{" "}
              first to populate this dropdown.
            </div>
            <div className="cp-jira-row">
              <select id="new-proj-jira">
                <option value="">— none —</option>
              </select>
              <button className="ghost" id="new-proj-jira-refresh" type="button">Reload</button>
            </div>
            <div className="muted" id="new-proj-jira-status" style={{ fontSize: "11px", marginTop: "6px" }}></div>
          </div>
          <div className="cp-step">
            <div className="cp-step-head">
              <span className="cp-step-num">4</span>
              <h3>Confluence space</h3>
              <span className="muted">(optional)</span>
            </div>
            <div className="sub" style={{ margin: "0 0 8px" }}>Link a Confluence space to pull design/spec context for this project.</div>
            <div className="cp-jira-row">
              <select id="new-proj-confluence">
                <option value="">— none —</option>
              </select>
              <button className="ghost" id="new-proj-confluence-refresh" type="button">Reload</button>
            </div>
            <div className="muted" id="new-proj-confluence-status" style={{ fontSize: "11px", marginTop: "6px" }}></div>
          </div>
          <div className="cp-step cp-full">
            <div className="cp-step-head">
              <span className="cp-step-num">5</span>
              <h3>Git provider &amp; PAT</h3>
              <span className="muted">(optional)</span>
            </div>
            <div className="cp-provider-toggle">
              <button type="button" data-provider="github" className="cp-prov active">GitHub</button>
              <button type="button" data-provider="gitlab" className="cp-prov">GitLab</button>
            </div>
            <div className="sub" style={{ margin: "0 0 8px" }}>Provide a fine-grained PAT scoped to PR + contents read. wardenIQ stores it encrypted at rest, registers webhooks on the repos you pick below, and uses it to read PR diffs for coverage analysis.</div>
            <input type="password" id="new-proj-pat" placeholder="ghp_..." />
            <div style={{ marginTop: "8px" }}>
              <button className="ghost" type="button" id="new-proj-load-repos">Load my repositories</button>
              <span className="muted" id="new-proj-pat-status" style={{ fontSize: "11px", marginLeft: "8px" }}></span>
            </div>
          </div>
          <div className="cp-step">
            <div className="cp-step-head">
              <span className="cp-step-num">6</span>
              <h3>App repositories</h3>
              <span className="muted">(optional)</span>
            </div>
            <div className="sub" style={{ margin: "0 0 8px" }}>Repositories that contain your application code. Webhooks are registered on these so PRs trigger coverage automatically.</div>
            <div className="cp-repo-picker" id="new-proj-app-picker">
              <div className="muted cp-repo-empty">Load repositories above to pick.</div>
            </div>
            <div className="muted" style={{ marginTop: "8px", fontSize: "12px" }}>
              Selected:
              <span id="new-proj-app-count">0</span>
            </div>
          </div>
          <div className="cp-step">
            <div className="cp-step-head">
              <span className="cp-step-num">7</span>
              <h3>Test repositories</h3>
              <span className="muted">(optional)</span>
            </div>
            <div className="sub" style={{ margin: "0 0 8px" }}>Repositories that contain your automated tests (Playwright, Cypress, etc.). wardenIQ scans them for existing coverage — no webhook is added.</div>
            <div className="cp-repo-picker" id="new-proj-test-picker">
              <div className="muted cp-repo-empty">Load repositories above to pick.</div>
            </div>
            <div className="muted" style={{ marginTop: "8px", fontSize: "12px" }}>
              Selected:
              <span id="new-proj-test-count">0</span>
            </div>
          </div>
          <div className="cp-step cp-full" style={{ borderBottom: "none" }}>
            <div className="cp-actions">
              <button className="go" id="proj-create-save">Create project</button>
              <button className="ghost" id="proj-create-cancel" type="button">Cancel</button>
              <span className="muted" id="proj-create-status" style={{ fontSize: "12px", marginLeft: "8px" }}></span>
            </div>
          </div>
        </div>
      </div>
      <div id="project-cards-container" className="entity-grid"></div>
    </div>
  );
}
