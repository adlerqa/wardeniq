/**
 * Branded loaders (was 00-core.js; ported from the wardenIQ test-generator app),
 * as HTML strings: "analyze" (gear machine with rotating status messages) and
 * "quiz". Screens insert them with dangerouslySetInnerHTML (bridge
 * brandLoaderHtml); startBrandTicker cycles the analyze messages and stepper of
 * every loader on the page. Registered by useSharedGlobals.
 */
import { escapeHtml as esc } from "./html.js";

/** Gear outline SVG (ported from AnalyzeLoader GearSVG). */
export function gearSVG(size, teeth, fill, stroke) {
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

export const ANALYZE_STEPS = ["Analyzing inputs", "AI processing", "Generating output"];
export const ANALYZE_MESSAGES = [
  "Checking readiness…",
  "Processing sources…",
  "Building AI context…",
  "Generating outputs…",
  "Finalizing workspace…",
];
const ANALYZE_CARDS = [
  { ico: "✓", color: "#a78bfa", border: "rgba(139,92,246,.55)", bg: "rgba(139,92,246,.18)", name: "requirements.txt", x: 8, y: 26 },
  { ico: "⚠", color: "#fb923c", border: "rgba(251,146,60,.5)", bg: "rgba(251,146,60,.15)", name: "bug_report.md", x: 0, y: 112 },
  { ico: "?", color: "#818cf8", border: "rgba(99,102,241,.5)", bg: "rgba(99,102,241,.18)", name: "ambiguous.spec", x: 18, y: 196 },
  { ico: "≡", color: "#38bdf8", border: "rgba(56,189,248,.5)", bg: "rgba(56,189,248,.15)", name: "api_docs.yaml", x: 300, y: 56 },
];

/**
 * Loader HTML. variant: "analyze" (default) | "quiz".
 * opts: { compact, inline, messages, steps, questionLabel, optionLabel }
 */
export function brandLoader(variant, opts) {
  opts = opts || {};
  const sizeCls = opts.compact ? " compact" : opts.inline === false ? "" : " inline";
  if (variant === "quiz") {
    const steps = opts.steps || ["Analyzing inputs", "AI Processing", "Generating output"];
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
  const steps = opts.steps || ANALYZE_STEPS;
  const msgs = opts.messages || ANALYZE_MESSAGES;
  const stepper = steps
    .map(
      (s, i) =>
        `${i > 0 ? '<span class="aql-stp-line"></span>' : ""}<span class="aql-stp${i === 0 ? " active" : ""}"><span class="aql-stp-dot"></span><span class="aql-stp-label">${esc(s)}</span></span>`,
    )
    .join("");
  const cards = ANALYZE_CARDS.map(
    (c) => `<div class="aql-card" style="left:${c.x}px;top:${c.y}px;border:1px solid ${c.border};color:${c.color}">
    <span class="aql-ico" style="background:${c.bg};color:${c.color}">${c.ico}</span>${esc(c.name)}</div>`,
  ).join("");
  return `<div class="aql-root${sizeCls}" role="status" aria-label="Loading">
    <div class="aql-scene">
      <div class="aql-stepper" aria-hidden="true">${stepper}</div>
      ${cards}
      <div class="aql-machine">
        <span class="aql-gear big">${gearSVG(58, 15, "rgba(124,58,237,.9)", "rgba(196,181,253,.9)")}</span>
        <span class="aql-gear small">${gearSVG(34, 11, "rgba(56,189,248,.85)", "rgba(186,230,253,.9)")}</span>
      </div>
      <div class="aql-msg" data-msgs='${esc(JSON.stringify(msgs))}' data-i="0"><div class="aql-msg-pill">${esc(msgs[0])}</div></div>
    </div></div>`;
}

/** One tick: every analyze loader on the page shows message `tick % n` and the matching step. */
export function brandTick(tick, doc = document) {
  doc.querySelectorAll(".aql-msg[data-msgs]").forEach((el) => {
    let msgs;
    try {
      msgs = JSON.parse(el.dataset.msgs);
    } catch {
      return;
    }
    if (!msgs.length) return;
    const i = tick % msgs.length;
    if (String(i) === el.dataset.i) return;
    el.dataset.i = String(i);
    const pill = el.querySelector(".aql-msg-pill");
    if (pill) {
      pill.textContent = msgs[i];
      pill.classList.remove("swap");
      void pill.offsetWidth; // restart the swap animation
      pill.classList.add("swap");
    }
    const scene = el.closest(".aql-scene");
    if (scene) {
      const stps = [...scene.querySelectorAll(".aql-stp")];
      const active = Math.min(stps.length - 1, Math.floor(i / Math.max(1, Math.ceil(msgs.length / stps.length))));
      stps.forEach((s, si) => {
        s.classList.toggle("active", si === active);
        s.classList.toggle("passed", si < active);
      });
    }
  });
}

/** Ticks every 1.9 s for the whole page. Returns a stop function. */
export function startBrandTicker(doc = document) {
  let tick = 0;
  const id = setInterval(() => brandTick(++tick, doc), 1900);
  return () => clearInterval(id);
}
