// Legacy JavaScript — the original vanilla-JS UI. app/static/index.html has been
// removed, so this file (+ legacyShellHtml.js + styles/global.css) is now the
// CANONICAL source of the legacy UI and is hand-maintained.
//
// The original two <script> blocks, concatenated. LegacyApp.jsx imports this file
// with Vite's `?raw` suffix and injects it as a classic <script> element, so it
// runs in GLOBAL scope exactly like the old single-file page. Because of that,
// every top-level `function foo(){}` / `const foo = ...` is reachable from the
// inline on* handlers in the shell markup (e.g. onclick="navigateTo(...)") with
// no window.* shim required.

// Toasts, the confirm / prompt / HTML dialogs and the skeleton placeholders are
// React (components/overlays/modals, lib/skeleton.js, #257); they register
// toast, confirmModal, uiPrompt, uiModalHTML, skeleton, skIn and loadingRow on
// window.

// ============ BRANDED LOADERS (ported from the wardenIQ test-generator app) ============
// --- gear SVG generator (ported from AnalyzeLoader GearSVG) ---
function _gearSVG(size, teeth, fill, stroke) {
  const r = size / 2,
    inner = r * 0.58,
    toothH = r * 0.24,
    hole = r * 0.23,
    step = (Math.PI * 2) / teeth;
  let d = "";
  const pt = (a, rad) => [Math.cos(a) * rad, Math.sin(a) * rad];
  for (let i = 0; i < teeth; i++) {
    const a0 = step * i - step * 0.36,
      a1 = step * i - step * 0.14,
      a2 = step * i + step * 0.14,
      a3 = step * i + step * 0.36;
    const [x0, y0] = pt(a0, inner),
      [x1, y1] = pt(a1, r + toothH),
      [x2, y2] = pt(a2, r + toothH),
      [x3, y3] = pt(a3, inner);
    if (i === 0) d += `M ${x0.toFixed(2)},${y0.toFixed(2)} `;
    d += `L ${x1.toFixed(2)},${y1.toFixed(2)} L ${x2.toFixed(2)},${y2.toFixed(2)} L ${x3.toFixed(2)},${y3.toFixed(2)} `;
  }
  d += "Z";
  const vb = r + toothH + 2;
  return (
    `<svg width="${(vb * 2).toFixed(0)}" height="${(vb * 2).toFixed(0)}" viewBox="${-vb} ${-vb} ${vb * 2} ${vb * 2}" style="overflow:visible">` +
    `<path d="${d}" fill="${fill}" stroke="${stroke}" stroke-width="1.3"/>` +
    `<circle r="${hole.toFixed(2)}" fill="none" stroke="${stroke}" stroke-width="1.6"/>` +
    `<circle r="${(hole * 0.38).toFixed(2)}" fill="${stroke}" opacity="0.75"/></svg>`
  );
}
const ANALYZE_STEPS = [
  "Analyzing inputs",
  "AI processing",
  "Generating output",
];
const ANALYZE_MESSAGES = [
  "Checking readiness…",
  "Processing sources…",
  "Building AI context…",
  "Generating outputs…",
  "Finalizing workspace…",
];
const _analyzeCards = [
  {
    ico: "✓",
    color: "#a78bfa",
    border: "rgba(139,92,246,.55)",
    bg: "rgba(139,92,246,.18)",
    name: "requirements.txt",
    x: 8,
    y: 26,
  },
  {
    ico: "⚠",
    color: "#fb923c",
    border: "rgba(251,146,60,.5)",
    bg: "rgba(251,146,60,.15)",
    name: "bug_report.md",
    x: 0,
    y: 112,
  },
  {
    ico: "?",
    color: "#818cf8",
    border: "rgba(99,102,241,.5)",
    bg: "rgba(99,102,241,.18)",
    name: "ambiguous.spec",
    x: 18,
    y: 196,
  },
  {
    ico: "≡",
    color: "#38bdf8",
    border: "rgba(56,189,248,.5)",
    bg: "rgba(56,189,248,.15)",
    name: "api_docs.yaml",
    x: 300,
    y: 56,
  },
];

