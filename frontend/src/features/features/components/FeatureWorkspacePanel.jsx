import { Fragment, useEffect, useRef } from "react";

import { brandLoaderHtml, navigateTo } from "../../../lib/compatBridge.js";
import { escapeHtml } from "../../../lib/html.js";
import { CaseRows } from "../../test-cases/components/CaseList.jsx";
import { CASE_GROUPS, featureMeta, featureSummaryText, genCaption, versionInfo } from "../lib/workspace.js";

const SUMMARY_GROUPS = [
  ["api", "API"],
  ["ui", "UI validations"],
  ["functional", "Business / functional"],
  ["e2e", "End-to-end"],
  ["nfr", "Edge & reliability"],
  ["integration", "Integration"],
];

const GEN_MESSAGES = ["Generating test cases…", "AI drafting scenarios…", "Normalizing & de-duping…", "Finalizing suite…"];

/** Open every case group and scroll to them ("Test cases" tile). */
function showAndScrollToTestCases() {
  document.querySelectorAll("#d-cases details.case-group").forEach((d) => {
    d.open = true;
  });
  const el = document.getElementById("d-cases");
  if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
}

function ActionTile({ cls, onClick, title, text, meta }) {
  return (
    <button type="button" className={`feature-action ${cls}`} onClick={onClick}>
      <div className="feature-action-content">
        <b>{title}</b>
        <span>{text}</span>
      </div>
      <div className="feature-action-meta">
        <span>{meta[0]}</span>
        <span>{meta[1]}</span>
      </div>
    </button>
  );
}

function Overview({ f, bt }) {
  const n = f.test_cases.length;
  return (
    <div className="feature-hero">
      <div className="muted">{featureMeta(f)}</div>
      <div className="feature-summary">{featureSummaryText(f)}</div>
      <div className="feature-stats">
        {SUMMARY_GROUPS.map(([t, label]) => (
          <div key={t} className="feature-stat">
            <b>{(bt[t] || []).length}</b>
            <span>{label}</span>
          </div>
        ))}
      </div>
      <div className="feature-action-grid">
        <ActionTile
          cls="feature-action-cases"
          onClick={showAndScrollToTestCases}
          title="Test cases"
          text={`Review, filter, execute, and edit ${n} cases.`}
          meta={[`${n} cases`, "Open library"]}
        />
        <ActionTile
          cls="feature-action-validator"
          onClick={() => navigateTo("validator")}
          title="Validator"
          text="Check requirement clarity and identify missing decisions."
          meta={["Requirements", "Review"]}
        />
        <ActionTile
          cls="feature-action-plan"
          onClick={() => navigateTo("testplan")}
          title="Test plan"
          text="Build the QA strategy and generate an exportable test plan."
          meta={["QA strategy", "Generate"]}
        />
        <ActionTile
          cls="feature-action-gap"
          onClick={() => navigateTo("gap")}
          title="Gap Analysis"
          text="Inspect code and automation coverage with exact commit links."
          meta={["Coverage", "Analyze"]}
        />
      </div>
    </div>
  );
}

function Coverage({ ws }) {
  const s = ws.coverage.summary;
  if (!s) return null;
  const thr = s.ready_threshold != null ? s.ready_threshold : 80;
  return (
    <div
      style={{
        marginTop: "14px",
        border: "1px solid var(--line,#1e293b)",
        borderRadius: "12px",
        padding: "14px 16px",
        background: "var(--panel,#0d1728)",
      }}
    >
      <div style={{ fontSize: "13px", fontWeight: 600 }}>
        Coverage{" "}
        <span style={{ fontWeight: 400, color: "var(--muted,#94a3b8)" }}>— aggregated across all PRs linked to this feature</span>
      </div>
      <div style={{ fontSize: "12px", color: "var(--muted,#94a3b8)", margin: "2px 0 10px" }}>
        A test case counts as covered once ANY linked PR implements it (no single repo need cover everything).
      </div>
      <div className="dash-gauge">
        <div className="top">
          <span>Code coverage (cases implemented by PRs)</span>
          <b>{`${s.code_pct}%`}</b>
        </div>
        <div className="track">
          <div className="fill code" style={{ width: `${s.code_pct}%` }}></div>
        </div>
      </div>
      <div className="dash-gauge">
        <div className="top">
          <span>Automation Test Coverage (dev-written tests)</span>
          <b>{`${s.automation_pct}%`}</b>
        </div>
        <div className="track">
          <div className="fill auto" style={{ width: `${s.automation_pct}%` }}></div>
        </div>
      </div>
      <div className="dash-cov-note">
        {`${s.covered_cases} covered${s.partial_cases ? ` · ${s.partial_cases} partial (not counted)` : ""} · ${s.automated_cases} automated of ${s.total_cases} cases`}
      </div>
      {s.ready ? (
        <div style={{ marginTop: "10px", color: "#34d399", fontWeight: 600, fontSize: "13px" }}>
          {`✓ Minimum code-coverage target reached (${s.code_pct}% ≥ ${thr}%) — ready for manual QA.`}
        </div>
      ) : (
        <div style={{ marginTop: "10px", color: "#f6a623", fontSize: "12.5px" }}>
          {`Not ready for manual QA — code coverage ${s.code_pct}% is below the ${thr}% target for this feature.`}
        </div>
      )}
      <div
        style={{
          marginTop: "10px",
          display: "flex",
          alignItems: "center",
          gap: "8px",
          flexWrap: "wrap",
          fontSize: "12.5px",
          color: "var(--muted,#94a3b8)",
        }}
      >
        <span>QA-readiness target:</span>
        <input
          key={ws.coverage.seq}
          id="fc-threshold"
          className="needs-editor"
          type="number"
          min="0"
          max="100"
          defaultValue={thr}
          style={{ width: "64px" }}
        />
        <span>% code coverage</span>
        <button
          className="ghost needs-editor"
          type="button"
          onClick={() => ws.saveThreshold(document.getElementById("fc-threshold")?.value)}
        >
          Save
        </button>
        <span id="fc-threshold-status" className="muted">
          {ws.thresholdStatus}
        </span>
      </div>
    </div>
  );
}

