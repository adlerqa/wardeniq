/**
 * Skeleton placeholders as HTML strings, for the Gap Analysis loading states
 * (same markup as before). Other screens use components/feedback/Skeleton.jsx.
 */
import { escapeHtml } from "./html.js";

export function skeletonState(body, label = "Loading content") {
  return `<div class="sk-state" role="status" aria-label="${escapeHtml(label)}">${body}</div>`;
}

export const skeleton = {
  line(w) {
    return `<div class="sk sk-line"${w ? ` style="width:${w}"` : ""}></div>`;
  },
  cards(n = 6, label = "Loading cards") {
    let c = "";
    for (let i = 0; i < n; i++)
      c += `<div class="sk-card"><div class="sk sk-line lg"></div><div class="sk sk-line sm"></div><div class="sk sk-line" style="width:40%;margin-top:22px"></div></div>`;
    return skeletonState(`<div class="sk-grid">${c}</div>`, label);
  },
  kpis(n = 7) {
    let c = "";
    for (let i = 0; i < n; i++)
      c += `<div class="sk-kpi"><div class="sk sk-line" style="width:50%;height:24px"></div><div class="sk sk-line sm" style="margin-top:10px"></div></div>`;
    return c;
  },
  rows(n = 5, label = "Loading rows") {
    let c = "";
    for (let i = 0; i < n; i++)
      c += `<div class="sk-row"><div class="sk sk-dot"></div><div style="flex:1"><div class="sk sk-line lg" style="margin:0 0 8px"></div><div class="sk sk-line sm" style="margin:0"></div></div><div class="sk sk-badge"></div></div>`;
    return skeletonState(`<div class="sk-row-wrap">${c}</div>`, label);
  },
  table(cols = 5, n = 5, label = "Loading table") {
    const head = `<tr>${Array(cols).fill('<th><div class="sk sk-line sm" style="margin:0;width:70%"></div></th>').join("")}</tr>`;
    let body = "";
    for (let i = 0; i < n; i++)
      body += `<tr>${Array(cols).fill('<td><div class="sk sk-line" style="margin:0"></div></td>').join("")}</tr>`;
    return skeletonState(`<div style="overflow:auto"><table>${head}${body}</table></div>`, label);
  },
  block(label = "Loading details") {
    return skeletonState(
      `<div class="sk sk-line lg"></div><div class="sk sk-line"></div><div class="sk sk-line sm"></div>`,
      label,
    );
  },
  dashboard() {
    return skeletonState(
      `<div class="sk sk-line lg" style="width:180px;height:24px;margin-bottom:20px"></div>` +
        `<div class="dash-metrics">${this.kpis(7)}</div>` +
        `<div class="dash-row c2"><div class="sk-card">${this.kpis(2)}</div><div class="sk-card">${this.blockLines(5)}</div></div>` +
        `<div class="sk-card" style="margin-top:16px">${this.blockLines(6)}</div>`,
      "Loading dashboard",
    );
  },
  blockLines(n = 4) {
    let c = "";
    for (let i = 0; i < n; i++) c += `<div class="sk sk-line${i === 0 ? " lg" : i === n - 1 ? " sm" : ""}"></div>`;
    return c;
  },
};
