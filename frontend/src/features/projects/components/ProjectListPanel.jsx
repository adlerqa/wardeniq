import { REPO_KINDS, patPlaceholder, pickerRows } from "../lib/projects.js";
import ProjectCards from "./ProjectCards.jsx";
import StatusText from "./StatusText.jsx";

/** One repo picker of the create wizard (#new-proj-app-picker / #new-proj-test-picker). */
function RepoPicker({ cp, sectionKey }) {
  if (!cp.available.length) return <div className="muted cp-repo-empty">Load repositories above to pick.</div>;
  const [mine, other] = sectionKey === "app" ? [cp.appRepos, cp.testRepos] : [cp.testRepos, cp.appRepos];
  const rows = pickerRows(cp.available, mine, other);
  if (!rows.length) return <div className="muted cp-repo-empty">No more repositories available.</div>;
  return rows.map(({ repo: r, staged }) => (
    <div key={r.full_name} className={`cp-repo-row${staged ? " staged" : ""}`}>
      <div className="cp-repo-main">
        <div className="cp-repo-name">
          <b>{r.full_name}</b>{" "}
          <span className="cp-repo-meta">{`${r.private ? "private" : "public"}${r.default_branch ? " · " + r.default_branch : ""}`}</span>
        </div>
        {staged ? (
          <div className="cp-repo-fields" style={{ display: "flex", gap: "8px", alignItems: "center", marginTop: "6px" }}>
            <input
              className="cp-repo-label-input"
              data-key={sectionKey}
              data-fn={r.full_name}
              value={staged.label || ""}
              onChange={(e) => cp.updateRepo(sectionKey, r.full_name, { label: e.target.value })}
              placeholder="Display name (e.g. Backend API)"
              style={{ flex: "1" }}
            />
            <select
              className="cp-repo-kind-input"
              data-key={sectionKey}
              data-fn={r.full_name}
              title="Kind"
              value={staged.kind || (sectionKey === "test" ? "test" : "BE")}
              onChange={(e) => cp.updateRepo(sectionKey, r.full_name, { kind: e.target.value })}
              style={{ flex: "0 0 130px", fontSize: "12px", padding: "5px 8px" }}
            >
              {REPO_KINDS.map(([v, lab]) => (
                <option key={v} value={v}>
                  {lab}
                </option>
              ))}
            </select>
          </div>
        ) : null}
      </div>
      <div className="cp-repo-actions">
        {staged ? (
          <button
            type="button"
            className="cp-repo-remove"
            data-key={sectionKey}
            data-fn={r.full_name}
            onClick={() => cp.removeRepo(sectionKey, r.full_name)}
          >
            remove
          </button>
        ) : (
          <button
            type="button"
            className="cp-repo-add"
            data-key={sectionKey}
            data-fn={r.full_name}
            onClick={() => cp.addRepo(sectionKey, r.full_name)}
          >
            add
          </button>
        )}
      </div>
    </div>
  ));
}

