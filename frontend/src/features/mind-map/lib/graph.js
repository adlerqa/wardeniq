/**
 * Model and helpers for the implementation coverage graph (was the second
 * half of compat/runtime/controllers/09-mind-map-and-jobs.js).
 *
 * Structure: PROJECT → REPOSITORY → FEATURE → STATUS → test cases. Two
 * layouts, picked so the map never crowds: radial for small single-repo
 * projects, a tidy tree otherwise (every row comes from its leaf index, so
 * nothing overlaps at any size).
 */
import { escapeHtml as esc } from "../../../lib/html.js";
import { typeLabel } from "../../test-cases/lib/testCases.js";
import { statusRank } from "./mindmap.js";

export const MM_C = {
  covered: "#34d399",
  partial: "#fbbf24",
  uncovered: "#f87171",
  hub: "#60a5fa",
  repo: "#38bdf8",
  feat: "#a78bfa",
  file: "#7dd3fc",
};
export const MM_ST = ["covered", "partial", "uncovered"];
export const MM_RADIAL_MAX = 9; // beyond this, radial can't stay legible → tree
export const MM_LEAF_CAP = 48; // cases drawn per expanded feature before "+N more"
export const ZOOM_MIN = 0.5;
export const ZOOM_MAX = 2.2;

export const mmTrunc = (s, n) => {
  s = String(s || "");
  return s.length > n ? s.slice(0, n - 1) + "…" : s;
};
export const mmPct = (a, b) => (b ? Math.round((a / b) * 100) : 0);
export const mmPolar = (cx, cy, r, d) => [cx + r * Math.cos((d * Math.PI) / 180), cy + r * Math.sin((d * Math.PI) / 180)];

/** Zoom factor after one zoom step (clamped). */
export const zoomStep = (k, d) => Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, k * d));

/*
 * Tooltips. The data-tip attribute holds a small HTML string whose values are
 * escaped; it is shown through mmSafeTipNodes, which only keeps a few
 * formatting tags (never innerHTML).
 */
export const mmTip = (h) => String(h);
const MM_TIP_TAGS = new Set(["B", "I", "BR", "CODE", "SPAN"]);
export function mmSafeTipNodes(html, doc = document, Parser = DOMParser) {
  const parsed = new Parser().parseFromString(String(html || ""), "text/html");
  const out = doc.createDocumentFragment();
  const copy = (src, dst) => {
    for (const n of Array.from(src.childNodes)) {
      if (n.nodeType === 3) dst.appendChild(doc.createTextNode(n.nodeValue));
      else if (n.nodeType === 1) {
        if (MM_TIP_TAGS.has(n.tagName)) {
          const el = doc.createElement(n.tagName.toLowerCase());
          const cls = n.getAttribute("class");
          if (n.tagName === "SPAN" && cls && /^[\w -]+$/.test(cls)) el.className = cls;
          copy(n, el);
          dst.appendChild(el);
        } else copy(n, dst); // drop the element, keep its text
      }
    }
  };
  copy(parsed.body, out);
  return out;
}

export const featTip = (f) =>
  mmTip(
    `<b>${esc(f.label)}</b> · v${f.version}<br>${mmPct(f.counts.covered || 0, f.total || 1)}% implemented · ${
      f.total || f.case_count
    } cases` +
      (f.repos.length ? `<br>${esc(f.repos.join(", "))}` : "") +
      `<br><i>click to expand</i>`,
  );
export const caseTip = (c) =>
  mmTip(
    `<b>${esc(mmTrunc(c.title, 80))}</b><br><span class="mm-t-${esc(c.status)}">${esc(c.status)}</span> · ${esc(
      typeLabel(c.type || ""),
    )}` +
      (c.rationale ? `<br>${esc(mmTrunc(c.rationale, 170))}` : "") +
      ((c.files || []).length
        ? `<br>evidence: ${c.files
            .slice(0, 2)
            .map((x) => `<code>${esc(mmTrunc(x, 32))}</code>`)
            .join(" ")}`
        : "<br><i>no implementing file found</i>"),
  );
export const bucketTip = (v, k, label, n) =>
  mmTip(`<b>${v} ${k}</b> case${v === 1 ? "" : "s"}<br>in ${esc(mmTrunc(label, n))}<br><i>click to open</i>`);
export const hubTip = (m) =>
  mmTip(
    `<b>${m.feats.length} features · ${m.grand} judged cases</b><br>${m.totals.covered} covered · ${m.totals.partial} partial · ${m.totals.uncovered} uncovered`,
  );
export const notAnalyzedTip = (f) => mmTip(`${esc(f.label)}<br>${f.case_count} cases · not analyzed`);
export const repoTip = (repo, fc) =>
  mmTip(`<b>${esc(repo)}</b><br>${fc} feature${fc === 1 ? "" : "s"} reviewed against this repository`);
export const hotTip = (e) =>
  mmTip(
    `<b>${esc(e.file)}</b><br>${e.cases} case${e.cases === 1 ? "" : "s"} · ${e.feats} feature${e.feats === 1 ? "" : "s"}`,
  );

/** Wrap a label into at most `max` lines of about `per` characters. */
export function mmWrap(s, per, max) {
  const w = String(s || "").split(/\s+/),
    out = [];
  let cur = "";
  for (const x of w) {
    if (!cur) {
      cur = x;
      continue;
    }
    if ((cur + " " + x).length <= per) cur += " " + x;
    else {
      out.push(cur);
      cur = x;
      if (out.length === max) break;
    }
  }
  if (cur && out.length < max) out.push(cur);
  return out.length ? out.slice(0, max) : [""];
}

