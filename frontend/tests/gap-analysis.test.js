import assert from "node:assert/strict";
import { createRequire } from "node:module";
import test from "node:test";
import { fileURLToPath } from "node:url";
import vm from "node:vm";
import { build } from "esbuild";
import { JSDOM } from "jsdom";
import React, { act } from "react";

import { manualRunBody, runCard, runDetail } from "../src/features/gap-analysis/lib/gap.js";

const dom = new JSDOM("<!doctype html><body></body>", { url: "http://localhost/" });
const { window } = dom;
const { document } = window;
Object.assign(globalThis, { window, document, IS_REACT_ACT_ENVIRONMENT: true });
const { createRoot } = await import("react-dom/client");
test.after(() => window.close());
const require = createRequire(import.meta.url);
const settle = () => new Promise((r) => setTimeout(r, 0));
const bundled = await build({
  entryPoints: [fileURLToPath(new URL("../src/features/gap-analysis/pages/GapAnalysisPage.jsx", import.meta.url))],
  bundle: true, write: false, format: "cjs", platform: "neutral", jsx: "automatic",
  external: ["react", "react/jsx-runtime", "react-dom"], logLevel: "silent",
});

// issue #291: a "partial" match (the PR touches relevant code but the implementation
// was not confirmed) is shown and labelled, and kept out of the covered counts.
const run = (over = {}) => ({
  id: "r1", pr_number: 7, pr_title: "Fix reset", status: "done", tests_total: 3,
  tests_covered: 0, tests_partial: 0, source: "webhook", ...over,
});
const cases = [
  { id: "c1", title: "Case one", type: "functional", priority: "P2", steps: [] },
  { id: "c2", title: "Case two", type: "functional", priority: "P2", steps: [] },
  { id: "c3", title: "Case three", type: "functional", priority: "P2", steps: [] },
];
const entry = (id, status, rationale = "r") => ({ test_case_id: id, ...(status === undefined ? {} : { status }), rationale, by_dev_test: false });
const detailFor = (covered, comparison = {}) => ({
  id: "r1", feature_id: "f1", pr_number: 7, pr_title: "Fix reset", pr_branch: "feat/x", repo_full_name: "acme/app",
  head_sha: "abcdef0123", tests_total: 3, feature_cases: cases, result: { covered, comparison },
});

test("run cards: partial matches are listed but not counted", () => {
  assert.deepEqual([runCard(run({ tests_partial: 3 })), runCard(run({ tests_covered: 1, tests_partial: 2 }))].map((c) => [c.covered, c.total, c.pct, c.partial]),
    [[0, 3, 0, 3], [1, 3, 33, 2]]);
  assert.equal(runCard(run({ tests_covered: 2, tests_partial: undefined })).partial, 0);
});

test("run detail model: partial is a gap; entries without status count as covered", () => {
  let d = runDetail(detailFor([entry("c1", "partial"), entry("c2", "covered")]));
  assert.deepEqual([d.cov, d.total, d.partialCount, d.gaps], [1, 3, 1, 2]);
  assert.deepEqual(d.sections[0].covered.map((c) => c.id), ["c2"]);
  assert.deepEqual(d.sections[0].missing.map((c) => [c.id, !!c.partial]), [["c1", true], ["c3", false]]);
  d = runDetail(detailFor([entry("c1", undefined), entry("c2", undefined)]));
  assert.deepEqual([d.cov, d.partialCount], [2, 0]);
});

test("manual run: a URL, a PR number on the first App repo, or an error", () => {
  assert.deepEqual(manualRunBody("f", " https://github.com/a/b/pull/7 ", []), { body: { feature_id: "f", pr_url: "https://github.com/a/b/pull/7" } });
  assert.deepEqual(manualRunBody("f", "#42", [{ id: "t", repo_type: "test" }, { id: "a" }]), { body: { feature_id: "f", repo_id: "a", pr_number: 42 } });
  assert.deepEqual(manualRunBody("f", "42", [{ id: "t", repo_type: "test" }]), { error: "No App repos connected on this project" });
  assert.deepEqual(manualRunBody("f", "abc", [{ id: "a" }]), { error: "Enter a numeric PR number or a full PR/MR URL" });
});

