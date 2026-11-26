/**
 * HTML-string renderers for screens that still build markup as strings (Gap
 * Analysis). Was 00-core.js prioBadge / stepsHtml; the React screens use
 * features/test-cases/components/PriorityBadge.jsx and their own step table.
 * Registered on window by useSharedGlobals.
 */
import { escapeHtml as esc } from "./html.js";
import { PRIO_COLORS, prioKey, prioLabel } from "../features/test-cases/lib/testCases.js";

/** Priority pill: High red, Medium blue, Low green (accepts High/Med/Low, P1/P2/P3, 1/2/3). */
export function prioBadge(p) {
  const C = PRIO_COLORS[prioKey(p)];
  return `<span style="font-size:10px;font-weight:600;padding:2px 8px;border-radius:999px;border:1px solid ${C[0]};background:${C[1]};color:${C[2]}">${prioLabel(p)}</span>`;
}

/**
 * The # / Step / Expected result table, same look as the test-case detail.
 * Steps are { action, expected } or "action → expected" / "action -> expected" strings.
 */
export function stepsHtml(steps) {
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