// Build a branded loader HTML string. variant: "analyze" | "quiz".
// opts: {compact, inline, messages, steps, questionLabel, optionLabel}
function brandLoader(variant, opts) {
  opts = opts || {};
  const sizeCls = opts.compact
    ? " compact"
    : opts.inline === false
      ? ""
      : " inline";
  if (variant === "quiz") {
    const steps = opts.steps || [
      "Analyzing inputs",
      "AI Processing",
      "Generating output",
    ];
    const q = opts.questionLabel || "Question 01",
      o = opts.optionLabel || "Option:";
    return `<div class="wql-root${sizeCls}" role="status" aria-label="Loading">
      <div class="wql-shell">
        <div class="wql-stepper" aria-hidden="true">
          <span class="wql-step wql-step-1"><span class="wql-step-dot"></span>${esc(steps[0])}</span>
          <span class="wql-step-line"></span>
          <span class="wql-step wql-step-2"><span class="wql-step-dot"></span>${esc(steps[1])}</span>
          <span class="wql-step-line"></span>
          <span class="wql-step wql-step-3"><span class="wql-step-dot"></span>${esc(steps[2])}</span>
        </div>
        <div class="wql-stack">
          <div class="wql-qcard"><div class="wql-qtitle">${esc(q)}</div>
            <div class="wql-qrow"><div class="wql-track"><div class="wql-line"></div></div><div class="wql-qmark">?</div></div></div>
          <div class="wql-ocard"><div class="wql-otitle">${esc(o)}</div>
            <div class="wql-olist" aria-hidden="true">
              <div class="wql-orow wql-row-1"><span class="wql-odot"></span><span class="wql-oline wql-l1"></span></div>
              <div class="wql-orow wql-row-2"><span class="wql-odot"></span><span class="wql-oline wql-l2"></span></div>
              <div class="wql-orow wql-row-3"><span class="wql-odot"></span><span class="wql-oline wql-l3"></span></div>
              <div class="wql-orow wql-row-4"><span class="wql-odot"></span><span class="wql-oline wql-l4"></span></div></div></div>
          <button class="wql-next" type="button" tabindex="-1">Next</button>
        </div>
      </div></div>`;
  }
  // analyze (gear machine)
  const steps = opts.steps || ANALYZE_STEPS;
  const msgs = opts.messages || ANALYZE_MESSAGES;
  const stepper = steps
    .map(
      (s, i) =>
        `${i > 0 ? '<span class="aql-stp-line"></span>' : ""}<span class="aql-stp${i === 0 ? " active" : ""}"><span class="aql-stp-dot"></span><span class="aql-stp-label">${esc(s)}</span></span>`,
    )
    .join("");
  const cards = _analyzeCards
    .map(
      (
        c,
      ) => `<div class="aql-card" style="left:${c.x}px;top:${c.y}px;border:1px solid ${c.border};color:${c.color}">
    <span class="aql-ico" style="background:${c.bg};color:${c.color}">${c.ico}</span>${esc(c.name)}</div>`,
    )
    .join("");
  return `<div class="aql-root${sizeCls}" role="status" aria-label="Loading">
    <div class="aql-scene">
      <div class="aql-stepper" aria-hidden="true">${stepper}</div>
      ${cards}
      <div class="aql-machine">
        <span class="aql-gear big">${_gearSVG(58, 15, "rgba(124,58,237,.9)", "rgba(196,181,253,.9)")}</span>
        <span class="aql-gear small">${_gearSVG(34, 11, "rgba(56,189,248,.85)", "rgba(186,230,253,.9)")}</span>
      </div>
      <div class="aql-msg" data-msgs='${esc(JSON.stringify(msgs))}' data-i="0"><div class="aql-msg-pill">${esc(msgs[0])}</div></div>
    </div></div>`;
}

// Global ticker cycles analyze-loader messages + phase steppers (auto-skips removed nodes).
let _brandTick = 0;
setInterval(() => {
  _brandTick++;
  document.querySelectorAll(".aql-msg[data-msgs]").forEach((el) => {
    let msgs;
    try {
      msgs = JSON.parse(el.dataset.msgs);
    } catch (e) {
      return;
    }
    if (!msgs.length) return;
    const i = _brandTick % msgs.length;
    if (String(i) === el.dataset.i) return;
    el.dataset.i = String(i);
    const pill = el.querySelector(".aql-msg-pill");
    if (pill) {
      pill.textContent = msgs[i];
      pill.classList.remove("swap");
      void pill.offsetWidth;
      pill.classList.add("swap");
    }
    // reflect progress in the stepper of the same scene
    const scene = el.closest(".aql-scene");
    if (scene) {
      const stps = [...scene.querySelectorAll(".aql-stp")];
      const active = Math.min(
        stps.length - 1,
        Math.floor(i / Math.max(1, Math.ceil(msgs.length / stps.length))),
      );
      stps.forEach((s, si) => {
        s.classList.toggle("active", si === active);
        s.classList.toggle("passed", si < active);
      });
    }
  });
}, 1900);

// Fullscreen branded loader overlay
function showBrandLoader(variant, opts) {
  hideBrandLoader();
  const ov = document.createElement("div");
  ov.className = "brand-loader-overlay";
  ov.id = "brand-loader-overlay";
  ov.innerHTML = brandLoader(
    variant,
    Object.assign({ inline: false }, opts || {}),
  );
  document.body.appendChild(ov);
  return ov;
}
function hideBrandLoader() {
  const ov = document.getElementById("brand-loader-overlay");
  if (ov) ov.remove();
}
// Inject a compact inline branded loader into a container by selector
function brandLoaderIn(sel, variant, opts) {
  const el = $(sel);
  if (el)
    el.innerHTML = brandLoader(
      variant || "analyze",
      Object.assign({ compact: true }, opts || {}),
    );
}

