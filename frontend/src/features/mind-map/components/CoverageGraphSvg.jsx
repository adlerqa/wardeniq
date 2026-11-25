import {
  MM_C,
  MM_LEAF_CAP,
  MM_ST,
  bucketTip,
  caseTip,
  featTip,
  filteredCases,
  hubTip,
  mmLayout,
  mmPct,
  mmPolar,
  mmTrunc,
  mmWrap,
  notAnalyzedTip,
  radialEdgePath,
  repoTip,
  treeEdgePath,
  treeRows,
} from "../lib/graph.js";

/*
 * The coverage graph SVG (zero-dependency, works air-gapped). Same elements,
 * classes and attributes as the old string-built SVG. The extra
 * [data-mm-pan-layer] group is where MindMapPage's drag-to-pan writes its
 * translate (it used to insert that group itself on the first drag).
 */

function Defs() {
  return (
    <defs>
      <filter id="mmSh" x="-60%" y="-60%" width="220%" height="220%">
        <feDropShadow dx="0" dy="2" stdDeviation="3.5" floodColor="#000" floodOpacity=".5" />
      </filter>
      <linearGradient id="mmCard" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stopColor="#1a2333" />
        <stop offset="100%" stopColor="#141b28" />
      </linearGradient>
      <radialGradient id="mmHubG" cx="50%" cy="38%">
        <stop offset="0%" stopColor="#1e3a5f" />
        <stop offset="100%" stopColor="#101927" />
      </radialGradient>
    </defs>
  );
}

function Stage({ W, H, scroll, k, children }) {
  return (
    <svg
      className={scroll ? "mm-svg mm-svg-tall" : "mm-svg"}
      viewBox={`0 0 ${W} ${H}`}
      preserveAspectRatio="xMidYMin meet"
      style={scroll ? { height: `${H}px` } : undefined}
      role="img"
      aria-label="implementation coverage map"
    >
      <Defs />
      <g data-mm-pan-layer="true" data-mm-pan-x="0" data-mm-pan-y="0">
        <g id="mm-zoom" transform={`translate(${W / 2},${H / 2}) scale(${k}) translate(${-W / 2},${-H / 2})`}>
          {children}
        </g>
      </g>
    </svg>
  );
}

function StatBar({ x, y, w, f }) {
  const t = f.total || 1,
    s = (key) => Math.max(0, ((f.counts[key] || 0) / t) * w);
  return (
    <g transform={`translate(${x},${y})`}>
      <rect width={w} height="5" rx="2.5" fill="#0d1420" />
      <rect width={s("covered")} height="5" rx="2.5" fill={MM_C.covered} />
      <rect x={s("covered")} width={s("partial")} height="5" rx="2.5" fill={MM_C.partial} />
      <rect x={s("covered") + s("partial")} width={s("uncovered")} height="5" rx="2.5" fill={MM_C.uncovered} />
    </g>
  );
}

const Edge = ({ d, cls, sw, extra }) => (
  <path className={cls ? `mm-edge ${cls}` : "mm-edge"} style={{ strokeWidth: sw, ...extra }} d={d} />
);

function Hub({ m, cx, cy }) {
  const pct = mmPct(m.totals.covered, m.grand);
  return (
    <g className="mm-node" data-tip={hubTip(m)}>
      <circle cx={cx} cy={cy} r="76" fill="url(#mmHubG)" stroke={MM_C.hub} strokeWidth="2" filter="url(#mmSh)" />
      <text x={cx} y={cy - 8} className="mm-hub-n">{`${pct}%`}</text>
      <text x={cx} y={cy + 11} className="mm-hub-l">
        implemented
      </text>
      <text x={cx} y={cy + 30} className="mm-hub-s">{`${m.grand} cases · ${m.feats.length} features`}</text>
    </g>
  );
}

