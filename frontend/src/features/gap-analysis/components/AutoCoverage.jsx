import { useState } from "react";
import { skeleton } from "../../../lib/skeleton.js";
import { autoPriority, autoSections, fmtTime, frameworkClass, shortPath, typeTitle } from "../lib/gap.js";

const SCAN_BADGE = {
  running: <span className="badge functional">scanning…</span>,
  done: <span className="badge api">scanned</span>,
  failed: (
    <span className="badge nfr" style={{ color: "var(--red)" }}>
      scan failed
    </span>
  ),
  never: <span className="badge">never scanned</span>,
};

/** #gap-auto-repos: the project's Test repos with Rescan (or Reset while scanning). */
export function AutoRepos({ repos, onRescan, onReset }) {
  if (repos.kind === "loading")
    return (
      <div
        key="skeleton"
        id="gap-auto-repos"
        style={{ display: "flex", flexDirection: "column", gap: "8px", marginBottom: "14px" }}
        dangerouslySetInnerHTML={{ __html: skeleton.rows(4, "Loading automation repositories") }}
      />
    );
  let body = null;
  if (repos.kind === "none")
    body = (
      <div className="muted">
        No <b>Test</b> repos connected on this project. Add one from the project detail page (type = Test).
      </div>
    );
  else if (repos.kind === "error") body = <div className="err">{repos.text}</div>;
  else if (repos.kind === "list")
    body = repos.list.map((rp) => {
      const status = rp.scan_status || "never";
      return (
        <div key={rp.id} className="repo-item-card">
          <div style={{ flex: "1" }}>
            <div>
              <b>{rp.full_name}</b> {SCAN_BADGE[status] || <span className="badge">{status}</span>}
            </div>
            <div className="muted" style={{ fontSize: "11px", marginTop: "3px" }}>
              files: {rp.scan_files_found || 0} · tests extracted: {rp.scan_cases_count || 0} · last scan: {rp.last_scan_at ? fmtTime(rp.last_scan_at) : "never"}
              {rp.scan_error ? (
                <>
                  {" · "}
                  <span className="err">{rp.scan_error}</span>
                </>
              ) : null}
            </div>
          </div>
          <div style={{ display: "flex", gap: "6px" }}>
            {status === "running" ? (
              <>
                <button className="ghost" type="button" disabled>
                  Scanning…
                </button>{" "}
                <button className="ghost" type="button" onClick={() => onReset(rp.id)} title="Force-clear a scan that's been stuck for too long" style={{ color: "var(--amber)" }}>
                  Reset
                </button>
              </>
            ) : (
              <button className="ghost" type="button" onClick={() => onRescan(rp.id)}>
                Rescan
              </button>
            )}
          </div>
        </div>
      );
    });
  return (
    <div key="list" id="gap-auto-repos" style={{ display: "flex", flexDirection: "column", gap: "8px", marginBottom: "14px" }}>
      {body}
    </div>
  );
}

/** One generated case: covered ones open to show the matched automated test. */
function AutoItem({ it }) {
  const [open, setOpen] = useState(false);
  const m = it.match;
  const isCov = it.status === "covered" && m;
  const prio = autoPriority(it.priority);
  const state = isCov ? "covered" : "missing";
  return (
    <div className={`auto-cov-card ${state}${open ? " open" : ""}`}>
      <button type="button" className="auto-cov-row" onClick={isCov ? () => setOpen((o) => !o) : undefined}>
        <span className={`auto-cov-check ${state}`}>{isCov ? "✓" : "○"}</span>
        <span className={`auto-cov-priority ${prio}`} title={`Priority: ${prio}`}></span>
        {it.display_id ? <code className="auto-cov-code">{it.display_id}</code> : null}
        <span className="auto-cov-title">{it.generated_title || ""}</span>
        {it.generated_type ? (
          <span className="badge" style={{ border: "none", background: "transparent", padding: "0", color: "var(--muted)", fontSize: "11px", marginLeft: "auto" }}>
            {it.generated_type.replace(/_/g, " ")} tests
          </span>
        ) : null}
        <span className={`auto-cov-badge-status ${state}`}>{isCov ? "✓ Test Exists" : "○ Test Missing"}</span>
        {isCov ? <span className="auto-cov-chevron">▼</span> : null}
      </button>
      {isCov ? (
        <div className="auto-cov-detail">
          <p className="auto-cov-detail-label">Matched Automation Test</p>
          <p className="auto-cov-detail-title">{m.title || "Untitled test"}</p>
          <div className="auto-cov-detail-meta">
            <span className={`auto-cov-fw-badge ${frameworkClass(m.framework || "unknown")}`}>{m.framework || "unknown"}</span>
            <span className="auto-cov-repo-badge" title={m.repo_full_name ?? ""}>
              {(m.repo_full_name || "").split("/").pop() || m.repo_full_name || ""}
            </span>
            {m.file_url ? (
              <a href={m.file_url} target="_blank" rel="noopener noreferrer" className="auto-cov-detail-link" title="Open file">
                {shortPath(m.file_path)}
              </a>
            ) : m.file_path ? (
              <span className="auto-cov-detail-link" title={m.file_path}>
                {shortPath(m.file_path)}
              </span>
            ) : null}
            <span className="auto-cov-detail-confidence">{Math.round((m.score || 0) * 100)}% match confidence</span>
          </div>
        </div>
      ) : null}
    </div>
  );
}

/** #gap-auto-items: generated cases by type, DONE then MISSING. */
export function AutoItems({ scan, seq }) {
  const sections = scan ? autoSections(scan.items) : [];
  return (
    <div id="gap-auto-items">
      {sections.map((sec) => (
        <details key={`${seq}-${sec.type}`} className="case-group gap-section" open={sec.covered.length > 0}>
          <summary style={{ color: "var(--text)", fontSize: "13px", textTransform: "none", letterSpacing: "normal", fontWeight: "600" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
              <span>{typeTitle(sec.type)}</span>
              <span className="badge" style={{ borderRadius: "999px", background: "rgba(255,255,255,.05)", border: "1px solid var(--line)", color: "var(--muted)", padding: "2px 7px", fontSize: "10px" }}>
                {sec.covered.length + sec.missing.length}
              </span>
            </div>
          </summary>
          <div className="case-group-body" style={{ padding: "10px 14px 14px" }}>
            {sec.covered.length ? (
              <>
                <div className="typehdr" style={{ margin: "0 0 8px", fontSize: "10.5px", color: "var(--green)" }}>
                  DONE ({sec.covered.length})
                </div>
                {sec.covered.map((it, i) => (
                  <AutoItem key={i} it={it} />
                ))}
              </>
            ) : null}
            {sec.missing.length ? (
              <>
                <div className="typehdr" style={{ margin: "12px 0 8px", fontSize: "10.5px", color: "var(--red)" }}>
                  MISSING ({sec.missing.length})
                </div>
                {sec.missing.map((it, i) => (
                  <AutoItem key={i} it={it} />
                ))}
              </>
            ) : null}
          </div>
        </details>
      ))}
    </div>
  );
}