function mmLabel(f, feats) {
  const d = feats.filter((x) => x.name === f.name);
  return d.length < 2 ? f.name : `${f.name} (${d.indexOf(f) + 1}/${d.length})`;
}

/** Graph model from the /mindmap response. */
export function mmModel(data) {
  const feats = ((data && data.features) || []).map((f, i) => {
    const c = f.counts || {},
      total = MM_ST.reduce((s, k) => s + (c[k] || 0), 0);
    const files = new Set();
    (f.cases || []).forEach((cs) => (cs.files || []).forEach((x) => files.add(x)));
    (f.reviewed_files || []).forEach((x) => files.add(x));
    return {
      i,
      id: f.feature_id,
      name: f.feature,
      version: f.version,
      counts: c,
      total,
      cases: (f.cases || []).slice().sort((a, b) => statusRank(a.status) - statusRank(b.status)),
      repos: f.repos || [],
      files: [...files],
      case_count: f.case_count || 0,
    };
  });
  feats.forEach((f) => (f.label = mmLabel(f, feats)));
  const totals = { covered: 0, partial: 0, uncovered: 0 };
  feats.forEach((f) => MM_ST.forEach((k) => (totals[k] += f.counts[k] || 0)));
  // a feature reviewed against several repos is listed under each
  const groups = new Map();
  feats.forEach((f) => {
    (f.repos.length ? f.repos : ["(no repository)"]).forEach((r) => {
      if (!groups.has(r)) groups.set(r, []);
      groups.get(r).push(f);
    });
  });
  const ev = new Map();
  feats.forEach((f) =>
    f.cases.forEach((c) =>
      (c.files || []).forEach((fp) => {
        if (!ev.has(fp)) ev.set(fp, { cases: 0, feats: new Set() });
        const e = ev.get(fp);
        e.cases++;
        e.feats.add(f.i);
      }),
    ),
  );
  return {
    feats,
    totals,
    grand: MM_ST.reduce((s, k) => s + totals[k], 0),
    repos: [...groups.keys()],
    groups,
    evidence: [...ev.entries()]
      .map(([file, e]) => ({ file, cases: e.cases, feats: e.feats.size }))
      .sort((a, b) => b.cases - a.cases),
  };
}

/** "radial" or "tree" for the chosen mode ("auto" picks the clearer one). */
export function mmLayout(m, mode) {
  return mode !== "auto" ? mode : m.feats.length <= MM_RADIAL_MAX && m.repos.length <= 1 ? "radial" : "tree";
}

/** Cases of a feature under the active status filter. */
export const filteredCases = (f, filter) => (filter ? f.cases.filter((c) => c.status === filter) : f.cases);

/** Cubic edge between two points, bending at the midpoint column (tree layout). */
export const treeEdgePath = (x0, y0, x1, y1) => {
  const mx = (x0 + x1) / 2;
  return `M${x0},${y0} C${mx},${y0} ${mx},${y1} ${x1},${y1}`;
};
/** Edge from (x0,y0) toward (x1,y1) with control points at fractions a and b. */
export const radialEdgePath = (x0, y0, x1, y1, a, b) =>
  `M${x0},${y0} C${x0 + (x1 - x0) * a},${y0 + (y1 - y0) * a} ${x0 + (x1 - x0) * b},${y0 + (y1 - y0) * b} ${x1},${y1}`;

/**
 * Rows of the tree layout: groups (repos) → features → leaves, with a y for
 * every node. A leaf's y is a pure function of its index, so nothing overlaps.
 */
export function treeRows(m, sel, filter) {
  const multi = m.repos.length > 1,
    ROW = 30,
    PAD = 64;
  const leaves = [];
  const groups = [];
  (multi ? m.repos : [null]).forEach((rp) => {
    const fs = multi ? m.groups.get(rp) : m.feats;
    const g = { repo: rp, feats: [] };
    fs.forEach((f) => {
      const item = { f, kids: [] };
      if (sel === f.i) {
        const cs = filteredCases(f, filter);
        cs.slice(0, MM_LEAF_CAP).forEach((c) => item.kids.push({ kind: "case", c }));
        if (cs.length > MM_LEAF_CAP) item.kids.push({ kind: "more", n: cs.length - MM_LEAF_CAP });
        if (!cs.length) item.kids.push({ kind: "none" });
      } else {
        const act = MM_ST.filter((k) => (f.counts[k] || 0) > 0);
        (act.length ? act : ["na"]).forEach((k) => item.kids.push({ kind: "bucket", k, v: f.counts[k] || 0 }));
      }
      item.kids.forEach((k) => {
        k.y = PAD + leaves.length * ROW;
        leaves.push(k);
      });
      item.y = (item.kids[0].y + item.kids[item.kids.length - 1].y) / 2;
      g.feats.push(item);
    });
    g.y = g.feats.length ? (g.feats[0].y + g.feats[g.feats.length - 1].y) / 2 : PAD;
    groups.push(g);
  });
  const H = Math.max(300, PAD + leaves.length * ROW + 34);
  const rootY = groups.length ? (groups[0].y + groups[groups.length - 1].y) / 2 : H / 2;
  return { multi, groups, H, rootY };
}