// ============ REFERENCE DASHBOARD COMPONENTS (ported from test-generator DashboardPage) ============
const RC_COLORS = {
  sky: "#38bdf8",
  violet: "#a78bfa",
  amber: "#fbbf24",
  emerald: "#34d399",
  rose: "#fb7185",
  teal: "#2dd4bf",
  slate: "#94a3b8",
};
const RC_ICONS = {
  testCases:
    "M9 11l3 3L22 4M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11",
  testPlan:
    "M9 5H7a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2M9 5a2 2 0 0 0 2 2h2a2 2 0 0 0 2-2M9 5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2",
  analysis: "M3 3v18h18M7 14l4-4 3 3 5-6",
  testCycles: "M3 12a9 9 0 1 0 9-9 9 9 0 0 0-7 3.5M3 4v4h4",
  coverage:
    "M12 2a10 10 0 1 0 10 10A10 10 0 0 0 12 2zM2 12h20M12 2a15 15 0 0 1 0 20",
};
const rcNum = (n) => Number(n || 0).toLocaleString();
function rcIcon(path) {
  return `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${path}"/></svg>`;
}
function rcMetric(o) {
  const subs =
    o.subs && o.subs.length
      ? `<dl class="rc-metric-subs">${o.subs.map((s) => `<div class="rc-metric-sub"><dt>${esc(s.label)}</dt><dd${s.tone ? ` style="color:${s.tone}"` : ""}>${esc(s.value)}</dd></div>`).join("")}</dl>`
      : "";
  return `<div class="rc-card hover rc-metric"><div class="rc-metric-top"><span style="color:${o.accent}">${o.icon || ""}</span><h2>${esc(o.title)}</h2></div>
    <div class="rc-metric-val">${esc(o.value)}</div>${o.caption ? `<div class="rc-metric-cap">${esc(o.caption)}</div>` : ""}${subs}</div>`;
}
function rcSection(title, body, extraCls) {
  return `<div class="rc-card hover rc-section ${extraCls || ""}"><h3 class="rc-section-title">${esc(title)}</h3>${body}</div>`;
}
function rcBars(items) {
  const upper = Math.max(1, ...items.map((i) => +i.value || 0));
  const total = items.reduce((s, i) => s + Math.max(0, +i.value || 0), 0);
  if (!total) return `<div class="rc-empty">No data yet</div>`;
  return (
    `<div class="rc-bars" role="img" aria-label="${esc(items.map((i) => i.label + ": " + i.value).join(", "))}">` +
    items
      .map((i) => {
        const pct = Math.round((Math.max(0, +i.value || 0) / upper) * 100);
        return (
          `<div class="rc-bar"><span class="rc-bar-lab">${esc(i.label)}</span>` +
          `<span class="rc-bar-track"><span class="rc-bar-fill" style="width:${pct}%;background:${i.color}"></span></span>` +
          `<span class="rc-bar-val">${rcNum(i.value)}</span></div>`
        );
      })
      .join("") +
    `</div>`
  );
}
function rcDonut(o) {
  const size = o.size || 132,
    thickness = o.thickness || 14,
    segs = o.segments || [];
  const total = segs.reduce((s, x) => s + Math.max(0, +x.value || 0), 0);
  const r = (size - thickness) / 2,
    circ = 2 * Math.PI * r,
    cx = size / 2;
  let off = 0;
  let arcs = `<circle cx="${cx}" cy="${cx}" r="${r}" fill="none" stroke="rgba(255,255,255,.05)" stroke-width="${thickness}"/>`;
  if (total > 0)
    segs.forEach((s) => {
      const v = Math.max(0, +s.value || 0);
      if (!v) return;
      const dash = (v / total) * circ;
      arcs += `<circle cx="${cx}" cy="${cx}" r="${r}" fill="none" stroke="${s.color}" stroke-width="${thickness}" stroke-linecap="butt" stroke-dasharray="${dash} ${circ - dash}" stroke-dashoffset="${-off}" transform="rotate(-90 ${cx} ${cx})"/>`;
      off += dash;
    });
  const center =
    o.centerValue != null || o.centerLabel
      ? `<g>${o.centerValue != null ? `<text x="${cx}" y="${cx - (o.centerLabel ? 2 : -5)}" text-anchor="middle" fill="#fff" style="font-size:18px;font-weight:600">${esc(o.centerValue)}</text>` : ""}${o.centerLabel ? `<text x="${cx}" y="${cx + 14}" text-anchor="middle" fill="#94a3b8" style="font-size:9px;letter-spacing:.08em;text-transform:uppercase">${esc(o.centerLabel)}</text>` : ""}</g>`
      : "";
  const legend = `<dl class="rc-legend">${segs.map((s) => `<div class="rc-legend-row"><span class="rc-legend-sw" style="background:${s.color}"></span><dt class="rc-legend-lab">${esc(s.label)}</dt><dd class="rc-legend-val">${rcNum(s.value)}</dd></div>`).join("")}${total === 0 ? `<div class="rc-empty">No data yet</div>` : ""}</dl>`;
  return `<div class="rc-donut" role="img" aria-label="${esc(segs.map((s) => s.label + ": " + s.value).join(", ")) || "No data"}"><svg viewBox="0 0 ${size} ${size}" width="${size}" height="${size}">${arcs}${center}</svg>${legend}</div>`;
}
function rcRing(o) {
  const size = o.size || 148,
    thickness = o.thickness || 16,
    pct = Math.max(0, Math.min(100, Math.round(o.percent || 0)));
  const r = (size - thickness) / 2,
    circ = 2 * Math.PI * r,
    cx = size / 2,
    dash = (pct / 100) * circ;
  const tone =
    pct >= 80
      ? RC_COLORS.emerald
      : pct >= 50
        ? RC_COLORS.amber
        : RC_COLORS.rose;
  return `<div style="display:flex;justify-content:center" role="img" aria-label="${esc(o.label || "")}: ${pct}%">
    <svg viewBox="0 0 ${size} ${size}" width="${size}" height="${size}">
      <circle cx="${cx}" cy="${cx}" r="${r}" fill="none" stroke="rgba(255,255,255,.05)" stroke-width="${thickness}"/>
      <circle cx="${cx}" cy="${cx}" r="${r}" fill="none" stroke="${tone}" stroke-width="${thickness}" stroke-linecap="round" stroke-dasharray="${dash} ${circ - dash}" transform="rotate(-90 ${cx} ${cx})"/>
      <text x="${cx}" y="${cx - 2}" text-anchor="middle" fill="#fff" style="font-size:22px;font-weight:600">${pct}%</text>
      ${o.label ? `<text x="${cx}" y="${cx + 16}" text-anchor="middle" fill="#94a3b8" style="font-size:9px;letter-spacing:.08em;text-transform:uppercase">${esc(o.label)}</text>` : ""}
    </svg></div>`;
}
// ----- second <script> block -----

