import { useEffect, useRef } from "react";

import { editCase } from "../../../lib/compatBridge.js";
import { PriorityBadge } from "../../test-cases/components/CaseList.jsx";
import { prioLabel } from "../../test-cases/lib/testCases.js";
import { ITEM_STATUSES, cycleProgress, dateOnly, needsInlineEditor, normalizeSteps, scheduleBadge } from "../lib/cycles.js";

/** The canonical # / Step / Expected result table (also used by Gap Analysis). */
export function StepsTable({ steps }) {
  const rows = normalizeSteps(steps);
  if (!rows.length) return null;
  return (
    <div className="case-steps-table" style={{ margin: "8px 0 2px" }}>
      <div className="case-step case-step-head">
        <span>#</span>
        <span>Step</span>
        <span>Expected result</span>
      </div>
      {rows.map((s, i) => (
        <div key={i} className="case-step">
          <span className="case-step-num">{`${i + 1}.`}</span>
          <span>{s.action}</span>
          <span className="case-step-expected">{s.expected || "No separate expected result"}</span>
        </div>
      ))}
    </div>
  );
}

const statusPill = (st) => <span className={`cycle-status-pill ${st || "pending"}`}>{st || "pending"}</span>;

function CycleItem({ c, it, tc }) {
  const editing = tc.edit.itemId === it.id;
  const draft = editing ? tc.edit.draft || {} : {};
  const status = editing ? draft.status || it.execution_status || "pending" : it.execution_status || "pending";
  const actual = editing ? (draft.actual_result ?? it.actual_result ?? "") : it.actual_result || "";
  const notes = editing ? (draft.notes ?? it.notes ?? "") : it.notes || "";
  const defect = editing ? (draft.defect_link ?? it.defect_link ?? "") : it.defect_link || "";
  const showEditor = editing || needsInlineEditor(it, tc.edit.itemId);
  const change = (field, value) => (editing ? tc.updateDraft(field, value) : tc.beginEdit(it, field, value));
  return (
    <div className={`cycle-exec-item status-${status}`}>
      <div className="cycle-exec-head">
        <div className="cycle-exec-order">{it.display_order || ""}</div>
        <div>
          <div className="cycle-exec-title">
            {it.display_id ? (
              <code
                style={{
                  fontSize: "10px",
                  background: "rgba(255,255,255,.06)",
                  padding: "1px 6px",
                  borderRadius: "4px",
                  color: "#94a3b8",
                  marginRight: "6px",
                }}
              >
                {it.display_id}
              </code>
            ) : null}
            {it.title}
          </div>
          <div className="cycle-exec-sub">
            <span className={`badge ${it.category}`}>{it.category || ""}</span>
            {it.priority ? <PriorityBadge priority={it.priority} /> : null}
            {statusPill(status)}
            {it.case_id ? (
              <button
                className="ghost"
                style={{ padding: "1px 9px", fontSize: "10.5px" }}
                onClick={(e) => {
                  e.stopPropagation();
                  editCase(it.case_id);
                }}
              >
                Edit case
              </button>
            ) : null}
          </div>
          <StepsTable steps={it.steps} />
        </div>
        <div className="cycle-exec-priority muted">{it.priority ? prioLabel(it.priority) : ""}</div>
        <div className="cycle-exec-status">
          <select value={status} onChange={(e) => tc.changeItemStatus(c.id, it.id, e.target.value)} style={{ width: "100%" }}>
            {ITEM_STATUSES.map((s) => (
              <option key={s}>{s}</option>
            ))}
          </select>
        </div>
      </div>
      {!showEditor && (actual || notes || defect) ? (
        <div className="cycle-exec-notes">
          <div>{actual || notes}</div>
          {defect ? (
            <div style={{ marginTop: "4px" }}>
              <a href={defect} target="_blank" rel="noopener noreferrer">
                Open defect link
              </a>
            </div>
          ) : null}
        </div>
      ) : null}
      {showEditor ? (
        <div className="cycle-exec-editor">
          <div className="cycle-exec-editor-grid">
            <div className="full">
              <label>Execution result</label>
              <textarea value={actual} onChange={(e) => change("actual_result", e.target.value)} />
            </div>
            <div className="full">
              <label>Notes</label>
              <textarea value={notes} onChange={(e) => change("notes", e.target.value)} />
            </div>
            <div className="full">
              <label>Defect link</label>
              <input
                value={defect}
                placeholder="https://…"
                onChange={(e) => change("defect_link", e.target.value)}
              />
            </div>
          </div>
          <div className="cycle-exec-actions">
            <button className="ghost" onClick={tc.cancelEdit}>
              Cancel
            </button>
            <button className="go" onClick={() => tc.saveEdit(c.id, it.id)}>
              Save status
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}

/** The open cycle: progress, actions, schedule and the items to execute. */
export default function TestCycleDetailPanel({ tc }) {
  const cardRef = useRef(null);
  const c = tc.detail;
  // The old screen scrolled to the card on every redraw of the cycle.
  useEffect(() => {
    if (tc.renderSeq && cardRef.current && cardRef.current.scrollIntoView)
      cardRef.current.scrollIntoView({ behavior: "smooth" });
  }, [tc.renderSeq]);

  let body = null;
  if (c) {
    const cc = c.counts || {};
    const { pct } = cycleProgress(c);
    const today = new Date().toISOString().slice(0, 10);
    const start = dateOnly(c.scheduled_start_at);
    const end = dateOnly(c.scheduled_end_at);
    const badge = scheduleBadge(start, end, today);
    const kpi = (v, label) => (
      <div className="cycle-detail-kpi">
        <b>{v}</b>
        <span>{label}</span>
      </div>
    );
    body = (
      <>
        <div className="muted" style={{ margin: "8px 0" }}>
          {`${c.description || ""} `}
          {c.environment ? (
            <>
              · env <b>{c.environment}</b>
            </>
          ) : null}{" "}
          {c.build_version ? (
            <>
              · build <b>{c.build_version}</b>
            </>
          ) : null}
        </div>
        <div className="progress">
          <div className="pbar" style={{ width: `${pct}%` }}></div>
        </div>
        <div className="cycle-detail-summary">
          {kpi(c.total || 0, "Total cases")}
          {kpi(cc.passed || 0, "Passed")}
          {kpi(cc.failed || 0, "Failed")}
          {kpi(cc.blocked || 0, "Blocked")}
          {kpi(`${pct}%`, "Progress")}
        </div>
        <div className="cycle-detail-actions">
          <a className="export-btn" href={`/api/test-cycles/${c.id}/export/csv`}>
            Export CSV
          </a>
          <a className="export-btn" href={`/api/test-cycles/${c.id}/export/pdf`}>
            Export PDF
          </a>
          <button className="ghost" onClick={() => tc.showReport(c.id)}>
            View summary
          </button>
          <button className="ghost" onClick={() => tc.editDescription(c.id)}>
            Edit description
          </button>
          <button className="ghost" onClick={() => tc.saveAsTemplate(c.id)}>
            Save as template
          </button>
        </div>
        <div className="cycle-detail-actions" style={{ marginTop: "10px", alignItems: "center", flexWrap: "wrap", gap: "12px" }}>
          <label className="muted" style={{ fontSize: "12px", display: "flex", alignItems: "center", gap: "6px" }}>
            Start{" "}
            <input
              type="date"
              id="cyc-start"
              value={start}
              min={today}
              onChange={(e) => tc.schedule(c.id, "scheduled_start_at", e.target.value)}
              style={{ width: "auto", padding: "4px 8px" }}
            />
          </label>
          <label className="muted" style={{ fontSize: "12px", display: "flex", alignItems: "center", gap: "6px" }}>
            End{" "}
            <input
              type="date"
              id="cyc-end"
              value={end}
              min={start || today}
              onChange={(e) => tc.schedule(c.id, "scheduled_end_at", e.target.value)}
              style={{ width: "auto", padding: "4px 8px" }}
            />
          </label>
          {badge ? <span className={badge.cls}>{badge.text}</span> : null}
          <button className="go" style={{ padding: "5px 12px", marginLeft: "auto" }} onClick={() => tc.openChooser(c.id)}>
            + Add test cases
          </button>
        </div>
        <div className="cycle-exec-list">
          {(c.items || []).map((it) => (
            <CycleItem key={`${tc.renderSeq}:${it.id}`} c={c} it={it} tc={tc} />
          ))}
        </div>
      </>
    );
  }

  return (
    <div className="card" id="cyc-detail-card" ref={cardRef} style={{ display: tc.shown ? "block" : "none" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h2 id="cyc-d-name" style={{ margin: "0" }}>
          {c ? (
            <>
              {c.name} <span className="badge">{c.status || "draft"}</span>
            </>
          ) : (
            "Cycle"
          )}
        </h2>
        <div style={{ display: "flex", gap: "6px" }}>
          <button className="ghost" id="cyc-d-rename" onClick={tc.rename}>
            Rename
          </button>
          <button className="danger" id="cyc-d-del" onClick={tc.remove}>
            Delete cycle
          </button>
          <button className="ghost" id="cyc-d-close" onClick={tc.close}>
            Close
          </button>
        </div>
      </div>
      <div id="cyc-d-items">{body}</div>
    </div>
  );
}
