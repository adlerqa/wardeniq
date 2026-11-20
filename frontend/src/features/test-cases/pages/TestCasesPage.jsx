/**
 * TestCasesPage
 *
 * Structural React port of the original static screen markup.
 * Data loading and mutation behavior is currently supplied by the domain
 * compatibility controllers under src/compat/runtime/controllers.
 * Keeping the DOM contract here lets the UI be migrated screen-by-screen
 * without a single monolithic HTML template.
 */
export default function TestCasesPage() {
  return (
    <section id="view-cases" className="view" hidden>
      <div className="card">
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
          }}
        >
          <h2 style={{ margin: "0" }}>Test Cases</h2>
          <button className="go" id="tc-new">
            + New test case
          </button>
        </div>
        <div className="sub">
          Open a title to review its full specification. Editing is a separate
          action; shared-step changes are called out before saving.
        </div>
        <div className="case-filter-panel">
          {/* Primary filters */}
          <div className="case-filter-primary">
            <div className="case-filter-field">
              <label htmlFor="tc-feat">Feature</label>

              <select id="tc-feat">
                <option value="">All features</option>
              </select>
            </div>

            <div className="case-filter-field">
              <label htmlFor="tc-type">Category</label>

              <select id="tc-type">
                <option value="">All categories</option>
                <option value="functional">Business / functional</option>
                <option value="e2e">End-to-end</option>
                <option value="api">API</option>
                <option value="ui">UI validations</option>
                <option value="nfr">Edge &amp; reliability</option>
              </select>
            </div>

            <div className="case-filter-field case-filter-search">
              <label htmlFor="tc-q">Search</label>

              <div className="case-search-wrap">
                

                <input id="tc-q" placeholder="Search by title or ID..." />
              </div>
            </div>

            <div className="filter-actions">
              <button type="button" className="go" id="tc-apply">
                Apply filters
              </button>

              <button type="button" className="ghost" id="tc-reset">
                Reset
              </button>
            </div>
          </div>

          {/* Secondary filters */}
          <details className="case-filter-more">
            <summary>
              <span>More filters</span>

              <svg
                className="case-filter-chevron"
                viewBox="0 0 24 24"
                width="14"
                height="14"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <path d="m6 9 6 6 6-6" />
              </svg>
            </summary>

            <div className="case-filter-grid">
              <div className="case-filter-field">
                <label htmlFor="tc-tag">Tag</label>

                <select id="tc-tag">
                  <option value="">Any tag</option>
                </select>
              </div>

              <div className="case-filter-field">
                <label htmlFor="tc-status">Status</label>

                <select id="tc-status" defaultValue="active">
                  <option value="active">Active test cases</option>

                  <option value="deprecated">Deprecated only</option>

                  <option value="all">Active + deprecated</option>
                </select>
              </div>

              <div className="case-filter-field">
                <label htmlFor="tc-result">Execution result</label>

                <select id="tc-result">
                  <option value="">Any result</option>
                  <option value="untested">Untested</option>
                  <option value="passed">Passed</option>
                  <option value="failed">Failed</option>
                  <option value="blocked">Blocked</option>
                </select>
              </div>

              <div className="case-filter-field">
                <label htmlFor="tc-lineage">Reuse</label>

                <select id="tc-lineage">
                  <option value="">Generated + reused</option>

                  <option value="inherited">Inherited / reused only</option>

                  <option value="created">Created in selected feature</option>
                </select>
              </div>
            </div>
          </details>
        </div>
        <div className="filter-summary" id="tc-summary"></div>
        <div className="case-bulk-toolbar" data-bulk-scope="cases">
          <div className="case-bulk-left">
            <span className="case-bulk-count" data-bulk-count="cases">
              0 selected
            </span>
          </div>
          <div className="case-bulk-actions">
            <button
              className="ghost bulk-pass"
              onClick={() => window.bulkSetCaseResult?.("passed")}
            >
              Pass selected
            </button>
            <button
              className="ghost bulk-fail"
              onClick={() => window.bulkSetCaseResult?.("failed")}
            >
              Fail selected
            </button>
            <button
              className="ghost"
              onClick={() => window.bulkSetCaseResult?.("untested")}
            >
              Clear status
            </button>
            <button
              className="ghost"
              onClick={() => window.bulkExportSelected?.("pdf")}
            >
              Export selected
            </button>
            <button
              className="testcase-delete"
              onClick={() => window.bulkDeleteSelected?.()}
            >
              Delete selected
            </button>
          </div>
        </div>
        <div id="tc-list" style={{ marginTop: "12px" }}></div>
        <div
          className="case-bulk-toolbar bulk-floating"
          data-bulk-scope="cases-floating"
        >
          <div className="case-bulk-left">
            <span className="badge" data-bulk-count="cases-floating">
              0
            </span>
            <span className="case-bulk-count">selected</span>
          </div>
          <div className="case-bulk-actions">
            <button
              className="ghost"
              onClick={() => window.bulkExportSelected?.("pdf")}
            >
              Export selected
            </button>
            <button
              className="testcase-delete"
              onClick={() => window.bulkDeleteSelected?.()}
            >
              Delete selected
            </button>
          </div>
        </div>
        <div className="pager" id="tc-pager"></div>
      </div>
    </section>
  );
}