function VersionInfo({ f }) {
  const vi = versionInfo(f.version_diff);
  if (!vi) return null;
  if (vi.kind === "replace")
    return (
      <div className="muted" style={{ margin: "8px 0" }}>
        {`This version was regenerated; ${vi.removed} obsolete cases removed.`}
      </div>
    );
  return (
    <div
      className="explain"
      style={{
        background: "rgba(19,112,171,.08)",
        border: "1px solid rgba(19,112,171,.25)",
        borderRadius: "8px",
        padding: "10px 12px",
        margin: "10px 0",
        fontSize: "12.5px",
      }}
    >
      <b>{`Version ${vi.version} diff:`}</b>
      {` ${vi.kept} cases carried over${vi.retired.length ? `, ${vi.retired.length} retired` : ""}, new cases added by generation.`}
      {vi.retired.length ? (
        <details style={{ marginTop: "6px" }}>
          <summary className="muted">retired cases</summary>
          {vi.retired.map((r, i) => (
            <div key={i} className="muted" style={{ marginTop: "4px" }}>
              {`• ${r.title || r.id} — ${r.reason || ""}`}
            </div>
          ))}
        </details>
      ) : null}
    </div>
  );
}

let loaderHtml = null;
const loader = () => (loaderHtml = loaderHtml || brandLoaderHtml("analyze", { compact: true, messages: GEN_MESSAGES }));

/**
 * #d-genbanner: the generation loader. Its markup is set once per run (so the
 * animation doesn't restart); the caption under it follows the job.
 */
function GenBanner({ banner }) {
  const ref = useRef(null);
  let html = "";
  if (banner && banner.kind === "failed")
    html = `<div class="gen-banner err"><span>Generation failed: ${escapeHtml(banner.text)}</span></div>`;
  else if (banner)
    html = `${loader()}<div class="gen-sub" id="d-gencap" style="text-align:center;margin:2px 0 6px">this can take a minute; results will refresh automatically.</div>`;
  const caption = banner && banner.kind === "running" && banner.caption ? genCaption(banner.caption) : null;
  useEffect(() => {
    const cap = ref.current && ref.current.querySelector("#d-gencap");
    if (cap && caption) cap.textContent = caption;
  }, [caption, html]);
  return <div id="d-genbanner" ref={ref} dangerouslySetInnerHTML={{ __html: html }} />;
}

function CaseGroups({ ws }) {
  if (ws.view.error) return <div className="err">{ws.view.error}</div>;
  const f = ws.feature;
  if (!f) return null;
  const total = CASE_GROUPS.reduce((n, [t]) => n + (ws.bt[t] || []).length, 0);
  return (
    <Fragment key={ws.view.seq}>
      {CASE_GROUPS.map(([t, label, help]) => {
        const cases = ws.bt[t] || [];
        return (
          <details key={t} className="case-group">
            <summary title={help}>
              <span>{`${label} (${cases.length})`}</span>
            </summary>
            <div className="case-group-body">
              {cases.length ? (
                <CaseRows items={cases} cl={ws.cl} scope="feature" variant="feature" total={total} />
              ) : (
                <div className="case-group-empty">{`No ${label.toLowerCase()} were generated from the current evidence.`}</div>
              )}
            </div>
          </details>
        );
      })}
    </Fragment>
  );
}