const $ = (s) => document.querySelector(s);
// Escapes &, <, >, " and ' so the result is safe in BOTH element text and quoted
// HTML attribute contexts (e.g. href="...", title="..."). Entities decode back to
// the original characters when rendered, so this is also safe for text nodes.
const esc = (s) =>
  (s ?? "").toString().replace(
    /[&<>"']/g,
    (c) =>
      ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
      })[c],
  );
const escAttr = esc; // alias: same escaper is attribute-safe now
// ---- shared verdict + evidence renderers (used by Impact, PR coverage & Mind Map) ----
function vStatus(s) {
  const m = {
    matched: ["mm-covered", "matched"],
    covered: ["mm-covered", "covered"],
    review_needed: ["mm-partial", "review"],
    partial: ["mm-partial", "partial"],
    uncovered: ["mm-uncovered", "uncovered"],
  };
  const x = m[s];
  return x ? `<span class="badge ${x[0]}">${x[1]}</span>` : "";
}
function vConf(c, tier, stype) {
  return c != null
    ? `<span class="badge" title="confidence">${Math.round(c * 100)}%${tier ? ` · T${tier}` : ""}</span>`
    : stype === "ai"
      ? `<span class="pill" title="LLM-inferred (no exact code signal)">AI</span>`
      : "";
}
function vSignal(sig, stype) {
  return sig
    ? `<span class="pill" title="matched code signal">${esc(stype || "")}: ${esc(sig)}</span>`
    : "";
}
function vEvidence(ev) {
  return (ev || [])
    .map(
      (e) =>
        `<div class="muted" style="font-size:11.5px;margin-left:12px">↳ <code>${esc(e.file || "")}${e.line ? ":" + e.line : ""}</code>${e.sha ? ` <a class="pill" ${e.url ? `href="${e.url}" target="_blank"` : ""}>${esc((e.sha || "").slice(0, 7))}</a>` : ""}</div>`,
    )
    .join("");
}
// Priority badge — accepts High/Mid/Low, P1/P2/P3 or 1/2/3 (previously everything showed "Low").
// Canonical priority everywhere: High=red, Medium=blue, Low=green. Accepts High/Med/Low, P1/P2/P3, 1/2/3.
function prioKey(p) {
  const s = (p == null ? "" : p).toString().toLowerCase();
  if (["high", "critical", "p1", "1"].includes(s)) return "high";
  if (["medium", "mid", "p2", "2"].includes(s)) return "medium";
  return "low";
}
function prioLabel(p) {
  return { high: "High", medium: "Medium", low: "Low" }[prioKey(p)];
}
function prioBadge(p) {
  const k = prioKey(p);
  const C = {
    high: ["rgba(239,68,68,0.25)", "rgba(239,68,68,0.12)", "#fca5a5"],
    medium: ["rgba(59,130,246,0.25)", "rgba(59,130,246,0.12)", "#93c5fd"],
    low: ["rgba(34,197,94,0.25)", "rgba(34,197,94,0.12)", "#86efac"],
  }[k];
  return `<span style="font-size:10px;font-weight:600;padding:2px 8px;border-radius:999px;border:1px solid ${C[0]};background:${C[1]};color:${C[2]}">${prioLabel(p)}</span>`;
}
// Canonical step table (# / Step / Expected result) — same look as the test-case detail.
// Accepts dicts {action,expected} or "action → expected" / "action -> expected" strings.
function stepsHtml(steps) {
  if (!steps || !steps.length) return "";
  const norm = steps.map((s) => {
    if (typeof s === "string") {
      const p = s.split(/\s*(?:→|->)\s*/);
      return { action: p[0] || "", expected: p.slice(1).join(" → ") };
    }
    return { action: s.action || "", expected: s.expected || "" };
  });
  const rows = norm
    .map(
      (s, i) =>
        `<div class="case-step"><span class="case-step-num">${i + 1}.</span><span>${esc(s.action)}</span><span class="case-step-expected">${esc(s.expected || "No separate expected result")}</span></div>`,
    )
    .join("");
  return `<div class="case-steps-table" style="margin:8px 0 2px"><div class="case-step case-step-head"><span>#</span><span>Step</span><span>Expected result</span></div>${rows}</div>`;
}
// Turn raw backend / httpx error strings into a short, human message (used app-wide).
function cleanErr(detail, status) {
  let d = (detail == null ? "" : detail).toString().trim();
  d = d.replace(/\s*For more information check:\s*https?:\/\/\S+/gi, ""); // drop MDN hint
  d = d.replace(/(?:client|server) error '([^']+)' for url '[^']*'/gi, "$1"); // → "404 Not Found"
  d = d.replace(/\s*for url '[^']*'/gi, "");
  d = d
    .replace(/https?:\/\/\S+/g, "")
    .replace(/\s*\n\s*/g, " ")
    .replace(/[ \t]{2,}/g, " ")
    .trim();
  d = d.replace(/[:\s]+$/, "").trim();
  if (d) return d;
  // No useful detail from the server — give a friendly, status-aware fallback.
  const byStatus = {
    400: "That request wasn't valid. Please check your input and try again.",
    404: "We couldn't find what you were looking for.",
    408: "The request timed out. Please try again.",
    409: "That conflicts with something that already exists.",
    413: "The file or payload is too large.",
    422: "Some of the information provided couldn't be processed. Please review and try again.",
    429: "Too many requests — please wait a moment and try again.",
    500: "The server ran into a problem. Please try again in a moment.",
    502: "The server is unreachable right now (bad gateway). Please try again shortly.",
    503: "The service is temporarily unavailable. Please try again shortly.",
    504: "The server took too long to respond. Please try again.",
  };
  return (
    byStatus[status] ||
    `Request failed${status ? ` (${status})` : ""}. Please try again.`
  );
}
async function api(p, o) {
  // NOTE: never log request bodies or response payloads — they can carry PATs,
  // API keys, SMTP passwords, OTP codes and other secrets into the browser console.
  let r, raw;
  try {
    r = await fetch(p, o);
    raw = await r.text();
  } catch (netErr) {
    // Network / server-unreachable — give the user a clear, non-technical message.
    console.error(`[API Net] ${p}`, netErr);
    if (typeof toast === "function")
      toast(
        "Can't reach the server. Check that wardenIQ is running and your connection is active.",
        { type: "err", title: "Connection problem" },
      );
    throw new Error(
      "Can't reach the server — please check your connection and try again.",
    );
  }
  let j = {};
  try {
    j = raw ? JSON.parse(raw) : {};
  } catch (e) {
    j = { detail: raw || `Request failed with status ${r.status}` };
  }
  if (r.status === 401 && !p.startsWith("/api/auth/")) {
    // Includes session invalidation after a role change / disable / forced logout.
    ME = null;
    showLogin();
    if (typeof toast === "function")
      toast(j.detail || "Your session ended — please sign in again.", {
        type: "info",
        title: "Session expired",
      });
    throw new Error(j.detail || "Please sign in");
  }
  if (r.status === 403) {
    // Authorization denial — surface it instead of failing silently, and refresh
    // identity in case the user's role changed under them.
    if (typeof toast === "function")
      toast(j.detail || "You don't have permission to do that.", {
        type: "err",
        title: "Not allowed",
      });
    if (!p.startsWith("/api/auth/"))
      setTimeout(() => {
        try {
          refreshMe();
        } catch (e) {}
      }, 0);
    throw new Error(cleanErr(j.detail || "not permitted", r.status));
  }
  if (!r.ok) {
    throw new Error(cleanErr(j.detail, r.status));
  }
  return j;
}
let currentProject = null,
  currentFeature = null,
  currentFeatureData = null,
  currentFeatureCases = [],
  currentViewName = "dashboard";
