import { useEffect, useState } from "react";

// Loader / skeleton / spinner components — idiomatic React ports of the
// feedback widgets in app/static/index.html.
//
// Two tiers, by animation complexity:
//   • Simple (Spinner, Skeleton*): pure inline Tailwind. The shimmer keyframe is
//     registered in tailwind.config.js (animate-shimmer); the spinner uses the
//     built-in animate-spin.
//   • Branded (WardenIQLoader, AnalyzeLoader): these use ~30 staggered, per-
//     element keyframes that don't map cleanly to utility classes, so they keep
//     their `wql-*` / `aql-*` class rules in global.css (kept in sync with
//     index.html). The components below just render the markup + drive the
//     runtime bits (the analyze message ticker) in React.

// ---------------------------------------------------------------------------
// Spinner — inline (status text) or in-button.
// ---------------------------------------------------------------------------
export function Spinner({ size = 13, className = "" }) {
  return (
    <span
      role="status"
      aria-label="Loading"
      className={
        "inline-block animate-spin rounded-full border-2 border-[rgba(125,154,194,.28)] border-t-[#7cb0ea] " +
        className
      }
      style={{ width: size, height: size }}
    />
  );
}

export function LoadingRow({ children = "Loading…" }) {
  return (
    <div className="flex items-center gap-2.5 px-0.5 py-2 text-[12.5px] text-muted">
      <Spinner />
      <span>{children}</span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Skeletons — shimmering placeholders. `animate-shimmer` + the gradient below
// reproduce the `.sk` look from index.html.
// ---------------------------------------------------------------------------
const SK_BASE =
  "relative overflow-hidden rounded-lg bg-[#151d29] bg-[linear-gradient(90deg,rgba(255,255,255,.02)_0%,rgba(255,255,255,.07)_45%,rgba(255,255,255,.02)_90%)] bg-[length:320px_100%] bg-no-repeat animate-shimmer";

export function Skeleton({ className = "", style }) {
  return <div className={SK_BASE + " " + className} style={style} />;
}

export function SkeletonLine({ size }) {
  const dims =
    size === "sm" ? "h-2.5 w-[55%]" : size === "lg" ? "h-4 w-[70%]" : "h-3";
  return <Skeleton className={"my-2 rounded-md " + dims} />;
}

export function SkeletonCard() {
  return (
    <div className="min-h-[154px] rounded-2xl border border-[rgba(116,139,166,.16)] bg-[linear-gradient(145deg,rgba(24,34,48,.6),rgba(13,20,30,.7))] p-[22px]">
      <SkeletonLine size="lg" />
      <SkeletonLine />
      <SkeletonLine size="sm" />
    </div>
  );
}

export function SkeletonGrid({ count = 6 }) {
  return (
    <div className="grid grid-cols-[repeat(auto-fill,minmax(260px,1fr))] gap-4">
      {Array.from({ length: count }).map((_, i) => (
        <SkeletonCard key={i} />
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Gear SVG — React port of _gearSVG() (AnalyzeLoader).
// ---------------------------------------------------------------------------
function Gear({ size, teeth, fill, stroke, className = "" }) {
  const r = size / 2;
  const inner = r * 0.58;
  const toothH = r * 0.24;
  const hole = r * 0.23;
  const step = (Math.PI * 2) / teeth;
  const pt = (a, rad) => [Math.cos(a) * rad, Math.sin(a) * rad];
  let d = "";
  for (let i = 0; i < teeth; i++) {
    const a0 = step * i - step * 0.36;
    const a1 = step * i - step * 0.14;
    const a2 = step * i + step * 0.14;
    const a3 = step * i + step * 0.36;
    const [x0, y0] = pt(a0, inner);
    const [x1, y1] = pt(a1, r + toothH);
    const [x2, y2] = pt(a2, r + toothH);
    const [x3, y3] = pt(a3, inner);
    if (i === 0) d += `M ${x0.toFixed(2)},${y0.toFixed(2)} `;
    d += `L ${x1.toFixed(2)},${y1.toFixed(2)} L ${x2.toFixed(2)},${y2.toFixed(2)} L ${x3.toFixed(2)},${y3.toFixed(2)} `;
  }
  d += "Z";
  const vb = r + toothH + 2;
  return (
    <svg
      width={(vb * 2).toFixed(0)}
      height={(vb * 2).toFixed(0)}
      viewBox={`${-vb} ${-vb} ${vb * 2} ${vb * 2}`}
      style={{ overflow: "visible" }}
      className={className}
    >
      <path d={d} fill={fill} stroke={stroke} strokeWidth="1.3" />
      <circle r={hole.toFixed(2)} fill="none" stroke={stroke} strokeWidth="1.6" />
      <circle r={(hole * 0.38).toFixed(2)} fill={stroke} opacity="0.75" />
    </svg>
  );
}

// ---------------------------------------------------------------------------
// WardenIQLoader — the "quiz" branded loader.
// ---------------------------------------------------------------------------
export function WardenIQLoader({
  compact = false,
  inline = true,
  steps = ["Analyzing inputs", "AI Processing", "Generating output"],
  questionLabel = "Question 01",
  optionLabel = "Option:",
}) {
  const sizeCls = compact ? " compact" : inline ? " inline" : "";
  return (
    <div className={"wql-root" + sizeCls} role="status" aria-label="Loading">
      <div className="wql-shell">
        <div className="wql-stepper" aria-hidden="true">
          <span className="wql-step wql-step-1">
            <span className="wql-step-dot" />
            {steps[0]}
          </span>
          <span className="wql-step-line" />
          <span className="wql-step wql-step-2">
            <span className="wql-step-dot" />
            {steps[1]}
          </span>
          <span className="wql-step-line" />
          <span className="wql-step wql-step-3">
            <span className="wql-step-dot" />
            {steps[2]}
          </span>
        </div>
        <div className="wql-stack">
          <div className="wql-qcard">
            <div className="wql-qtitle">{questionLabel}</div>
            <div className="wql-qrow">
              <div className="wql-track">
                <div className="wql-line" />
              </div>
              <div className="wql-qmark">?</div>
            </div>
          </div>
          <div className="wql-ocard">
            <div className="wql-otitle">{optionLabel}</div>
            <div className="wql-olist" aria-hidden="true">
              {[1, 2, 3, 4].map((n) => (
                <div key={n} className={"wql-orow wql-row-" + n}>
                  <span className="wql-odot" />
                  <span className={"wql-oline wql-l" + n} />
                </div>
              ))}
            </div>
          </div>
          <button className="wql-next" type="button" tabIndex={-1}>
            Next
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// AnalyzeLoader — the "gear machine" branded loader, with a live message ticker.
// ---------------------------------------------------------------------------
const ANALYZE_STEPS = ["Analyzing inputs", "AI processing", "Generating output"];
const ANALYZE_MESSAGES = [
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

export function AnalyzeLoader({
  compact = false,
  inline = true,
  steps = ANALYZE_STEPS,
  messages = ANALYZE_MESSAGES,
}) {
  const sizeCls = compact ? " compact" : inline ? " inline" : "";
  const [i, setI] = useState(0);
  const [swap, setSwap] = useState(false);

  useEffect(() => {
    const t = setInterval(() => {
      setI((prev) => (prev + 1) % messages.length);
      setSwap(true);
    }, 1900);
    return () => clearInterval(t);
  }, [messages.length]);

  useEffect(() => {
    if (!swap) return;
    const t = setTimeout(() => setSwap(false), 320);
    return () => clearTimeout(t);
  }, [swap]);

  const active = Math.min(
    steps.length - 1,
    Math.floor(i / Math.max(1, Math.ceil(messages.length / steps.length)))
  );

  return (
    <div className={"aql-root" + sizeCls} role="status" aria-label="Loading">
      <div className="aql-scene">
        <div className="aql-stepper" aria-hidden="true">
          {steps.map((s, si) => (
            <span key={si} style={{ display: "contents" }}>
              {si > 0 && <span className="aql-stp-line" />}
              <span className={"aql-stp" + (si === active ? " active" : si < active ? " passed" : "")}>
                <span className="aql-stp-dot" />
                <span className="aql-stp-label">{s}</span>
              </span>
            </span>
          ))}
        </div>
        {ANALYZE_CARDS.map((c) => (
          <div
            key={c.name}
            className="aql-card"
            style={{ left: c.x, top: c.y, border: `1px solid ${c.border}`, color: c.color }}
          >
            <span className="aql-ico" style={{ background: c.bg, color: c.color }}>
              {c.ico}
            </span>
            {c.name}
          </div>
        ))}
        <div className="aql-machine">
          <span className="aql-gear big">
            <Gear size={58} teeth={15} fill="rgba(124,58,237,.9)" stroke="rgba(196,181,253,.9)" />
          </span>
          <span className="aql-gear small">
            <Gear size={34} teeth={11} fill="rgba(56,189,248,.85)" stroke="rgba(186,230,253,.9)" />
          </span>
        </div>
        <div className="aql-msg">
          <div className={"aql-msg-pill" + (swap ? " swap" : "")}>{messages[i]}</div>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// BrandLoaderOverlay — fullscreen host for either branded loader.
// ---------------------------------------------------------------------------
export function BrandLoaderOverlay({ variant = "analyze", ...opts }) {
  return (
    <div className="brand-loader-overlay">
      {variant === "quiz" ? (
        <WardenIQLoader inline={false} {...opts} />
      ) : (
        <AnalyzeLoader inline={false} {...opts} />
      )}
    </div>
  );
}
