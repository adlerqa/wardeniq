import { skeleton } from "../../../lib/skeleton.js";
import { runCard } from "../lib/gap.js";

const STATUS = {
  done: <span className="badge api">DONE</span>,
  running: <span className="badge functional">RUNNING</span>,
  pending: <span className="badge">PENDING</span>,
  failed: (
    <span className="badge nfr" style={{ color: "var(--red)" }}>
      FAILED
    </span>
  ),
};

function RunCard({ run, onOpen, onExclude }) {
  const c = runCard(run);
  return (
    <div className="repo-item-card" style={{ cursor: "pointer", ...(c.excluded ? { opacity: ".55" } : {}) }} onClick={() => onOpen(c.id)}>
      <div style={{ flex: "1" }}>
        <div>
          <b>#{c.number}</b> · {c.title} {STATUS[c.status] || <span className="badge">{c.status || ""}</span>}{" "}
          {c.needsRerun ? (
            <span className="badge nfr" style={{ color: "var(--amber)" }}>
              NEEDS RERUN
            </span>
          ) : null}{" "}
          {c.excluded ? (
            <span className="badge" style={{ background: "#3a2a20", color: "var(--amber)" }}>
              EXCLUDED
            </span>
          ) : null}
        </div>
        <div className="muted" style={{ fontSize: "11px", marginTop: "3px" }}>
          {c.repo} · branch <b>{c.branch}</b> · {c.when}
        </div>
      </div>
      <div style={{ textAlign: "right" }}>
        <div>
          <b>
            {c.covered}/{c.total}
          </b>{" "}
          covered
        </div>
        <div className="muted" style={{ fontSize: "11px" }}>
          {c.pct}%{c.partial ? ` · ${c.partial} partial, not counted` : ""} · {c.source}
        </div>
        {c.prId ? (
          <button
            className="ghost needs-editor"
            type="button"
            title={c.excluded ? "Count this PR in coverage again" : "Ignore this PR in coverage"}
            style={{ fontSize: "11px", padding: "3px 9px", marginTop: "5px" }}
            onClick={(e) => {
              e.stopPropagation();
              onExclude(c.prId, !c.excluded);
            }}
          >
            {c.excluded ? "Include" : "Exclude"}
          </button>
        ) : null}
      </div>
    </div>
  );
}

/**
 * #gap-pr-list content. list.kind: "initial" | "loading" | "empty" | "error" |
 * "muted" (manual run progress) | "runs".
 */
export default function PrRuns({ list, onOpen, onExclude }) {
  if (list.kind === "loading")
    return <div key="skeleton" id="gap-pr-list" className="muted" dangerouslySetInnerHTML={{ __html: skeleton.rows(4, "Loading pull request coverage runs") }} />;
  let body;
  if (list.kind === "initial")
    body = (
      <>
        No runs yet — connect a repo on this project and open a PR (or click <b>+ Run on a PR</b>).
      </>
    );
  else if (list.kind === "empty") body = <div className="muted">No PR coverage runs yet. Waiting for a PR… (updates automatically)</div>;
  else if (list.kind === "error") body = <div className="err">{list.text}</div>;
  else if (list.kind === "muted") body = <div className="muted">{list.text}</div>;
  else body = list.runs.map((run) => <RunCard key={run.id} run={run} onOpen={onOpen} onExclude={onExclude} />);
  return (
    <div key="list" id="gap-pr-list" className="muted">
      {body}
    </div>
  );
}