const TITLES = {
  dashboard: "Dashboard",
  projects: "Projects & Repos",
  features: "Features",
  validator: "MCQ Validator",
  testplan: "Test Plan",
  cases: "Test Cases",
  gap: "Gap Analysis",
  cycles: "Code Analysis",
  testcycles: "Test Cycles",
  mindmap: "Mind Map",
  develop: "Start Developing",
  steps: "Step Library",
  usage: "LLM Usage & Cost",
  users: "Users",
  config: "Configuration",
};
let ME = null;
// Read-only accessor for React screens (src/lib/compatBridge.js) until the
// navigation state moves out of this file (#257).
function getCurrentProject() {
  return currentProject;
}
function setCurrentProject(id) {
  currentProject = id;
}
function getCurrentFeatureId() {
  return currentFeature;
}
function setCurrentFeature(id) {
  currentFeature = id;
}
function setCurrentFeatureData(f) {
  currentFeatureData = f;
  currentFeatureCases = (f && f.test_cases) || [];
}
// Signed-in user (or null), for React screens until identity moves to React (#257).
function getCurrentUser() {
  return ME;
}
function setCurrentUser(u) {
  ME = u;
}
function getCurrentViewName() {
  return currentViewName;
}

// ---- nav ----
function navigateTo(v) {
  currentViewName = v;
  const sidebarView = ["features", "validator", "testplan"].includes(v)
    ? "projects"
    : v;
  document
    .querySelectorAll("nav button")
    .forEach((x) =>
      x.classList.toggle("active", x.dataset.view === sidebarView),
    );
  document
    .querySelectorAll(".view")
    .forEach((s) => (s.hidden = s.id !== "view-" + v));
  $("#view-title").textContent = TITLES[v] || "";
  if (v === "dashboard") loadDashboard();
  if (v === "projects") {
    showProjectList();
    loadProjects();
    loadSyncStatus();
  }
  if (v === "features") {
    loadProjects();
    loadFeatures();
    if (currentFeature) openFeature(currentFeature);
    else showFeatureList();
  }
  if (v === "cases") initCases();
  if (v === "steps") loadSteps();
  if (v === "cycles") initCycles();
  if (v === "testcycles") initTestCycles();
  if (v === "mindmap") initMindmap();
  if (v === "config") loadConfig();
  if (v === "users") {
    loadProjectPicker();
    loadUsers();
    loadApiTokens();
    loadAudit();
  }
  if (v === "usage") loadUsage();
  if (v === "validator") initValidator();
  if (v === "testplan") initTestPlan();
  if (v === "gap") initGap();
  renderBreadcrumbs();
  updateBackbar();
  // Enforce viewer read-only on the freshly-shown view (now + after async loaders
  // inject their buttons).
  try {
    enforceViewerReadOnly();
    setTimeout(enforceViewerReadOnly, 400);
  } catch (e) {}
  // Remember where the user is so a refresh restores it instead of jumping to Dashboard.
  try {
    history.replaceState(null, "", "#" + v);
  } catch (e) {}
  try {
    localStorage.setItem(
      "wq_nav",
      JSON.stringify({
        view: v,
        project: currentProject,
        feature: currentFeature,
      }),
    );
  } catch (e) {}
}
document
  .querySelectorAll("nav button")
  .forEach((b) => (b.onclick = () => navigateTo(b.dataset.view)));