// ---- layout A: radial (small projects) ------------------------------------
function Radial({ m, k }) {
  const n = m.feats.length,
    BW = 180,
    sector = 360 / n;
  // ring radius that guarantees no overlap: circumference needed / 2π
  const R1 = Math.max(210, Math.ceil((n * (BW + 34)) / (2 * Math.PI)));
  const R2 = R1 + 165,
    W = Math.ceil((R2 + 150) * 2),
    H = W;
  const cx = W / 2,
    cy = H / 2;
  const links = [],
    nodes = [],
    clus = [];
  m.feats.forEach((f, idx) => {
    const ang = -90 + idx * sector,
      [fx, fy] = mmPolar(cx, cy, R1, ang);
    const lines = mmWrap(f.label, 21, 2),
      bh = 30 + lines.length * 14;
    links.push(
      <Edge
        key={`f${idx}`}
        sw={Math.max(1.8, Math.min(8, (f.total || 1) / 11))}
        d={radialEdgePath(cx, cy, fx, fy, 0.45, 0.7)}
      />,
    );
    const act = MM_ST.filter((key) => (f.counts[key] || 0) > 0);
    act.forEach((key, j) => {
      const span = Math.min(sector * 0.7, 34 * act.length),
        a = ang - span / 2 + (act.length <= 1 ? span / 2 : (span * j) / (act.length - 1));
      const [bx, by] = mmPolar(cx, cy, R2, a),
        v = f.counts[key] || 0,
        r = 15 + Math.min(15, Math.sqrt(v) * 3);
      links.push(
        <Edge
          key={`b${idx}${key}`}
          cls={key}
          sw={Math.max(1.6, Math.min(9, v / 5))}
          d={radialEdgePath(fx, fy, bx, by, 0.5, 0.7)}
        />,
      );
      clus.push(
        <g key={`c${idx}${key}`} className="mm-node mm-clu" data-mmbucket={`${f.i}:${key}`} data-tip={bucketTip(v, key, f.label, 38)}>
          <circle cx={bx} cy={by} r={r} fill={MM_C[key]} fillOpacity=".15" stroke={MM_C[key]} strokeWidth="1.6" />
          <text x={bx} y={by + 1} className="mm-clu-n" fill={MM_C[key]}>
            {v}
          </text>
          <text x={bx} y={by + r + 13} className="mm-clu-l">
            {key}
          </text>
        </g>,
      );
    });
    if (!act.length) {
      const [bx, by] = mmPolar(cx, cy, R2, ang);
      clus.push(
        <g key={`e${idx}`} className="mm-node" data-tip={notAnalyzedTip(f)}>
          <circle cx={bx} cy={by} r="18" className="mm-clu-empty" />
          <text x={bx} y={by + 3} className="mm-clu-l">
            n/a
          </text>
        </g>,
      );
    }
    nodes.push(
      <g key={`n${idx}`} className="mm-node mm-feat" data-mmfeat={f.i} data-tip={featTip(f)}>
        <rect x={fx - BW / 2} y={fy - bh / 2} width={BW} height={bh} rx="12" className="mm-card" filter="url(#mmSh)" />
        {lines.map((l, li) => (
          <text key={li} x={fx} y={fy - bh / 2 + 19 + li * 14} className="mm-card-t">
            {l}
          </text>
        ))}
        <StatBar x={fx - 66} y={fy + bh / 2 - 15} w={132} f={f} />
        <text x={fx} y={fy + bh / 2 - 2} className="mm-card-m">{`v${f.version} · ${f.total || f.case_count} cases · ${mmPct(
          f.counts.covered || 0,
          f.total || 1,
        )}%`}</text>
      </g>,
    );
  });
  return (
    <Stage W={W} H={H} k={k}>
      <circle cx={cx} cy={cy} r={R1} className="mm-ring" />
      <circle cx={cx} cy={cy} r={R2} className="mm-ring" />
      {links}
      <Hub m={m} cx={cx} cy={cy} />
      {nodes}
      {clus}
    </Stage>
  );
}

function RadialFocus({ m, sel, filter, k }) {
  const f = m.feats.find((x) => x.i === sel);
  const cs = filteredCases(f, filter);
  const shown = cs.slice(0, MM_LEAF_CAP),
    n = shown.length || 1;
  // ring capacity from arc length so labels never collide
  const per = Math.max(8, Math.min(20, Math.floor(n / Math.ceil(n / 20)) || n));
  const ringCount = Math.ceil(n / per),
    R0 = 210,
    RS = 118;
  const Rmax = R0 + (ringCount - 1) * RS,
    W = Math.ceil((Rmax + 300) * 2),
    H = W;
  const cx = W / 2,
    cy = H / 2;
  const links = [],
    dots = [],
    labels = [];
  shown.forEach((c, j) => {
    const ring = Math.floor(j / per),
      inRing = Math.min(per, n - ring * per);
    const a = -90 + (360 * (j % per)) / inRing + (ring % 2 ? 180 / inRing : 0);
    const R = R0 + ring * RS,
      [dx, dy] = mmPolar(cx, cy, R, a);
    links.push(<Edge key={j} cls={c.status} sw={2} extra={{ opacity: 0.45 }} d={radialEdgePath(cx, cy, dx, dy, 0.5, 0.72)} />);
    dots.push(
      <g key={j} className="mm-node" data-tip={caseTip(c)}>
        <circle cx={dx} cy={dy} r="9" fill={MM_C[c.status]} className="mm-leaf" />
      </g>,
    );
    const right = dx >= cx;
    labels.push(
      <text key={j} x={dx + (right ? 14 : -14)} y={dy + 4} className="mm-leaf-t" textAnchor={right ? "start" : "end"}>
        {mmTrunc(c.title, 30)}
      </text>,
    );
  });
  const ttl = mmWrap(f.label, 18, 2);
  return (
    <>
      <Stage W={W} H={H} k={k}>
        {links}
        <g className="mm-node mm-hub-back" data-tip="back to all features">
          <circle cx={cx} cy={cy} r="94" fill="url(#mmHubG)" stroke={MM_C.feat} strokeWidth="2" filter="url(#mmSh)" />
          {ttl.map((l, i) => (
            <text key={i} x={cx} y={cy - 34 + i * 15} className="mm-hub-l" style={{ fontSize: "12px", fill: "#e6edf6" }}>
              {l}
            </text>
          ))}
          <text x={cx} y={cy + 2} className="mm-hub-n" style={{ fontSize: "22px" }}>{`${mmPct(
            f.counts.covered || 0,
            f.total || 1,
          )}%`}</text>
          <text x={cx} y={cy + 20} className="mm-hub-s">{`${cs.length} ${filter || "cases"}`}</text>
          <StatBar x={cx - 75} y={cy + 30} w={150} f={f} />
          <text x={cx} y={cy + 58} className="mm-hub-s">
            ← back
          </text>
        </g>
        {dots}
        {labels}
      </Stage>
      {cs.length > MM_LEAF_CAP ? (
        <div className="mm-note">{`Showing ${MM_LEAF_CAP} of ${cs.length} cases — filter by status, or use the list below.`}</div>
      ) : null}
    </>
  );
}

