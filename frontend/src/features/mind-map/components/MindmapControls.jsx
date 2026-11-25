import { Fragment } from "react";

import { completeText, formatMindmapStage, progressBits, repoKindClass, repoKindLabel } from "../lib/mindmap.js";

/** Repo checkboxes with a branch picker each (#mm-repos rows). */
export function RepoRows({ repos, onChange }) {
  if (!repos.length) return <span className="muted">no repos yet — connect one under Projects &amp; Repos</span>;
  return repos.map((rp) => (
    <div key={rp.id} style={{ display: "flex", gap: "8px", alignItems: "center", fontSize: "12.5px" }}>
      <label style={{ display: "flex", gap: "6px", alignItems: "center", margin: "0", flex: "1" }}>
        <input
          type="checkbox"
          className="mm-repo-chk"
          value={rp.id}
          checked={rp.checked}
          onChange={(e) => onChange(rp.id, { checked: e.target.checked })}
          style={{ width: "auto" }}
        />{" "}
        {rp.full_name} <span className={`pill ${repoKindClass(rp.kind)}`}>{repoKindLabel(rp.kind)}</span>
      </label>
      <select
        className="mm-repo-branch"
        data-rid={rp.id}
        title="branch to analyze"
        value={rp.branch}
        onChange={(e) => onChange(rp.id, { branch: e.target.value })}
        style={{ flex: "0 0 220px", fontSize: "12px", padding: "5px 8px" }}
      >
        <option value="">{`${rp.defaultLabel} (default)`}</option>
        {rp.branchOptions.map((b) => (
          <option key={b} value={b}>
            {b}
          </option>
        ))}
      </select>
    </div>
  ));
}

/** Contents of #mm-status. */
export function AnalysisStatus({ status }) {
  if (!status) return null;
  if (status.kind === "text") return status.text;
  if (status.kind === "error") return <span className="err">{status.text}</span>;
  if (status.kind === "failed") return <span className="err">Analysis failed: {status.text}</span>;
  if (status.kind === "running") {
    const bits = progressBits(status.result);
    return (
      <>
        {`⏳ ${formatMindmapStage(status.stage)}`}
        {bits ? (
          <>
            {" "}
            <span className="muted">· {bits}</span>
          </>
        ) : null}
      </>
    );
  }
  const a = status.result || {};
  return (
    <>
      {completeText(a)}
      {a.note ? (
        <>
          {" · "}
          <span className="warn">{a.note}</span>
        </>
      ) : null}
      {(a.errors || []).length ? (
        <>
          {" · "}
          <span className="err">{a.errors.length} repo issue(s)</span>
        </>
      ) : null}
    </>
  );
}

/** "Indexed code by repository" diagnostics (#mm-diag). */
export function IndexedCodeDiag({ perRepo }) {
  if (!perRepo.length) return null;
  return (
    <div className="card mindmap-diagnostics">
      <details>
        <summary>Indexed code by repository</summary>
        <div className="sub" style={{ marginTop: "8px" }}>
          Production files indexed from each repo&apos;s selected branch (test/spec files excluded). If a file you
          expected is missing here, it&apos;s not on that branch — pick the right branch and re-run.
        </div>
        {perRepo.map((r, i) => (
          <DiagRepo key={i} r={r} />
        ))}
      </details>
    </div>
  );
}

/** `<code>a</code> <code>b</code>` — space-separated, no wrapper element. */
export function Codes({ items }) {
  return items.map((s, i) => (
    <Fragment key={i}>
      {i ? " " : null}
      <code>{s}</code>
    </Fragment>
  ));
}

function DiagRepo({ r }) {
  if (r.error)
    return (
      <div className="stepitem">
        <b>{r.repo}</b> <span className="badge mm-uncovered">fetch error</span>
        <div className="err">{r.error}</div>
      </div>
    );
  if (r.reused)
    return (
      <div className="stepitem">
        <b>{r.repo}</b> <span className="pill">{r.branch || "default"}</span>{" "}
        <span className="badge mm-covered">index reused (unchanged)</span>{" "}
        <span className="muted">{`${r.impl_files} impl files`}</span>
      </div>
    );
  const impl = r.impl_sample || [];
  const sample = r.sample || [];
  return (
    <div className="stepitem">
      <b>{r.repo}</b> <span className="pill">{r.branch || "default"}</span>{" "}
      <span className="muted">
        {`${r.files_in_repo} files in repo · `}
        <b style={{ color: "var(--text)" }}>{`${r.impl_files} impl indexed`}</b>
        {` · ${r.test_files} tests excluded`}
      </span>
      {(r.extensions || []).length ? (
        <div className="muted" style={{ marginTop: "3px" }}>
          extensions: <Codes items={r.extensions.map((e) => `${e[0]}×${e[1]}`)} />
        </div>
      ) : null}
      {impl.length ? (
        <div className="muted" style={{ marginTop: "3px" }}>
          indexed files: <Codes items={impl} />
        </div>
      ) : sample.length ? (
        <div className="muted" style={{ marginTop: "3px" }}>
          sample paths: <Codes items={sample.slice(0, 8)} />
        </div>
      ) : null}
    </div>
  );
}
