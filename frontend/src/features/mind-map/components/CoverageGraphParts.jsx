import { typeLabel } from "../../test-cases/lib/testCases.js";
import { MM_C, MM_ST, filteredCases, hotTip, mmLayout, mmPct, mmTrunc } from "../lib/graph.js";

/** Headline numbers above the graph (#mm-summary). */
export function GraphSummary({ m }) {
  if (!m.grand)
    return (
      <span className="mm-sum-x">
        Not analyzed yet — run <b>Analyze codebase</b> to build the map.
      </span>
    );
  return (
    <>
      <span className="mm-sum-hero">{`${mmPct(m.totals.covered, m.grand)}%`}</span>
      <span className="mm-sum-l">implemented</span>
      <span className="mm-sum-sep"></span>{" "}
      <span className="mm-sum-i">
        <b>{m.grand}</b> cases judged
      </span>{" "}
      <span className="mm-sum-i cov">
        <b>{m.totals.covered}</b> covered
      </span>{" "}
      <span className="mm-sum-i par">
        <b>{m.totals.partial}</b> partial
      </span>{" "}
      <span className="mm-sum-i unc">
        <b>{m.totals.uncovered}</b> uncovered
      </span>{" "}
      <span className="mm-sum-i">
        <b>{m.feats.length}</b> features
      </span>{" "}
      <span className="mm-sum-i">
        <b>{m.repos.length}</b>
        {` repo${m.repos.length === 1 ? "" : "s"}`}
      </span>
    </>
  );
}

/** Status colours + how to read the layout (#mm-legend). */
export function GraphLegend({ m, mode }) {
  return (
    <>
      {MM_ST.map((k) => (
        <span key={k} className="mm-lg">
          <i style={{ background: MM_C[k] }}></i>
          {k}
        </span>
      ))}
      <span className="mm-lg-hint">
        {mmLayout(m, mode) === "tree"
          ? "grouped by repository · click a feature to expand its cases"
          : "node size = cases · click a branch to expand"}
      </span>
    </>
  );
}

const MODE_TITLES = {
  auto: "pick the clearest layout automatically",
  radial: "radial map (best for small projects)",
  tree: "tree (best for many repos/features)",
};

/** Breadcrumb of the open feature / filter, and the layout switch (#mm-crumb). */
export function GraphCrumb({ m, mode, sel, filter }) {
  const f = sel != null ? m.feats.find((x) => x.i === sel) : null;
  return (
    <>
      {f ? (
        <>
          <button type="button" className="mm-crumb-btn" id="mm-crumb-root">
            All features
          </button>
          {" ▸ "}
          <b>{mmTrunc(f.label, 26)}</b>
          {filter ? (
            <>
              {" ▸ "}
              <b>{filter}</b>
            </>
          ) : null}
          {"　"}
        </>
      ) : null}
      <span className="mm-mode">
        {["auto", "radial", "tree"].map((x) => (
          <button
            key={x}
            type="button"
            className={mode === x ? "mm-mode-b on" : "mm-mode-b"}
            data-mmmode={x}
            title={MODE_TITLES[x]}
          >
            {x}
          </button>
        ))}
      </span>
    </>
  );
}

/** Evidence hotspots, or the open feature's cases (#mm-detail). */
export function GraphDetail({ m, sel, filter }) {
  if (sel == null) {
    if (!m.evidence.length) return null;
    const top = m.evidence.slice(0, 6),
      max = top[0].cases || 1;
    return (
      <div className="mm-hot">
        <div className="mm-hot-head">
          Evidence hotspots{" "}
          <span className="muted">— files cited most often as implementing a case; the riskiest places to change</span>
        </div>
        {top.map((e, i) => (
          <div key={i} className="mm-hot-row" data-tip={hotTip(e)}>
            <span className="mm-hot-file">
              <code>{mmTrunc(e.file, 50)}</code>
            </span>
            <span className="mm-hot-bar">
              <i style={{ width: `${Math.max(4, (e.cases / max) * 100)}%` }}></i>
            </span>
            <span className="mm-hot-n">{`${e.cases} case${e.cases === 1 ? "" : "s"}`}</span>
          </div>
        ))}
      </div>
    );
  }
  const f = m.feats.find((x) => x.i === sel);
  if (!f) return null;
  const shown = filteredCases(f, filter);
  return (
    <>
      <div className="mm-detail-head">
        <div>
          <div className="mm-detail-title">
            {f.label} <span className="pill">{`v${f.version}`}</span>
          </div>
          <div className="mm-detail-sub">
            {`${f.files.length} file${f.files.length === 1 ? "" : "s"} reviewed${f.repos.length ? " · " + f.repos.join(", ") : ""}`}
          </div>
        </div>
        <div className="mm-chip-row">
          {MM_ST.map((k) => (
            <button key={k} type="button" className={`mm-chip ${k} ${filter === k ? "on" : ""}`} data-mmfilter={k}>
              {`${f.counts[k] || 0} ${k}`}
            </button>
          ))}
          <button type="button" className={`mm-chip ${filter ? "" : "on"}`} data-mmfilter="">
            all
          </button>
        </div>
      </div>
      <div className="mm-case-list">
        {shown.length ? (
          shown.slice(0, 60).map((c, i) => (
            <div key={i} className="mm-case">
              <div className="mm-case-h">
                <span className={`mm-sdot ${c.status}`}></span>
                <b>{c.title}</b>{" "}
                <span className="mm-case-tags">
                  {c.display_id ? <code>{c.display_id}</code> : null}
                  <span className={`badge ${c.type}`}>{typeLabel(c.type || "")}</span>
                  <span className={`badge mm-${c.status}`}>{c.status}</span>
                </span>
              </div>
              {c.rationale ? <div className="mm-case-why">{c.rationale}</div> : null}
              {(c.files || []).length ? (
                <div className="mm-case-ev">
                  <span>evidence</span>
                  {c.files.map((x, j) => (
                    <code key={j}>{x}</code>
                  ))}
                </div>
              ) : (
                <div className="mm-case-ev none">
                  <span>no implementing file was found in the indexed source</span>
                </div>
              )}
            </div>
          ))
        ) : (
          <div className="mm-detail-empty">{`No ${filter || ""} cases here.`}</div>
        )}
      </div>
    </>
  );
}
