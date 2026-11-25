import { useEffect, useRef } from "react";

import { SkeletonBlockLines, SkeletonRows, SkeletonState } from "../../../components/feedback/Skeleton.jsx";
import { requestDeleteCase } from "../../../lib/compatBridge.js";
import CaseDetail from "./CaseDetail.jsx";
import PriorityBadge from "./PriorityBadge.jsx";

export { PriorityBadge };
import { RESULT_OPTIONS, caseSubText, caseTitle, lineageBadge } from "../lib/testCases.js";

/*
 * Rows keep the classes and data attributes of the old HTML (`.open`,
 * [data-case-detail], `.case-select[data-case-id]`, the result <select>
 * classes). Row behaviour — open detail, result, selection — comes from
 * useCaseList; every load remounts the rows, as the old innerHTML did.
 */

const stop = (e) => e.stopPropagation();

function ResultSelect({ testCase, cl }) {
  const r = cl.resultOf(testCase);
  return (
    <select
      className={r.cls}
      aria-label="Latest execution result"
      value={r.value}
      disabled={r.busy}
      onClick={stop}
      onChange={(e) => cl.setResult(testCase, e.target.value)}
    >
      {RESULT_OPTIONS.map(([value, label]) => (
        <option key={value} value={value}>
          {label}
        </option>
      ))}
    </select>
  );
}

/** The detail panel under an open row. */
function RowDetail({ id, cl }) {
  const d = cl.details[id];
  if (!d) return null;
  if (d.status === "loading")
    return (
      <SkeletonState label="Loading test case details">
        <SkeletonBlockLines count={3} />
      </SkeletonState>
    );
  if (d.status === "error") return <div className="err">{d.error}</div>;
  return <CaseDetail testCase={d.data} onClose={cl.closeDetail} />;
}

function CaseRow({ testCase: c, cl }) {
  const title = caseTitle(c);
  const badge = lineageBadge(c);
  return (
    <div
      className={`testcase-item${cl.open === c.id ? " open" : ""}`}
      data-case-item={c.id}
      style={c.deprecated ? { opacity: 0.6 } : undefined}
    >
      <div className="testcase-row" onClick={() => cl.toggleDetail(c.id)}>
        <input
          className="case-select"
          data-case-id={c.id}
          type="checkbox"
          aria-label={`Select ${title}`}
          checked={cl.selected.has(c.id)}
          onChange={(e) => cl.toggle(c.id, e.target.checked)}
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
        <ResultSelect testCase={c} cl={cl} />
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
      <div className="testcase-detail" data-case-detail={c.id}>
        <RowDetail id={c.id} cl={cl} />
      </div>
    </div>
  );
}

function CaseListHeader({ cl, total, scope }) {
  const ref = useRef(null);
  const all = total > 0 && cl.count === total;
  const some = cl.count > 0 && cl.count < total;
  useEffect(() => {
    if (ref.current) ref.current.indeterminate = some;
  }, [some]);
  return (
    <div className="case-list-head">
      <input
        ref={ref}
        type="checkbox"
        className="case-select case-select-all"
        data-bulk-scope={scope}
        title="Select all visible test cases"
        aria-label="Select all visible test cases"
        checked={all}
        onChange={(e) => cl.toggleAll(e.target.checked)}
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

/** Header and rows of a case list (Test Cases screen; the feature workspace groups). */
export function CaseRows({ items, cl, scope = "cases" }) {
  return (
    <>
      <CaseListHeader cl={cl} total={items.length} scope={scope} />
      {items.map((c) => (
        <CaseRow key={c.id} testCase={c} cl={cl} />
      ))}
    </>
  );
}

/** Contents of #tc-list: skeleton, rows, empty text or the error state. */
export function CaseList({ status, items, error, seq, onRetry, cl }) {
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
      <CaseRows items={items} cl={cl} />
    </div>
  );
}

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
