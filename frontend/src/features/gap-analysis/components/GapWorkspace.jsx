import PrRuns from "./PrRuns.jsx";
import RunDetail from "./RunDetail.jsx";
import { AutoItems, AutoRepos } from "./AutoCoverage.jsx";

/** The Gap Analysis workspace: PR Code Coverage and Automation Test Coverage tabs (state: hooks/useGap.js). */
export default function GapWorkspace({ g }) {
  const { view, tab, live, list, detail, manual, auto, actions: a } = g;
  const tabBtn = (id, label) => (
    <button type="button" className={`cp-prov${tab === id ? " active" : ""}`} data-gap-tab={id} onClick={() => a.switchTab(id)}>
      {label}
    </button>
  );
  return (
    <div id="gap-workspace" style={{ display: view.hasFeature ? "block" : "none" }}>
      <div className="card" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "10px", padding: "14px 18px" }}>
        <h2 id="gap-feat-title" style={{ margin: "0", fontSize: "15px" }}>{view.title}</h2>
        <div className="cp-provider-toggle" style={{ margin: "0" }}>
          {tabBtn("pr", "PR Code Coverage")}
          {tabBtn("auto", "Automation Test Coverage")}
        </div>
      </div>
      {/* PR Code Coverage tab */}
      <div id="gap-tab-pr" style={{ display: tab === "pr" ? "block" : "none" }}>
        <div className="card">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "10px", flexWrap: "wrap" }}>
            <h3 style={{ margin: "0", fontSize: "14px" }}>
              PR Coverage runs
              <span id="gap-pr-live" style={{ marginLeft: "6px", fontWeight: "400" }}>
                {live ? <span className="badge functional">⏳ gap analysis running…</span> : null}
              </span>
            </h3>
            <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
              <button className="ghost" id="gap-pr-export-csv" type="button" title="Export PR coverage as CSV" onClick={() => a.exportReport("pr-coverage", "csv")}>Export CSV</button>
              <button className="ghost" id="gap-pr-export-pdf" type="button" title="Export PR coverage as PDF" onClick={() => a.exportReport("pr-coverage", "pdf")}>Export PDF</button>
              <button className="ghost" id="gap-pr-refresh" type="button" onClick={a.refreshRuns}>Refresh</button>
              <button className="go" id="gap-pr-manual" type="button" disabled={manual.busy} onClick={a.runManual}>{manual.label}</button>
            </div>
          </div>
          <div className="sub" style={{ margin: "6px 0 12px" }}>Webhooks register on App repos at project setup. Each PR open/sync/reopen creates a run. You can also trigger a one-off run by PR number below.</div>
          <PrRuns list={list} onOpen={a.openRun} onExclude={a.setExcluded} />
        </div>
        <div className="card" id="gap-pr-detail" style={{ display: detail.open ? "block" : "none" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "10px" }}>
            <h3 style={{ margin: "0", fontSize: "14px" }} id="gap-pr-detail-title">{detail.title}</h3>
            <button className="ghost" id="gap-pr-detail-close" type="button" onClick={a.closeRun}>Close</button>
          </div>
          <RunDetail body={detail.body} onReassign={a.reassign} />
        </div>
      </div>
      {/* Automation Coverage tab */}
      <div id="gap-tab-auto" style={{ display: tab === "auto" ? "block" : "none" }}>
        <div className="card">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "10px", flexWrap: "wrap" }}>
            <h3 style={{ margin: "0", fontSize: "14px" }}>Automation Test Coverage</h3>
            <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
              <span className="muted" id="gap-auto-summary" style={{ fontSize: "12px" }}>{auto.summary}</span>
              <button className="ghost" id="gap-auto-export-csv" type="button" title="Export automation coverage as CSV" onClick={() => a.exportReport("automation", "csv")}>Export CSV</button>
              <button className="ghost" id="gap-auto-export-pdf" type="button" title="Export automation coverage as PDF" onClick={() => a.exportReport("automation", "pdf")}>Export PDF</button>
              <button className="ghost" id="gap-auto-refresh" type="button" onClick={a.refreshAuto}>Refresh</button>
            </div>
          </div>
          <div className="sub" style={{ margin: "6px 0 12px" }}>
            For each generated test case, wardenIQ finds the best-matching test in your connected{" "}
            <b>Test</b>{" "}
            repos (Playwright, Cypress, Cucumber, Jest, Pytest, Markdown, JSON, etc.) using a Jaccard prefilter + LLM verifier. Covered tests link to the exact file at the scanned commit.
          </div>
          <AutoRepos repos={auto.repos} onRescan={a.rescan} onReset={a.resetScan} />
          <div id="gap-auto-stats" style={{ display: auto.showStats ? "block" : "none" }}>
            <div className="kpis" style={{ marginBottom: "14px" }}>
              <div className="kpi">
                <div className="v accent" id="gap-auto-pct">{auto.scan ? (auto.scan.coverage_pct ?? 0) + "%" : "—"}</div>
                <div className="l">Automation Test Coverage</div>
              </div>
              <div className="kpi">
                <div className="v" id="gap-auto-covered">{auto.scan ? auto.scan.covered_count ?? 0 : "—"}</div>
                <div className="l">Covered</div>
              </div>
              <div className="kpi">
                <div className="v" id="gap-auto-missing">{auto.scan ? auto.scan.missing_count ?? 0 : "—"}</div>
                <div className="l">Missing</div>
              </div>
              <div className="kpi">
                <div className="v" id="gap-auto-total">{auto.scan ? auto.scan.total_generated ?? 0 : "—"}</div>
                <div className="l">Generated cases</div>
              </div>
            </div>
            <AutoItems scan={auto.scan} seq={auto.seq} />
          </div>
        </div>
      </div>
    </div>
  );
}
