import { memo } from "react";

import { SkeletonRows } from "../../../components/feedback/Skeleton.jsx";
import {
  requestDeleteCase,
  setCaseResult,
  viewCase,
} from "../../../lib/compatBridge.js";
import {
  PRIO_COLORS,
  RESULT_OPTIONS,
  caseSubText,
  caseTitle,
  lineageBadge,
  prioKey,
  prioLabel,
} from "../lib/testCases.js";

/*
 * Rows keep the classes and data attributes of the old HTML because the compat
 * runtime still works on them: viewCase() toggles `.open` and fills
 * [data-case-detail], setCaseResult() restyles the <select>, and the bulk bar
 * (03-features-and-usage.js) reads the `.case-select[data-case-id]` boxes.
 * React never re-renders those parts after mount (the props do not change),
 * and every load remounts the rows, as the old innerHTML did.
 */

const stop = (e) => e.stopPropagation();

export function PriorityBadge({ priority }) {
  const [border, background, color] = PRIO_COLORS[prioKey(priority)];
  return (
    <span
      style={{
        fontSize: "10px",
        fontWeight: 600,
        padding: "2px 8px",
        borderRadius: "999px",
        border: `1px solid ${border}`,
        background,
        color,
      }}
    >
      {prioLabel(priority)}
    </span>
  );
}

function ResultSelect({ testCase }) {
  const status = testCase.execution_status || "untested";
  return (
    <select
      className={`result-select needs-editor ${status}`}
      aria-label="Latest execution result"
      defaultValue={status}
      onClick={stop}
      onChange={(e) => setCaseResult(testCase.id, e.target.value, e.target)}
    >
      {RESULT_OPTIONS.map(([value, label]) => (
        <option key={value} value={value}>
          {label}
        </option>
      ))}
    </select>
  );
}

function CaseRow({ testCase: c }) {
  const title = caseTitle(c);
  const badge = lineageBadge(c);
  return (
    <div className="testcase-item" data-case-item={c.id} style={c.deprecated ? { opacity: 0.6 } : undefined}>
      <div className="testcase-row" onClick={(e) => viewCase(c.id, e.currentTarget)}>
        <input
          className="case-select"
          data-case-id={c.id}
          type="checkbox"
          aria-label={`Select ${title}`}
          onClick={stop}
        />
        <span className="testcase-chevron">›</span>
        <div>
          <div className="testcase-title">
            {c.display_id ? (
              <span className="badge" style={{ marginRight: "7px" }}>
                {c.display_id}
              </span>
            ) : null}
            {title}
            {badge ? (
              <span
                className="badge reused"
                style={{ marginLeft: "7px" }}
                title={
                  badge.kind === "imported"
                    ? "This test case came from an uploaded sheet (imported / reused across features)"
                    : undefined
                }
              >
                {badge.label}
              </span>
            ) : null}
          </div>
          <div className="testcase-sub">{caseSubText(c)}</div>
        </div>
        <ResultSelect testCase={c} />
        <span className="testcase-priority">
          <PriorityBadge priority={c.priority} />
        </span>
        <button
          className="testcase-delete needs-editor"
          title="Delete testcase"
          aria-label="Delete testcase"
          onClick={(e) => {
            e.stopPropagation();
            requestDeleteCase(c.id);
          }}
        >
          <span>Delete</span>
        </button>
      </div>
      <div className="testcase-detail" data-case-detail={c.id}></div>
    </div>
  );
}

function CaseListHeader() {
  return (
    <div className="case-list-head">
      <input
        type="checkbox"
        className="case-select case-select-all"
        data-bulk-scope="cases"
        title="Select all visible test cases"
        aria-label="Select all visible test cases"
        onClick={stop}
      />
      <span></span>
      <span>Test case</span>
      <span>Result</span>
      <span>Priority</span>
      <span>Action</span>
    </div>
  );
}

/** Contents of #tc-list: skeleton, rows, empty text or the error state. */
export const CaseList = memo(function CaseList({ status, items, error, seq, onRetry }) {
  if (status === "idle") return null;
  if (status === "loading") return <SkeletonRows count={8} label="Loading test cases" />;
  if (status === "error")
    return (
      <div className="empty-state">
        <div className="empty-state-icon">!</div>
        <h3>Couldn&apos;t load test cases</h3>
        <p>{error}</p>
        <button className="ghost" onClick={onRetry}>
          Retry
        </button>
      </div>
    );
  if (!items.length) return <span className="muted">No test cases match the selected filters.</span>;
  return (
    <div className="testcase-list" key={seq}>
      <CaseListHeader />
      {items.map((c) => (
        <CaseRow key={c.id} testCase={c} />
      ))}
    </div>
  );
});

/** Contents of #tc-pager. */
export function CasePager({ pager, onPrev, onNext }) {
  if (!pager) return null;
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        gap: "14px",
        margin: "16px 0 4px",
      }}
    >
      <button
        className="go"
        id="tcp"
        disabled={pager.page <= 0}
        style={{ flex: "0 0 auto", padding: "6px 16px" }}
        onClick={onPrev}
      >
        ‹ Prev
      </button>
      <span className="muted" style={{ fontSize: "12.5px", whiteSpace: "nowrap" }}>
        {pager.total} cases · page {pager.page + 1} of {pager.pages}
      </span>
      <button
        className="go"
        id="tcn"
        disabled={pager.page >= pager.pages - 1}
        style={{ flex: "0 0 auto", padding: "6px 16px" }}
        onClick={onNext}
      >
        Next ›
      </button>
    </div>
  );
}