if ($("#sidebar-toggle"))
  $("#sidebar-toggle").onclick = () => {
    $("#app-shell").classList.toggle("sidebar-collapsed");
    const isCollapsed = $("#app-shell").classList.contains("sidebar-collapsed");
    $("#sidebar-toggle").textContent = isCollapsed ? "›" : "‹";
    $("#sidebar-toggle").setAttribute(
      "title",
      isCollapsed ? "Expand sidebar" : "Collapse sidebar",
    );
  };

function getProjectName(projectId) {
  if (window.allProjects) {
    const p = window.allProjects.find((x) => x.id === projectId);
    if (p) return p.name;
  }
  const activeTitle = $("#active-proj-title")?.textContent;
  if (activeTitle && activeTitle !== "Project") return activeTitle;
  const featTitle = $("#features-page-title")?.textContent;
  if (featTitle && featTitle !== "Features") return featTitle;
  return "Project";
}

window.goToProjects = () => {
  navigateTo("projects");
  showProjectList();
  loadProjects();
};

// "Analyze" on a project settings repo card (moved from 02-projects.js, #257):
// show Code Analysis with only that repo ticked.
window.gotoAnalyze = async (rid, pid) => {
  currentProject = pid;
  document
    .querySelectorAll("nav button")
    .forEach((x) => x.classList.toggle("active", x.dataset.view === "cycles"));
  document
    .querySelectorAll(".view")
    .forEach((s) => (s.hidden = s.id !== "view-cycles"));
  $("#view-title").textContent = TITLES.cycles;
  // The Code Analysis screen is React (features/code-analysis): it loads the
  // projects and this project's repos with only `rid` ticked.
  if (window.openCodeAnalysisFor) await window.openCodeAnalysisFor(pid, rid);
  loadCycles();
  toast("Repo selected — set days & click Analyze changes");
};

window.goToProjectFeatures = () => {
  currentFeature = null;
  navigateTo("features");
  showFeatureList();
};

window.goToFeatureWorkspace = () => {
  if (currentFeature) {
    navigateTo("features");
    openFeature(currentFeature);
  }
};

function renderBreadcrumbs() {
  updateBackbar();
}