/** Project cards and the "Create project" wizard (useProjects + useCreateProject). */
export default function ProjectListPanel({ pj, cp }) {
  const creating = pj.page === "create";
  return (
    <div id="project-list-page" className="stage-page" hidden={pj.page === "detail"}>
      <div className="page-toolbar" id="project-list-toolbar" style={{ display: creating ? "none" : "" }}>
        <div>
          <h2>Projects</h2>
        </div>
        <button className="go" id="proj-new-btn" onClick={cp.open}>
          + New project
        </button>
      </div>
      <div id="proj-create-card" className="card create-project-card" style={{ display: creating ? "block" : "none" }}>
        <div className="page-toolbar" style={{ marginBottom: "18px" }}>
          <button className="ghost" id="proj-create-back" type="button" onClick={cp.cancel}>
            Back
          </button>
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
            <input
              id="new-proj-name"
              ref={cp.nameRef}
              className="line-clamp-2 text-wrap"
              placeholder="E.g. WardenIQ Core"
              value={cp.name}
              onChange={(e) => cp.setName(e.target.value)}
            />
            <div className="muted cp-err" id="new-proj-name-err">
              {cp.nameErr}
            </div>
          </div>
          <div className="cp-step">
            <div className="cp-step-head">
              <span className="cp-step-num">2</span>
              <h3>Description</h3>
              <span className="muted">(optional)</span>
            </div>
            <textarea
              id="new-proj-desc"
              className="line-clamp-3 text-wrap"
              rows="3"
              placeholder="What this project is about (optional)"
              value={cp.description}
              onChange={(e) => cp.setDescription(e.target.value)}
            ></textarea>
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
              <select id="new-proj-jira" value={cp.jiraKey} onChange={(e) => cp.setJiraKey(e.target.value)}>
                <option value="">— none —</option>
                {cp.jira.options.map((o) => (
                  <option key={o.value} value={o.value} data-name={o.name}>
                    {o.label}
                  </option>
                ))}
              </select>
              <button className="ghost" id="new-proj-jira-refresh" type="button" onClick={cp.loadJira}>
                Reload
              </button>
            </div>
            <div className="muted" id="new-proj-jira-status" style={{ fontSize: "11px", marginTop: "6px" }}>
              <StatusText status={cp.jira.status} />
            </div>
          </div>
          <div className="cp-step">
            <div className="cp-step-head">
              <span className="cp-step-num">4</span>
              <h3>Confluence space</h3>
              <span className="muted">(optional)</span>
            </div>
            <div className="sub" style={{ margin: "0 0 8px" }}>Link a Confluence space to pull design/spec context for this project.</div>
            <div className="cp-jira-row">
              <select id="new-proj-confluence" value={cp.confKey} onChange={(e) => cp.setConfKey(e.target.value)}>
                <option value="">— none —</option>
                {cp.confluence.options.map((o) => (
                  <option key={o.value} value={o.value} data-name={o.name}>
                    {o.label}
                  </option>
                ))}
              </select>
              <button className="ghost" id="new-proj-confluence-refresh" type="button" onClick={cp.loadConfluence}>
                Reload
              </button>
            </div>
            <div className="muted" id="new-proj-confluence-status" style={{ fontSize: "11px", marginTop: "6px" }}>
              <StatusText status={cp.confluence.status} />
            </div>
          </div>
          <div className="cp-step cp-full">
            <div className="cp-step-head">
              <span className="cp-step-num">5</span>
              <h3>Git provider &amp; PAT</h3>
              <span className="muted">(optional)</span>
            </div>
            <div className="cp-provider-toggle">
              {[
                ["github", "GitHub"],
                ["gitlab", "GitLab"],
              ].map(([v, label]) => (
                <button
                  key={v}
                  type="button"
                  data-provider={v}
                  className={`cp-prov${cp.provider === v ? " active" : ""}`}
                  onClick={() => cp.chooseProvider(v)}
                >
                  {label}
                </button>
              ))}
            </div>
            <div className="sub" style={{ margin: "0 0 8px" }}>Provide a fine-grained PAT scoped to PR + contents read. wardenIQ stores it encrypted at rest, registers webhooks on the repos you pick below, and uses it to read PR diffs for coverage analysis.</div>
            <input
              type="password"
              id="new-proj-pat"
              placeholder={patPlaceholder(cp.provider)}
              value={cp.pat}
              onChange={(e) => cp.setPat(e.target.value)}
            />
            <div style={{ marginTop: "8px" }}>
              <button
                className="ghost"
                type="button"
                id="new-proj-load-repos"
                aria-busy={cp.loadingRepos ? "true" : undefined}
                onClick={cp.loadRepos}
              >
                Load my repositories
              </button>
              <span className="muted" id="new-proj-pat-status" style={{ fontSize: "11px", marginLeft: "8px" }}>
                <StatusText status={cp.patStatus} />
              </span>
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
              <RepoPicker cp={cp} sectionKey="app" />
            </div>
            <div className="muted" style={{ marginTop: "8px", fontSize: "12px" }}>
              Selected:
              <span id="new-proj-app-count">{cp.appRepos.length}</span>
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
              <RepoPicker cp={cp} sectionKey="test" />
            </div>
            <div className="muted" style={{ marginTop: "8px", fontSize: "12px" }}>
              Selected:
              <span id="new-proj-test-count">{cp.testRepos.length}</span>
            </div>
          </div>
          <div className="cp-step cp-full" style={{ borderBottom: "none" }}>
            <div className="cp-actions">
              <button
                className="go"
                id="proj-create-save"
                disabled={cp.saving}
                aria-busy={cp.saving ? "true" : undefined}
                onClick={cp.save}
              >
                Create project
              </button>
              <button className="ghost" id="proj-create-cancel" type="button" disabled={cp.saving} onClick={cp.cancel}>
                Cancel
              </button>
              <span className="muted" id="proj-create-status" style={{ fontSize: "12px", marginLeft: "8px" }}>
                <StatusText status={cp.createStatus} />
              </span>
            </div>
          </div>
        </div>
      </div>
      <div id="project-cards-container" className="entity-grid" style={{ display: creating ? "none" : "" }}>
        <ProjectCards pj={pj} />
      </div>
    </div>
  );
}
