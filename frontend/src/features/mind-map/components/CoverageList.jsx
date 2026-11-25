import { Fragment } from "react";

import { SkeletonRows } from "../../../components/feedback/Skeleton.jsx";
import { typeLabel } from "../../test-cases/lib/testCases.js";
import { STATUSES, barPercents, coverageTotals, emptyReasonLine, hasEmptyReason, statusRank } from "../lib/mindmap.js";
import { Codes } from "./MindmapControls.jsx";

/*
 * The per-feature coverage list under the graph (#mm-map). Same markup and
 * classes as the old HTML.
 */

function Chips({ counts }) {
  return STATUSES.map((k, i) => (
    <Fragment key={k}>
      {i ? " " : null}
      <span className={`badge mm-${k}`}>{`${counts[k]} ${k}`}</span>
    </Fragment>
  ));
}

function Bar({ counts, total }) {
  const p = barPercents(counts, total);
  return (
    <div className="mm-bar" title={`${counts.covered} covered · ${counts.partial} partial · ${counts.uncovered} uncovered`}>
      {STATUSES.map((k) => (
        <span key={k} className={`mm-seg ${k}`} style={{ width: `${p[k]}%` }}></span>
      ))}
    </div>
  );
}

function EmptyReason({ last }) {
  if (!hasEmptyReason(last)) return null;
  const when = last.at ? new Date(last.at * 1000).toLocaleString() : "";
  const mapped = last.features_mapped || 0;
  const lines = (last.per_repo || []).map(emptyReasonLine);
  return (
    <div className="card mindmap-empty-reason" style={{ marginTop: "8px" }}>
      <div className="sub">
        {`Last analysis${when ? ` (${when})` : ""} mapped ${mapped} feature${mapped === 1 ? "" : "s"}.`}
      </div>
      {last.note ? (
        <div className="warn" style={{ marginTop: "4px" }}>
          {last.note}
        </div>
      ) : null}
      {lines.length ? (
        <div className="muted" style={{ marginTop: "6px", fontSize: "11.5px" }}>
          {lines.map((l, i) => (
            <Fragment key={i}>
              {i ? <br /> : null}
              <code>{l.repo}</code>
              {l.text}
            </Fragment>
          ))}
        </div>
      ) : null}
      {(last.errors || []).length ? (
        <div className="err" style={{ marginTop: "4px" }}>
          {last.errors.map((e, i) => (
            <Fragment key={i}>
              {i ? <br /> : null}
              {e}
            </Fragment>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function CaseItem({ c }) {
  return (
    <div className="mindmap-case-item">
      <div className="mindmap-case-title">
        <span className="mm-case-left">
          <span className={`mm-dot ${c.status}`}></span>
          {c.display_id ? (
            <code
              style={{
                fontSize: "10px",
                background: "rgba(255,255,255,.06)",
                padding: "1px 6px",
                borderRadius: "4px",
                color: "#94a3b8",
              }}
            >
              {c.display_id}
            </code>
          ) : null}
          <b>{c.title}</b>
        </span>
        <span className="mm-case-right">
          <span className={`badge ${c.type}`}>{typeLabel(c.type)}</span>
          <span className={`badge mm-${c.status}`}>{c.status}</span>
        </span>
      </div>
      <div className="mindmap-case-body">
        {c.rationale || ""}
        {(c.files || []).length ? (
          <>
            <br />
            <span style={{ color: "var(--accent2)" }}>Files reviewed:</span> <Codes items={c.files} />
          </>
        ) : null}
      </div>
    </div>
  );
}

function FeatureCard({ f }) {
  const c = f.counts;
  const t = c.covered + c.partial + c.uncovered;
  const cases = (f.cases || []).slice().sort((x, y) => statusRank(x.status) - statusRank(y.status));
  const reviewed = f.reviewed_files || [];
  return (
    <details className="mindmap-feature-card" open={c.uncovered > 0 || c.partial > 0}>
      <summary>
        <div className="mindmap-summary-main">
          <div className="mindmap-feature-title">
            <strong>{f.feature}</strong> <span className="pill">{`v${f.version}`}</span>{" "}
            {f.analyzed ? null : <span className="badge">not analyzed</span>}
          </div>
          {f.repos && f.repos.length ? (
            <div className="mindmap-feature-meta">
              Reviewed against{" "}
              {f.repos.map((rp, i) => (
                <Fragment key={i}>
                  {i ? " " : null}
                  <span className="pill">{rp}</span>
                </Fragment>
              ))}
            </div>
          ) : null}
        </div>
        <div className="mindmap-chip-row">
          <Chips counts={c} />
        </div>
      </summary>
      <div className="mindmap-feature-body">
        {t ? (
          <Bar counts={c} total={t} />
        ) : (
          <div className="muted" style={{ margin: "6px 0" }}>
            {`${f.case_count || 0} test cases — run analysis to map them to code.`}
          </div>
        )}
        {/* #21: "found code, judged uncovered" is different from "nothing found". */}
        {t && c.covered === 0 && c.partial === 0 && reviewed.length ? (
          <div className="warn" style={{ margin: "6px 0", fontSize: "12px" }}>
            {`All ${t} reviewed case${t === 1 ? "" : "s"} came back uncovered. ${reviewed.length} implementation file${
              reviewed.length === 1 ? " was" : "s were"
            } read for this feature — this may be an accurate gap, or the implementing code may live in a repo/branch that isn't connected here.`}
          </div>
        ) : null}
        {reviewed.length ? (
          <details style={{ margin: "6px 0 8px" }}>
            <summary className="muted" style={{ cursor: "pointer", fontSize: "11.5px" }}>
              {`Files reviewed for this feature (${reviewed.length})`}
            </summary>
            <div className="muted" style={{ marginTop: "4px" }}>
              <Codes items={reviewed} />
            </div>
          </details>
        ) : null}
        <div className="mindmap-case-list">
          {cases.map((cs, i) => (
            <CaseItem key={i} c={cs} />
          ))}
        </div>
      </div>
    </details>
  );
}

/** Contents of #mm-map. */
export function CoverageList({ map }) {
  if (map.status === "idle") return null;
  if (map.status === "loading") return <SkeletonRows count={5} label="Loading coverage map" />;
  if (map.status === "analyzing") return <SkeletonRows count={5} label="Analyzing code coverage" />;
  if (map.status === "noproject")
    return (
      <div className="card">
        <span className="muted">Pick a project to see its coverage map.</span>
      </div>
    );
  if (map.status === "error") return <div className="card err">{`Couldn't load the coverage map. ${map.error}`}</div>;
  const features = map.data.features || [];
  if (!features.length)
    return (
      <div className="card">
        <span className="muted">No features in this project yet.</span>
      </div>
    );
  const tot = coverageTotals(features);
  const grand = tot.covered + tot.partial + tot.uncovered;
  return (
    <>
      <div className="mindmap-summary-card">
        <div className="mindmap-summary-head">
          <h2>Project coverage map</h2>
          <div className="mindmap-chip-row">
            <Chips counts={tot} />
          </div>
        </div>
        {grand ? (
          <Bar counts={tot} total={grand} />
        ) : (
          <div className="sub">
            Not analyzed yet — click <b>Analyze codebase</b> to read the code and map coverage.
          </div>
        )}
      </div>
      {grand ? null : <EmptyReason last={map.data.last_analysis} />}
      {features.map((f, i) => (
        <FeatureCard key={`${map.seq}:${i}`} f={f} />
      ))}
    </>
  );
}