/** The feature workspace (useWorkspace). */
export default function FeatureWorkspacePanel({ fs, ws }) {
  const f = ws.feature;
  const cl = ws.cl;
  const bar = (scope) => `case-bulk-toolbar${scope}${cl.count ? " show" : ""}`;
  const vers = f ? f.versions || [] : [];
  return (
    <div className="card stage-page" id="detail-card" hidden={fs.page !== "workspace"}>
      <div className="feature-workspace-head">
        <div>
          <button className="ghost" id="d-close" style={{ marginBottom: "10px" }} onClick={fs.showFeatureList}>
            Back to features
          </button>
          <h2 id="d-name">{f ? f.name : "Feature"}</h2>
        </div>
        <div className="workspace-actions">
          <span className="version-combo">
            <span className="version-chip" id="d-version-chip">
              {f ? `Version ${f.version || 1} · ${f.test_cases.length} cases` : "Version 1"}
            </span>
            <button className="new-version-btn" id="d-newver" title="Create new version" onClick={ws.newVersion}>
              +
            </button>
          </span>
          <select
            id="d-version"
            style={{ display: "none" }}
            value={f ? f.id : ""}
            onChange={(e) => ws.switchVersion(e.target.value)}
          >
            {vers.map((v) => (
              <option key={v.id} value={v.id}>
                {`v${v.version} · ${v.case_count} cases`}
              </option>
            ))}
          </select>
          <button className="ghost" id="d-reuse-imports" type="button" title="Reuse imported sheet tests" onClick={ws.reuseImported}>
            ↺ Reuse imported
          </button>
          <button id="d-export" className="export-btn" onClick={() => cl.bulkExport("pdf")}>
            Export PDF
          </button>
          <button id="d-export-csv" className="export-btn" type="button" onClick={() => cl.bulkExport("csv")}>
            Export CSV
          </button>
          <button className="ghost" id="d-jira" style={{ display: f && f.key ? "" : "none" }} onClick={ws.syncJira}>
            Sync to Jira
          </button>
          <button className="ghost" id="d-rename" style={{ display: "none" }} onClick={ws.rename}>
            Rename
          </button>
          <button className="danger" id="d-del" style={{ display: "none" }} onClick={ws.remove}>
            Delete feature
          </button>
        </div>
      </div>
      <div className="muted" id="d-meta"></div>
      <div id="d-match-key" className="muted" style={{ margin: "6px 0" }}>
        {f ? (
          <>
            <span title="PRs whose title/body contain [TAG] auto-map to this feature">PR match tag: </span>
            <input
              key={ws.view.seq}
              id="d-match-key-input"
              className="needs-editor"
              style={{ width: "130px" }}
              placeholder="e.g. HOLDS"
              defaultValue={f.match_key || ""}
            />{" "}
            <button
              className="ghost needs-editor"
              type="button"
              onClick={() => ws.saveMatchKey(document.getElementById("d-match-key-input")?.value || "")}
            >
              Save
            </button>{" "}
            <span id="d-match-key-status" className="muted">
              {ws.matchKeyStatus}
            </span>
          </>
        ) : null}
      </div>
      <div id="d-coverage">
        <Coverage ws={ws} />
      </div>
      <div id="d-overview">{f ? <Overview f={f} bt={ws.bt} /> : null}</div>
      <div id="d-verinfo">{f ? <VersionInfo f={f} /> : null}</div>
      <GenBanner banner={ws.banner} />
      <div className={bar("")} data-bulk-scope="feature">
        <div className="case-bulk-left">
          <span className="case-bulk-count" data-bulk-count="feature">
            {`${cl.count} selected`}
          </span>
        </div>
        <div className="case-bulk-actions">
          <button className="ghost bulk-pass" onClick={() => cl.bulkSetResult("passed")}>
            Pass selected
          </button>
          <button className="ghost bulk-fail" onClick={() => cl.bulkSetResult("failed")}>
            Fail selected
          </button>
          <button className="ghost" onClick={() => cl.bulkSetResult("untested")}>
            Clear status
          </button>
          <button className="ghost" onClick={() => cl.bulkExport("pdf")}>
            Export selected
          </button>
          <button className="testcase-delete" onClick={() => cl.bulkDelete()}>
            Delete selected
          </button>
        </div>
      </div>
      <div id="d-cases">
        <CaseGroups ws={ws} />
      </div>
      <div className={bar(" bulk-floating")} data-bulk-scope="feature-floating">
        <div className="case-bulk-left">
          <span className="badge" data-bulk-count="feature-floating">
            {cl.count}
          </span>
          <span className="case-bulk-count">selected</span>
        </div>
        <div className="case-bulk-actions">
          <button className="ghost" onClick={() => cl.bulkExport("pdf")}>
            Export selected
          </button>
          <button className="testcase-delete" onClick={() => cl.bulkDelete()}>
            Delete selected
          </button>
        </div>
      </div>
    </div>
  );
}