async function mount(t, routes) {
  const calls = [];
  const reply = (status, body) => ({ status, ok: status < 400, text: async () => JSON.stringify(body), json: async () => body });
  const fakeFetch = async (path, opts = {}) => {
    calls.push([opts.method || "GET", path]);
    const r = routes[path];
    return typeof r === "function" ? r() : reply(200, r || {});
  };
  Object.assign(window, { toast: () => {}, getCurrentFeatureId: () => "f1", getCurrentProject: () => "p1" });
  const module = { exports: {} };
  vm.runInNewContext(bundled.outputFiles[0].text, { module, exports: module.exports, require, window, document, console, fetch: fakeFetch, setTimeout, clearTimeout });
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  await act(async () => root.render(React.createElement(module.exports.default)));
  t.after(async () => { await act(async () => root.unmount()); container.remove(); });
  const flush = (fn) => act(async () => { await fn?.(); for (let i = 0; i < 6; i++) await settle(); });
  return { $: (s) => container.querySelector(s), $$: (s) => [...container.querySelectorAll(s)], calls, flush };
}

test("screen: run cards, a run's detail with covered / missing toggle and partial labels", async (t) => {
  const h = await mount(t, {
    "/api/features/f1/code-coverage/runs?limit=50": { runs: [run({ tests_covered: 1, tests_partial: 2, pr_id: "pr1" })] },
    "/api/code-coverage/runs/r1": detailFor([entry("c1", "partial", "touches reset.py, not confirmed"), entry("c2", "covered")]),
  });
  await h.flush(() => window.initGap());
  assert.equal(h.$("#gap-workspace").style.display, "block");
  const card = h.$("#gap-pr-list .repo-item-card");
  assert.match(card.textContent, /1\/3 covered/);
  assert.match(card.textContent, /33% · 2 partial, not counted · webhook/);
  assert.equal(card.querySelector("button").textContent, "Exclude");
  await h.flush(() => card.click());
  const body = h.$("#gap-pr-detail-body");
  assert.equal(h.$("#gap-pr-detail").style.display, "block");
  assert.match(body.textContent, /1 \/ 3Tests covered\+ 1 partial, not counted/);
  assert.match(body.textContent, /2Gaps/);
  assert.match(body.querySelector("summary").textContent, /1 covered · 2 missing \(1 partial\)/);
  assert.equal(body.querySelector(".cov-list-covered-functional").dataset.count, "1");
  assert.equal(body.querySelector(".cov-list-missing-functional").style.display, "none");
  await h.flush(() => body.querySelectorAll(".cov-toggle-btn")[1].click());
  assert.equal(body.querySelector(".cov-list-missing-functional").style.display, "block");
  assert.equal(body.querySelector(".cov-status-badge").textContent, "2 missing");
  assert.match(body.querySelector(".cov-list-missing-functional").textContent, /Partial match, not confirmed — touches reset\.py, not confirmed/);
  await h.flush(() => h.$("#gap-pr-detail-close").click());
  assert.equal(h.$("#gap-pr-detail").style.display, "none");
});

test("screen: all partial reads 0 / 3 with no covered cases; automation tab", async (t) => {
  const h = await mount(t, {
    "/api/features/f1/code-coverage/runs?limit=50": { runs: [] },
    "/api/code-coverage/runs/r1": detailFor([entry("c1", "partial"), entry("c2", "partial"), entry("c3", "partial")]),
    "/api/features/f1/automation-coverage": {
      test_repos: [{ id: "t1", full_name: "acme/tests", scan_status: "done" }], total_generated: 2, coverage_pct: 50, covered_count: 1, missing_count: 1,
      items: [{ generated_type: "functional", status: "covered", generated_title: "A", match: { framework: "Jest", repo_full_name: "acme/tests", score: 0.9 } }, { generated_type: "functional", status: "missing", generated_title: "B" }],
    },
  });
  await h.flush(() => window.initGap());
  assert.match(h.$("#gap-pr-list").textContent, /No PR coverage runs yet/);
  await h.flush(() => window.openGapPrRun("r1"));
  const body = h.$("#gap-pr-detail-body");
  assert.match(body.textContent, /0 \/ 3Tests covered\+ 3 partial, not counted/);
  assert.equal(body.querySelector(".cov-list-covered-functional").dataset.count, "0");
  assert.match(body.textContent, /No covered test cases\./);
  await h.flush(() => h.$('[data-gap-tab="auto"]').click());
  assert.equal(h.$("#gap-tab-auto").style.display, "block");
  assert.equal(h.$("#gap-auto-pct").textContent, "50%");
  assert.equal(h.$("#gap-auto-summary").textContent, "1/2 covered · scanned ");
  const row = h.$(".auto-cov-card.covered .auto-cov-row");
  await h.flush(() => row.click());
  assert.equal(row.parentElement.className, "auto-cov-card covered open");
  assert.equal(h.$(".auto-cov-fw-badge").className, "auto-cov-fw-badge jest");
});