function updateBackbar() {
  const bar = $("#backbar"),
    btn = $("#backbar-btn"),
    label = $("#backbar-label");
  if (!bar || !btn || !label) return;
  let show = true,
    text = "",
    handler = null;
  if (currentViewName === "projects" && !$("#project-detail-page")?.hidden) {
    text = "Project settings";
    handler = () => showProjectList();
  } else if (
    currentViewName === "features" &&
    !$("#feature-create-page")?.hidden
  ) {
    text = "Create feature";
    handler = () => showFeatureList();
  } else if (currentViewName === "features" && currentFeature) {
    text = "Feature workspace";
    handler = () => showFeatureList();
  } else if (currentViewName === "features" && currentProject) {
    text = "Features";
    handler = () => {
      navigateTo("projects");
      showProjectList();
      loadProjects();
    };
  } else if (["validator", "testplan", "gap"].includes(currentViewName)) {
    const labels = {
      validator: "Validator",
      testplan: "Test plan",
      gap: "Gap analysis",
    };
    text = labels[currentViewName];
    handler = () => navigateTo("features");
  } else if (currentViewName === "cases" && currentFeature) {
    text = "Test Cases";
    handler = () => navigateTo("features");
  } else {
    show = false;
  }
  bar.classList.toggle("show", show);
  btn.onclick = handler || null;

  if (show) {
    const crumbs = [];
    crumbs.push({
      label: "Projects & Repos",
      action: "goToProjects()",
    });

    if (currentProject) {
      const projName = getProjectName(currentProject);
      const isProjectCurrent =
        currentViewName === "features" &&
        !currentFeature &&
        (!$("#feature-create-page") || $("#feature-create-page").hidden);
      crumbs.push({
        label: projName,
        action: isProjectCurrent ? null : "goToProjectFeatures()",
      });

      if (
        currentViewName === "projects" &&
        !$("#project-detail-page")?.hidden
      ) {
        crumbs.push({ label: "Settings", action: null });
      } else if (
        currentViewName === "features" &&
        !$("#feature-create-page")?.hidden
      ) {
        crumbs.push({ label: "Create feature", action: null });
      } else if (currentFeature) {
        const featName = currentFeatureData?.name || "Feature";
        const isFeatureCurrent = currentViewName === "features";
        crumbs.push({
          label: featName,
          action: isFeatureCurrent ? null : "goToFeatureWorkspace()",
        });

        if (currentViewName === "validator") {
          crumbs.push({ label: "Validator", action: null });
        } else if (currentViewName === "testplan") {
          crumbs.push({ label: "Test plan", action: null });
        } else if (currentViewName === "gap") {
          crumbs.push({ label: "Gap analysis", action: null });
        } else if (currentViewName === "cases") {
          crumbs.push({ label: "Test cases", action: null });
        }
      } else if (currentViewName === "cases") {
        crumbs.push({ label: "Test cases", action: null });
      }
    }

    label.innerHTML = crumbs
      .map((c, i) => {
        const isLast = i === crumbs.length - 1;
        if (isLast) {
          return `<span class="crumb active">${esc(c.label)}</span>`;
        } else {
          return `<span class="crumb clickable" onclick="${c.action}">${esc(c.label)}</span><span class="separator">›</span>`;
        }
      })
      .join("");
  } else {
    label.innerHTML = "";
  }
}

window.clickBreadcrumb = function (stepId) {
  if (stepId === "projects") {
    navigateTo("projects");
  } else if (stepId === "features") {
    if (!currentProject) {
      toast("Please select a project first.");
      return;
    }
    currentFeature = null;
    navigateTo("features");
  } else if (stepId === "workspace") {
    if (!currentProject) {
      toast("Please select a project first.");
      return;
    }
    if (!currentFeature) {
      toast("Please select a feature first.");
      return;
    }
    navigateTo("features");
  }
};

// ---- status ----
// Human-readable Vector Search copy from app/core/bootstrap.py (_SEARCH_REQUIRED_MSG).
// Shown when boot failed but the API still has a raw driver exception in boot.detail.
const BOOT_VECTOR_SEARCH_MSG =
  "wardenIQ requires a MongoDB with Vector Search — it's where embeddings are searched. The database at MONGO_URI doesn't have it. Use MongoDB Atlas (search built in) or a self-managed MongoDB running mongot, then restart.";
// Allowlist of KNOWN-SAFE, canned messages (all authored by app/core/bootstrap.py —
// see _SEARCH_REQUIRED_MSG, _SEARCH_INDEX_LIMIT_MSG, and the insecure-secret /
// insecure-production-posture messages in _check_app_secret / _check_production_posture).
// Anything NOT in this list is treated as potentially-raw backend/driver text and kept
// out of the primary summary (see looksLikeRawBootDetail below).
const BOOT_SAFE_DETAIL_MARKERS = [
  "requires a MongoDB with Vector Search",
  "doesn't allow enough search indexes",
  "insecure APP_SECRET",
  "insecure production configuration",
];