// ---- layout B: tidy tree (scales to many repos / features / cases) -------
function Tree({ m, sel, filter, k }) {
  const { multi, groups, H, rootY } = treeRows(m, sel, filter);
  const COL = { root: 26, repo: 250, feat: multi ? 470 : 300, leaf: multi ? 760 : 600 };
  const W = 1210;
  const out = [];
  const edge = (key, x0, y0, x1, y1, cls, sw) => (
    <Edge key={key} cls={cls} sw={sw || 1.6} d={treeEdgePath(x0, y0, x1, y1)} />
  );
  out.push(
    <text key="h-root" x={COL.root} y="30" className="mm-col-h">
      PROJECT
    </text>,
  );
  if (multi)
    out.push(
      <text key="h-repo" x={COL.repo} y="30" className="mm-col-h">{`REPOSITORY (${m.repos.length})`}</text>,
    );
  out.push(
    <text key="h-feat" x={COL.feat} y="30" className="mm-col-h">{`FEATURE (${m.feats.length})`}</text>,
    <text key="h-leaf" x={COL.leaf} y="30" className="mm-col-h">
      {sel != null ? "TEST CASES" : "COVERAGE"}
    </text>,
  );
  const pct = mmPct(m.totals.covered, m.grand);
  out.push(
    <g key="root" className="mm-node" data-tip={hubTip(m)}>
      <rect x={COL.root} y={rootY - 31} width="186" height="62" rx="13" fill="url(#mmHubG)" stroke={MM_C.hub} strokeWidth="1.6" filter="url(#mmSh)" />
      <text x={COL.root + 16} y={rootY - 8} className="mm-tree-pct">{`${pct}%`}</text>
      <text x={COL.root + 70} y={rootY - 9} className="mm-hub-l" style={{ textAnchor: "start" }}>
        implemented
      </text>
      <text x={COL.root + 16} y={rootY + 11} className="mm-hub-s" style={{ textAnchor: "start" }}>{`${m.grand} cases · ${m.feats.length} features`}</text>
      <StatBar x={COL.root + 16} y={rootY + 18} w={154} f={{ total: m.grand, counts: m.totals }} />
    </g>,
  );
  groups.forEach((g, gi) => {
    const fx = COL.feat;
    if (multi) {
      out.push(edge(`ge${gi}`, COL.root + 186, rootY, COL.repo, g.y, "", 2.4));
      const fc = g.feats.length;
      out.push(
        <g key={`g${gi}`} className="mm-node" data-tip={repoTip(g.repo, fc)}>
          <rect x={COL.repo} y={g.y - 19} width="188" height="38" rx="10" className="mm-card mm-card-repo" filter="url(#mmSh)" />
          <circle cx={COL.repo + 15} cy={g.y} r="4" fill={MM_C.repo} />
          <text x={COL.repo + 27} y={g.y - 2} className="mm-card-t" style={{ textAnchor: "start" }}>
            {mmTrunc(g.repo.split("/").pop(), 22)}
          </text>
          <text x={COL.repo + 27} y={g.y + 11} className="mm-card-m" style={{ textAnchor: "start" }}>{`${fc} feature${
            fc === 1 ? "" : "s"
          }`}</text>
        </g>,
      );
    }
    g.feats.forEach((it, fi) => {
      const f = it.f,
        x0 = multi ? COL.repo + 188 : COL.root + 186,
        y0 = multi ? g.y : rootY;
      out.push(edge(`fe${gi}-${fi}`, x0, y0, fx, it.y, "", Math.max(1.6, Math.min(6, (f.total || 1) / 14))));
      const isSel = sel === f.i;
      out.push(
        <g key={`f${gi}-${fi}`} className={isSel ? "mm-node mm-feat sel" : "mm-node mm-feat"} data-mmfeat={f.i} data-tip={featTip(f)}>
          <rect x={fx} y={it.y - 21} width="252" height="42" rx="11" className="mm-card" filter="url(#mmSh)" />
          <text x={fx + 13} y={it.y - 5} className="mm-card-t" style={{ textAnchor: "start" }}>
            {mmTrunc(f.label, 30)}
          </text>
          <StatBar x={fx + 13} y={it.y + 2} w={140} f={f} />
          <text x={fx + 161} y={it.y + 8} className="mm-card-m" style={{ textAnchor: "start" }}>{`v${f.version} · ${
            f.total || f.case_count
          }c · ${mmPct(f.counts.covered || 0, f.total || 1)}%`}</text>
          <text x={fx + 239} y={it.y - 5} className="mm-chev">
            {isSel ? "▾" : "▸"}
          </text>
        </g>,
      );
      it.kids.forEach((kid, ki) => {
        const key = `${gi}-${fi}-${ki}`;
        out.push(
          edge(
            `ke${key}`,
            fx + 252,
            it.y,
            COL.leaf,
            kid.y,
            kid.kind === "bucket" ? kid.k : kid.kind === "case" ? kid.c.status : "",
            kid.kind === "bucket" ? Math.max(1.6, Math.min(8, kid.v / 5)) : 1.6,
          ),
        );
        if (kid.kind === "bucket") {
          // A feature with no judged cases gets an "na" bucket (count 0). It has
          // no colour, so fill / stroke read "undefined" (as before) and the
          // pill draws with the default fill at 14% opacity.
          out.push(
            <g key={`k${key}`} className="mm-node mm-clu" data-mmbucket={`${f.i}:${kid.k}`} data-tip={bucketTip(kid.v, kid.k, f.label, 34)}>
              <rect x={COL.leaf} y={kid.y - 11} width="150" height="22" rx="11" fill={`${MM_C[kid.k]}`} fillOpacity=".14" stroke={`${MM_C[kid.k]}`} strokeOpacity=".7" />
              <text x={COL.leaf + 13} y={kid.y + 4} className="mm-pill-n" fill={`${MM_C[kid.k]}`}>
                {kid.v}
              </text>
              <text x={COL.leaf + 40} y={kid.y + 4} className="mm-pill-l">
                {kid.k}
              </text>
            </g>,
          );
        } else if (kid.kind === "case") {
          const t = mmTrunc(kid.c.title, 46);
          out.push(
            <g key={`k${key}`} className="mm-node" data-tip={caseTip(kid.c)}>
              <circle cx={COL.leaf + 8} cy={kid.y} r="6" fill={MM_C[kid.c.status]} className="mm-leaf" />
              <text x={COL.leaf + 22} y={kid.y + 4} className="mm-leaf-t">
                {t}
              </text>
              {(kid.c.files || []).length ? (
                <text x={COL.leaf + 22} y={kid.y + 4} className="mm-leaf-ev" dx={Math.min(300, t.length * 6.1) + 12}>
                  {mmTrunc((kid.c.files[0] || "").split("/").pop(), 22)}
                </text>
              ) : null}
            </g>,
          );
        } else if (kid.kind === "more") {
          out.push(
            <text key={`k${key}`} x={COL.leaf + 22} y={kid.y + 4} className="mm-leaf-more">{`+${kid.n} more — filter by status or see the list below`}</text>,
          );
        } else if (kid.kind === "none") {
          out.push(
            <text key={`k${key}`} x={COL.leaf + 22} y={kid.y + 4} className="mm-leaf-more">{`no ${filter || ""} cases`}</text>,
          );
        }
      });
    });
  });
  return (
    <Stage W={W} H={H} scroll k={k}>
      {out}
    </Stage>
  );
}

/** Contents of #mm-graph. */
export function CoverageGraphSvg({ m, mode, sel, filter, k }) {
  if (!m.feats.length)
    return (
      <div className="mm-empty">
        No features in this project yet — add a feature, then run <b>Analyze codebase</b>.
      </div>
    );
  if (mmLayout(m, mode) === "tree") return <Tree m={m} sel={sel} filter={filter} k={k} />;
  if (sel != null && m.feats.some((x) => x.i === sel)) return <RadialFocus m={m} sel={sel} filter={filter} k={k} />;
  return <Radial m={m} k={k} />;
}
