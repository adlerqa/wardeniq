import { useRef } from "react";

import { CaseList, CasePager } from "../components/CaseList.jsx";
import useCaseList from "../hooks/useCaseList.js";
import useTestCases from "../hooks/useTestCases.js";
import { projectOptionLabel } from "../lib/testCases.js";
import { openNewCase, toast } from "../../../lib/compatBridge.js";

/**
 * TestCasesPage — filters, list, summary and pager are React (see
 * useTestCases); row detail, results, selection and bulk actions come from
 * useCaseList; "+ New test case" opens the React case editor. The filter id
 * tc-feat is still read by the case delete dialog.
 */
export default function TestCasesPage() {
  const tc = useTestCases();
  const { filters, changeFilter } = tc;
  const onSelect = (key) => (e) => changeFilter(key, e.target.value);

  const featureRef = useRef("");
  featureRef.current = filters.feature;
  // Row detail, results, ticked rows and bulk actions; a reload clears them.
  const cl = useCaseList(tc.list.items, tc.list.seq, { feature: () => featureRef.current, reload: tc.reload });
  const bar = (scope) => `case-bulk-toolbar${scope}${cl.count ? " show" : ""}`;

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
          <button
            className="go"
            id="tc-new"
            onClick={() =>
              filters.feature
                ? openNewCase(filters.feature)
                : toast("Pick a Feature filter first, so the new case is added to it", true)
            }
          >
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
              <label htmlFor="tc-proj">Project</label>

              <select id="tc-proj" value={filters.project} onChange={onSelect("project")}>
                <option value="">All projects</option>
                {tc.projects.map((p) => (
                  <option key={p.id} value={p.id}>
                    {projectOptionLabel(p)}
                  </option>
                ))}
              </select>
            </div>

            <div className="case-filter-field">
              <label htmlFor="tc-feat">Feature</label>

              <select id="tc-feat" value={filters.feature} onChange={onSelect("feature")}>
                <option value="">All features</option>
                {tc.features.map((f) => (
                  <option key={f.id} value={f.id}>
                    {f.name}
                  </option>
                ))}
              </select>
            </div>

            <div className="case-filter-field">
              <label htmlFor="tc-type">Category</label>

              <select id="tc-type" value={filters.type} onChange={onSelect("type")}>
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
                

                <input
                  id="tc-q"
                  placeholder="Search by title or ID..."
                  value={filters.q}
                  onChange={(e) => tc.setQuery(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") tc.apply();
                  }}
                />
              </div>
            </div>

            <div className="filter-actions">
              <button type="button" className="go" id="tc-apply" onClick={tc.apply}>
                Apply filters
              </button>

              <button type="button" className="ghost" id="tc-reset" onClick={tc.reset}>
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

                <select id="tc-tag" value={filters.tag} onChange={onSelect("tag")}>
                  <option value="">Any tag</option>
                  {tc.tags.map((t) => (
                    <option key={t} value={t}>
                      {t}
                    </option>
                  ))}
                </select>
              </div>

              <div className="case-filter-field">
                <label htmlFor="tc-status">Status</label>

                <select id="tc-status" value={filters.status} onChange={onSelect("status")}>
                  <option value="active">Active test cases</option>

                  <option value="deprecated">Deprecated only</option>

                  <option value="all">Active + deprecated</option>
                </select>
              </div>

              <div className="case-filter-field">
                <label htmlFor="tc-result">Execution result</label>

                <select id="tc-result" value={filters.result} onChange={onSelect("result")}>
                  <option value="">Any result</option>
                  <option value="untested">Untested</option>
                  <option value="passed">Passed</option>
                  <option value="failed">Failed</option>
                  <option value="blocked">Blocked</option>
                </select>
              </div>

              <div className="case-filter-field">
                <label htmlFor="tc-lineage">Reuse</label>

                <select id="tc-lineage" value={filters.lineage} onChange={onSelect("lineage")}>
                  <option value="">Generated + reused</option>

                  <option value="inherited">Inherited / reused only</option>

                  <option value="created">Created in selected feature</option>
                </select>
              </div>
            </div>
          </details>
        </div>
        <div className="filter-summary" id="tc-summary">
          {tc.summary}
        </div>
        <div className={bar("")} data-bulk-scope="cases">
          <div className="case-bulk-left">
            <span className="case-bulk-count" data-bulk-count="cases">
              {`${cl.count} selected`}
            </span>
          </div>
          <div className="case-bulk-actions">
            <button
              className="ghost bulk-pass"
              onClick={() => cl.bulkSetResult("passed")}
            >
              Pass selected
            </button>
            <button
              className="ghost bulk-fail"
              onClick={() => cl.bulkSetResult("failed")}
            >
              Fail selected
            </button>
            <button
              className="ghost"
              onClick={() => cl.bulkSetResult("untested")}
            >
              Clear status
            </button>
            <button
              className="ghost"
              onClick={() => cl.bulkExport("pdf")}
            >
              Export selected
            </button>
            <button
              className="testcase-delete"
              onClick={() => cl.bulkDelete()}
            >
              Delete selected
            </button>
          </div>
        </div>
        <div id="tc-list" style={{ marginTop: "12px" }}>
          <CaseList
            status={tc.list.status}
            items={tc.list.items}
            error={tc.list.error}
            seq={tc.list.seq}
            onRetry={tc.reload}
            cl={cl}
          />
        </div>
        <div className={bar(" bulk-floating")} data-bulk-scope="cases-floating">
          <div className="case-bulk-left">
            <span className="badge" data-bulk-count="cases-floating">
              {cl.count}
            </span>
            <span className="case-bulk-count">selected</span>
          </div>
          <div className="case-bulk-actions">
            <button
              className="ghost"
              onClick={() => cl.bulkExport("pdf")}
            >
              Export selected
            </button>
            <button
              className="testcase-delete"
              onClick={() => cl.bulkDelete()}
            >
              Delete selected
            </button>
          </div>
        </div>
        <div className="pager" id="tc-pager">
          <CasePager pager={tc.pager} onPrev={tc.prevPage} onNext={tc.nextPage} />
        </div>
      </div>
    </section>
  );
}
