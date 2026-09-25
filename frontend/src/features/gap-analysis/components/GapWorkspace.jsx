/** GapWorkspace for gap-analysis. */
export default function GapWorkspace() {
  return (
    <div id="gap-workspace" style={{ display: "none" }}>
      <div className="card" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "10px", padding: "14px 18px" }}>
        <h2 id="gap-feat-title" style={{ margin: "0", fontSize: "15px" }}>Gap Analysis</h2>
        <div className="cp-provider-toggle" style={{ margin: "0" }}>
          <button type="button" className="cp-prov active" data-gap-tab="pr">PR Code Coverage</button>
          <button type="button" className="cp-prov" data-gap-tab="auto">Automation Test Coverage</button>
        </div>
      </div>
      {/* PR Code Coverage tab */}
      <div id="gap-tab-pr">
        <div className="card">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "10px", flexWrap: "wrap" }}>
            <h3 style={{ margin: "0", fontSize: "14px" }}>
              PR Coverage runs
              <span id="gap-pr-live" style={{ marginLeft: "6px", fontWeight: "400" }}></span>
            </h3>
            <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
              <button className="ghost" id="gap-pr-export-csv" type="button" title="Export PR coverage as CSV">Export CSV</button>
              <button className="ghost" id="gap-pr-export-pdf" type="button" title="Export PR coverage as PDF">Export PDF</button>
              <button className="ghost" id="gap-pr-refresh" type="button">Refresh</button>
              <button className="go" id="gap-pr-manual" type="button">+ Run on a PR</button>
            </div>
          </div>
          <div className="sub" style={{ margin: "6px 0 12px" }}>Webhooks register on App repos at project setup. Each PR open/sync/reopen creates a run. You can also trigger a one-off run by PR number below.</div>
          <div id="gap-pr-list" className="muted">
            No runs yet — connect a repo on this project and open a PR (or click{" "}
            <b>+ Run on a PR</b>
            ).
          </div>
        </div>
        <div className="card" id="gap-pr-detail" style={{ display: "none" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "10px" }}>
            <h3 style={{ margin: "0", fontSize: "14px" }} id="gap-pr-detail-title">Run detail</h3>
            <button className="ghost" id="gap-pr-detail-close" type="button">Close</button>
          </div>
          <div id="gap-pr-detail-body"></div>
        </div>
      </div>
      {/* Automation Coverage tab */}
      <div id="gap-tab-auto" style={{ display: "none" }}>
        <div className="card">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "10px", flexWrap: "wrap" }}>
            <h3 style={{ margin: "0", fontSize: "14px" }}>Automation Test Coverage</h3>
            <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
              <span className="muted" id="gap-auto-summary" style={{ fontSize: "12px" }}></span>
              <button className="ghost" id="gap-auto-export-csv" type="button" title="Export automation coverage as CSV">Export CSV</button>
              <button className="ghost" id="gap-auto-export-pdf" type="button" title="Export automation coverage as PDF">Export PDF</button>
              <button className="ghost" id="gap-auto-refresh" type="button">Refresh</button>
            </div>
          </div>
          <div className="sub" style={{ margin: "6px 0 12px" }}>
            For each generated test case, wardenIQ finds the best-matching test in your connected{" "}
            <b>Test</b>{" "}
            repos (Playwright, Cypress, Cucumber, Jest, Pytest, Markdown, JSON, etc.) using a Jaccard prefilter + LLM verifier. Covered tests link to the exact file at the scanned commit.
          </div>
          <div id="gap-auto-repos" style={{ display: "flex", flexDirection: "column", gap: "8px", marginBottom: "14px" }}></div>
          <div id="gap-auto-stats" style={{ display: "none" }}>
            <div className="kpis" style={{ marginBottom: "14px" }}>
              <div className="kpi">
                <div className="v accent" id="gap-auto-pct">—</div>
                <div className="l">Automation Test Coverage</div>
              </div>
              <div className="kpi">
                <div className="v" id="gap-auto-covered">—</div>
                <div className="l">Covered</div>
              </div>
              <div className="kpi">
                <div className="v" id="gap-auto-missing">—</div>
                <div className="l">Missing</div>
              </div>
              <div className="kpi">
                <div className="v" id="gap-auto-total">—</div>
                <div className="l">Generated cases</div>
              </div>
            </div>
            <div id="gap-auto-items"></div>
          </div>
        </div>
      </div>
    </div>
  );
}
