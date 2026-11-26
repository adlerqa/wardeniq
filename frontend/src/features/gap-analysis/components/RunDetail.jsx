import { useState } from "react";
import PriorityBadge from "../../test-cases/components/PriorityBadge.jsx";
import { StepsTable } from "../../test-cycles/components/TestCycleDetailPanel.jsx";
import { skeleton } from "../../../lib/skeleton.js";
import { runDetail, typeTitle } from "../lib/gap.js";

const ACTIVE = { background: "#35507a", color: "#d5e5ff" };
const IDLE = { background: "transparent", color: "var(--muted)" };
const BADGE = {
  covered: { background: "rgba(52,211,153,0.15)", color: "#34d399", borderColor: "rgba(52,211,153,0.2)" },
  missing: { background: "rgba(244,113,113,0.15)", color: "#f87171", borderColor: "rgba(244,113,113,0.2)" },
};
const STAT_LABEL = { fontSize: "10.5px", textTransform: "uppercase", letterSpacing: ".05em", marginTop: "5px" };
const STAT_VALUE = { fontSize: "18px", fontWeight: "700", lineHeight: "1" };

function CaseCard({ c, mode, run, newly, lost }) {
  const sha = run.head_sha ? run.head_sha.slice(0, 7) : "";
  return (
    <div style={{ border: "1px solid #1E2A40", background: "#0D1728", borderRadius: "10px", padding: "12px 14px", marginBottom: "8px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "12px", marginBottom: "6px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
          {mode === "covered" && newly.has(c.id) ? (
            <span style={{ color: "#34d399", fontWeight: "bold", fontSize: "14px", marginRight: "2px" }} title="Newly covered in this run">
              ↑
            </span>
          ) : mode === "missing" && lost.has(c.id) ? (
            <span style={{ color: "#f87171", fontWeight: "bold", fontSize: "14px", marginRight: "2px" }} title="No longer covered in this run">
              ↓
            </span>
          ) : null}
          {c.display_id ? (
            <code style={{ fontFamily: "monospace", fontSize: "10px", background: "rgba(255,255,255,0.06)", padding: "2px 6px", borderRadius: "4px", color: "#94a3b8" }}>
              {c.display_id}
            </code>
          ) : null}
        </div>
        <PriorityBadge priority={c.priority} />
      </div>
      <div style={{ fontSize: "13.5px", fontWeight: "500", color: "#e2e8f0", lineHeight: "1.4", marginBottom: "8px" }}>{c.title}</div>
      {c.partial ? (
        <div style={{ fontSize: "11.5px", color: "var(--amber)", marginBottom: "8px" }}>
          ⚠ Partial match, not confirmed{c.rationale ? ` — ${c.rationale}` : ""}
        </div>
      ) : null}
      <StepsTable steps={c.steps} />
      <div style={{ display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap" }}>
        {sha ? (
          run.commit_url ? (
            <a
              href={run.commit_url}
              target="_blank"
              rel="noopener noreferrer"
              style={{ display: "inline-flex", alignItems: "center", gap: "3px", fontFamily: "monospace", fontSize: "10px", background: "rgba(59,130,246,0.1)", color: "#60a5fa", border: "1px solid rgba(59,130,246,0.2)", padding: "2px 6px", borderRadius: "4px", textDecoration: "none" }}
            >
              {sha} ↗
            </a>
          ) : (
            <span style={{ fontFamily: "monospace", fontSize: "10px", background: "rgba(255,255,255,0.06)", color: "#94a3b8", padding: "2px 6px", borderRadius: "4px" }}>{sha}</span>
          )
        ) : null}
        {run.feature_name ? (
          <span style={{ fontSize: "10.5px", background: "rgba(51, 65, 85, 0.4)", color: "#94a3b8", padding: "2px 8px", borderRadius: "4px" }}>{run.feature_name}</span>
        ) : null}
      </div>
    </div>
  );
}

/** One type group: Covered / Missing toggle (covered first when there is any). */
function Section({ sec, run, newly, lost }) {
  const [mode, setMode] = useState(sec.covered.length ? "covered" : "missing");
  const partial = sec.missing.filter((c) => c.partial).length;
  const cov = mode === "covered";
  const list = (which, items, empty) => (
    <div className={`cov-list-${which}-${sec.type}`} data-count={items.length} style={{ display: mode === which ? "block" : "none" }}>
      {items.length ? (
        items.map((c) => <CaseCard key={c.id} c={c} mode={which} run={run} newly={newly} lost={lost} />)
      ) : (
        <div className="muted" style={{ padding: "8px 4px" }}>
          {empty}
        </div>
      )}
    </div>
  );
  const toggle = (which, label) => (
    <button
      type="button"
      className="cov-toggle-btn"
      onClick={() => setMode(which)}
      style={{ ...(mode === which ? ACTIVE : IDLE), border: "none", borderRadius: "999px", padding: "5px 12px", fontSize: "11px", fontWeight: "600", cursor: "pointer", transition: "all 0.15s" }}
    >
      {label}
    </button>
  );
  return (
    <details className="case-group gap-section" open={sec.covered.length > 0}>
      <summary style={{ color: "var(--text)", fontSize: "13px", textTransform: "none", letterSpacing: "normal", fontWeight: "600" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          <span>{typeTitle(sec.type)}</span>
          <span className="badge" style={{ borderRadius: "999px", background: "rgba(255,255,255,.05)", border: "1px solid var(--line)", color: "var(--muted)", padding: "2px 7px", fontSize: "10px" }}>
            {sec.covered.length} covered · {sec.missing.length} missing{partial ? ` (${partial} partial)` : ""}
          </span>
        </div>
      </summary>
      <div className="case-group-body" style={{ padding: "10px 14px 14px" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "12px", marginBottom: "12px" }}>
          <div className="inline-flex" style={{ display: "inline-flex", background: "#0d1728", border: "1px solid #28405f", borderRadius: "999px", padding: "2px" }}>
            {toggle("covered", "Covered")}
            {toggle("missing", "Missing")}
          </div>
          <span className="cov-status-badge" style={{ fontSize: "11px", fontWeight: "600", padding: "3px 10px", borderRadius: "999px", ...BADGE[mode], border: `1px solid ${BADGE[mode].borderColor}`, transition: "all 0.15s" }}>
            {cov ? `${sec.covered.length} covered` : `${sec.missing.length} missing`}
          </span>
        </div>
        {list("covered", sec.covered, "No covered test cases.")}
        {list("missing", sec.missing, "No missing test cases.")}
      </div>
    </details>
  );
}

function HeaderLinks({ run, onReassign }) {
  return (
    <div style={{ display: "flex", gap: "8px", flexWrap: "wrap", marginBottom: "12px", alignItems: "center" }}>
      {run.pr_url ? (
        <a className="run-link-btn run-link-primary" target="_blank" rel="noopener noreferrer" href={run.pr_url} title="Open pull request">
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <path d="M7 3v12"></path>
            <circle cx="7" cy="18" r="2"></circle>
            <circle cx="7" cy="5" r="2"></circle>
            <path d="M17 6h4v4"></path>
            <path d="m21 6-6 6"></path>
          </svg>
          <span>Open PR</span>
        </a>
      ) : null}
      {run.commit_url ? (
        <a className="run-link-btn run-link-secondary" target="_blank" rel="noopener noreferrer" href={run.commit_url} title="View commit">
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <circle cx="12" cy="12" r="3"></circle>
            <path d="M3 12h6"></path>
            <path d="M15 12h6"></path>
          </svg>
          <span>View commit</span>
          <svg className="run-link-external" viewBox="0 0 24 24" aria-hidden="true">
            <path d="M14 5h5v5"></path>
            <path d="M19 5l-8 8"></path>
            <path d="M18 13v5a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"></path>
          </svg>
        </a>
      ) : null}
      {run.head_sha ? (
        <span className="muted" style={{ fontSize: "11px" }}>
          SHA <code>{run.head_sha.slice(0, 7)}</code>
        </span>
      ) : null}
      {run.feature_name ? (
        <span className="muted" style={{ fontSize: "11px" }}>
          Feature: <b>{run.feature_name}</b>
        </span>
      ) : null}
      <button className="ghost" type="button" onClick={() => onReassign(run.id)}>
        Reassign feature…
      </button>
      {run.needs_rerun ? (
        <span className="badge nfr" style={{ color: "var(--amber)" }}>
          feature edited after run — rerun recommended
        </span>
      ) : null}
    </div>
  );
}

/** #gap-pr-detail-body: the selected run (body.kind: "loading" | "error" | "run"). */
export default function RunDetail({ body, onReassign }) {
  if (!body) return <div id="gap-pr-detail-body"></div>;
  if (body.kind === "loading")
    return <div key="skeleton" id="gap-pr-detail-body" dangerouslySetInnerHTML={{ __html: skeleton.block("Loading coverage run details") }} />;
  if (body.kind === "error")
    return (
      <div key="error" id="gap-pr-detail-body">
        <div className="err">{body.text}</div>
      </div>
    );
  const r = body.run;
  const d = runDetail(r);
  return (
    <div key={"run" + body.seq} id="gap-pr-detail-body">
      <div className="sub" style={{ margin: "8px 0" }}>
        {r.pr_title || ""} · branch <b>{r.pr_branch || ""}</b>
      </div>
      <HeaderLinks run={r} onReassign={onReassign} />
      <div style={{ display: "flex", gap: "0", padding: "14px 18px", background: "var(--panel2)", border: "1px solid var(--line)", borderRadius: "9px", marginBottom: "14px" }}>
        <div style={{ flex: "1", minWidth: "140px" }}>
          <div style={STAT_VALUE}>
            {d.cov} / {d.total}
          </div>
          <div className="muted" style={STAT_LABEL}>
            Tests covered
          </div>
          {d.partialCount ? (
            <div className="muted" style={{ fontSize: "11px", marginTop: "3px" }}>
              + {d.partialCount} partial, not counted
            </div>
          ) : null}
        </div>
        <div style={{ flex: "1", minWidth: "140px", borderLeft: "1px solid var(--line)", paddingLeft: "18px" }}>
          <div style={STAT_VALUE}>{d.newlyCount}</div>
          <div className="muted" style={STAT_LABEL}>
            New tests found
          </div>
        </div>
        <div style={{ flex: "1", minWidth: "140px", borderLeft: "1px solid var(--line)", paddingLeft: "18px" }}>
          <div style={STAT_VALUE}>{d.gaps}</div>
          <div className="muted" style={STAT_LABEL}>
            Gaps
          </div>
        </div>
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: "16px", border: "1px solid #0e1f35", background: "#07111f", borderRadius: "12px", padding: "12px 16px", marginBottom: "14px", fontSize: "12px", color: "#a0aec0" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
          <span style={{ color: "#34d399", fontWeight: "bold", fontSize: "14px" }}>↑</span>
          <span>
            <b>Upstream</b> means the testcase is newly covered in this run.
          </span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
          <span style={{ color: "#f87171", fontWeight: "bold", fontSize: "14px" }}>↓</span>
          <span>
            <b>Downstream</b> means the testcase was covered before and is now missing.
          </span>
        </div>
      </div>
      {d.sections.length ? (
        d.sections.map((sec) => <Section key={sec.type} sec={sec} run={r} newly={d.newly} lost={d.lost} />)
      ) : (
        <div className="muted">No test cases on this feature yet.</div>
      )}
    </div>
  );
}