// Deliberately an ALLOWLIST, not a blocklist: boot.detail can carry an arbitrary
// exception from any driver/library in the backend's call stack (pymongo, the OS
// resolver, mongot, …), and that space is unbounded — a blocklist of known raw-dump
// signatures (msgLen/ProtocolError/pymongo/etc.) will always be one exception shape
// behind (confirmed in practice: a plain `pymongo.errors.ConfigurationError` DNS
// failure matched none of the old signatures and was shown verbatim as the primary
// banner text). The set of SAFE messages, by contrast, is small and entirely owned
// by this app (BOOT_SAFE_DETAIL_MARKERS above) — enumerating what we trust is
// tractable in a way enumerating what we don't trust never is. So: safe only if it
// matches a known canned message; everything else stays behind the Details
// disclosure, regardless of whether it happens to look like a "recognizable" dump.
function looksLikeRawBootDetail(detail) {
  const d = String(detail || "");
  if (!d) return false;
  return !BOOT_SAFE_DETAIL_MARKERS.some((m) => d.includes(m));
}

function formatBootStatus(boot) {
  boot = boot || {};
  const stage = String(boot.stage || "");
  const detail = String(boot.detail || "");
  if (boot.ready) return { visible: false, kind: "ok", summary: "", raw: "" };

  const raw = looksLikeRawBootDetail(detail) ? detail : "";
  const safeDetail = raw ? "" : detail;

  if (stage === "error") {
    return {
      visible: true,
      kind: "error",
      summary: safeDetail || BOOT_VECTOR_SEARCH_MSG,
      raw,
    };
  }
  if (stage === "indexing") {
    return {
      visible: true,
      kind: "warn",
      summary: "Setting up Vector Search indexes…",
      raw: detail,
    };
  }
  if (stage === "connecting") {
    return {
      visible: true,
      kind: "warn",
      summary: "Connecting to MongoDB…",
      raw: detail,
    };
  }
  return {
    visible: true,
    kind: "warn",
    summary: stage ? `Starting up (${stage})` : "Starting up…",
    raw: raw || "",
  };
}

function bootBannerDetailsHtml(raw) {
  if (!raw) return "";
  return (
    `<details class="boot-banner-details">` +
    `<summary>Details</summary>` +
    `<pre class="boot-banner-raw">${esc(raw)}</pre>` +
    `</details>`
  );
}

function applyBootBanner(formatted) {
  const el = $("#boot-banner");
  if (!el) return;
  if (!formatted || !formatted.visible) {
    el.hidden = true;
    el.innerHTML = "";
    el.removeAttribute("data-kind");
    return;
  }
  el.hidden = false;
  el.dataset.kind = formatted.kind || "warn";
  if (formatted.raw) {
    try {
      console.warn("[wardenIQ] boot detail:", formatted.raw);
    } catch (e) {}
  }
  const icon = formatted.kind === "error" ? "⚠" : "●";
  el.innerHTML =
    `<span class="boot-banner-msg">${icon} ${esc(formatted.summary)}</span>` +
    bootBannerDetailsHtml(formatted.raw);
}

async function refreshStatus() {
  if ($("#status") && !$("#status").dataset.loaded)
    $("#status").innerHTML =
      `<span class="stat"><span class="spin-inline"></span>Checking services…</span>`;
  try {
    const s = await api("/api/status");
    const c = s.counts || {};
    if ($("#status")) $("#status").dataset.loaded = "1";
    // Keep #status to compact service chips only — long boot copy belongs in
    // the in-flow #boot-banner so it cannot overlay the sticky header chrome.
    $("#status").innerHTML =
      `<span class="status-group">` +
      `<span class="stat" title="MongoDB connection">${dot(s.mongo_connected)}Mongo</span>` +
      `<span class="stat" title="Embeddings: ${esc(s.embedding?.provider || "")}${s.embedding?.dims ? " · " + s.embedding.dims + "-d" : ""}${s.embedding?.health?.error ? " · " + s.embedding.health.error : ""}">${dot(s.embedding?.health?.ok)}${esc(s.embedding?.model)}</span>` +
      `<span class="stat" title="LLM: ${esc(s.llm?.health?.error || s.llm?.provider || "")}">${dot(s.llm?.health?.ok)}${esc(s.llm?.model)}</span>` +
      `</span>` +
      `<span class="stat-metric" title="Features and test cases in scope"><span><b>${c.features || 0}</b> features</span><span class="sep"></span><span><b>${c.test_cases || 0}</b> cases</span></span>`;
    applyBootBanner(formatBootStatus(s.boot));
  } catch (e) {
    const raw = e && e.message ? String(e.message) : "";
    applyBootBanner({
      visible: true,
      kind: "error",
      summary: looksLikeRawBootDetail(raw)
        ? "Can't load service status right now."
        : raw || "Can't load service status right now.",
      raw: looksLikeRawBootDetail(raw) ? raw : "",
    });
    if ($("#status") && !$("#status").dataset.loaded) {
      $("#status").innerHTML = `<span class="stat">${dot(false)}Status unavailable</span>`;
    }
  }
}
const dot = (ok) => `<span class="dot ${ok ? "ok" : "bad"}"></span>`;

