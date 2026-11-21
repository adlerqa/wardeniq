import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";

// issue #291: the Gap Analysis PR-run screens counted a "partial" match (the PR touches
// relevant code but the implementation was not confirmed) as covered. This runs the real
// 13-gap-analysis.js controller (same sandbox style as feature-upload-file-remove.test.js)
// with a stubbed `api`, and asserts on the HTML it renders for the run card and the run
// detail view. A partial match must be shown, labelled, and kept out of the covered counts.

const controllers = (name) =>
  readFileSync(new URL(`../src/compat/runtime/controllers/${name}`, import.meta.url), "utf8");

// Use the app's real escaper rather than an approximation.
const coreSource = controllers("00-core.js");
const escSource = coreSource.slice(
  coreSource.indexOf("const esc = (s) =>"),
  coreSource.indexOf("const escAttr = esc;") + "const escAttr = esc;".length,
);
const source = controllers("13-gap-analysis.js");

function harness(api) {
  const nodes = new Map();
  const $ = (selector) => {
    if (!nodes.has(selector)) {
      nodes.set(selector, {
        style: {}, innerHTML: "", textContent: "", dataset: {}, onclick: null,
        addEventListener() {}, classList: { add() {}, remove() {}, toggle() {} },
      });
    }
    return nodes.get(selector);
  };
  const win = {};
  const context = vm.createContext({
    $, window: win, document: { querySelectorAll: () => [], getElementById: () => null },
    api, skIn: (sel, html) => { $(sel).innerHTML = html; },
    skeleton: { rows: () => "", block: () => "" },
    currentFeature: "f1", currentProject: "p1", toast() {}, uiPrompt: async () => null,
    prioBadge: () => "", stepsHtml: () => "",
    setTimeout: () => 0, clearTimeout() {}, setInterval: () => 0, clearInterval() {}, console,
  });
  vm.runInContext(escSource, context);
  vm.runInContext(source, context);
  return { $, context, win };
}

const run = (over = {}) => ({
  id: "r1", pr_number: 7, pr_title: "Fix reset", status: "done", tests_total: 3,
  tests_covered: 0, tests_partial: 0, source: "webhook", ...over,
});

async function renderCards(runs) {
  const h = harness(async () => ({ runs }));
  await h.context.loadGapPrRuns();
  return h.$("#gap-pr-list").innerHTML;
}

const cases = [
  { id: "c1", title: "Case one", type: "functional", priority: "P2", steps: [] },
  { id: "c2", title: "Case two", type: "functional", priority: "P2", steps: [] },
  { id: "c3", title: "Case three", type: "functional", priority: "P2", steps: [] },
];
const entry = (id, status, rationale = "r") => ({
  test_case_id: id, ...(status === undefined ? {} : { status }), rationale, by_dev_test: false,
});

async function renderDetail(covered, comparison = {}) {
  const detail = {
    id: "r1", feature_id: "f1", pr_number: 7, pr_title: "Fix reset", pr_branch: "feat/x",
    repo_full_name: "acme/app", head_sha: "abcdef0123", tests_total: 3, feature_cases: cases,
    result: { covered, comparison },
  };
  const h = harness(async () => detail);
  await h.win.openGapPrRun("r1");
  return h.$("#gap-pr-detail-body").innerHTML;
}

// ---------------------------------------------------------------- run card
test("a run with only partial matches reads 0/3 and says how many are partial", async () => {
  const html = await renderCards([run({ tests_covered: 0, tests_partial: 3 })]);
  assert.match(html, /<b>0\/3<\/b> covered/);
  assert.match(html, /0%/);
  assert.match(html, /3 partial, not counted/);
});

test("one confirmed and two partial reads 1/3 (33%)", async () => {
  const html = await renderCards([run({ tests_covered: 1, tests_partial: 2 })]);
  assert.match(html, /<b>1\/3<\/b> covered/);
  assert.match(html, /33%/);
  assert.match(html, /2 partial, not counted/);
});

test("a fully confirmed run shows no partial note", async () => {
  const html = await renderCards([run({ tests_covered: 3, tests_partial: 0 })]);
  assert.match(html, /<b>3\/3<\/b> covered/);
  assert.doesNotMatch(html, /partial/);
});

test("a run from an older server without tests_partial still renders", async () => {
  const html = await renderCards([run({ tests_covered: 2, tests_partial: undefined })]);
  assert.match(html, /<b>2\/3<\/b> covered/);
  assert.doesNotMatch(html, /partial/);
});

// ---------------------------------------------------------------- run detail
test("detail: partial matches are not counted in the covered header or lists", async () => {
  const html = await renderDetail([entry("c1", "partial"), entry("c2", "covered")]);
  assert.match(html, /1 \/ 3<\/div>/);                         // Tests covered: 1 of 3
  assert.match(html, /\+ 1 partial, not counted/);
  assert.match(html, /data-count="1" style="display:block">[\s\S]*Case two/);   // covered list
  assert.match(html, /cov-list-missing-functional" data-count="2"/);           // c1 and c3
});

test("detail: gaps equal total minus confirmed, so a partial case is still a gap", async () => {
  const html = await renderDetail([entry("c1", "partial"), entry("c2", "covered")]);
  assert.match(html, /font-weight:700;line-height:1">2<\/div><div class="muted"[^>]*>Gaps/);
});

test("detail: all partial reads 0 / 3 with no covered cases", async () => {
  const html = await renderDetail([entry("c1", "partial"), entry("c2", "partial"), entry("c3", "partial")]);
  assert.match(html, /0 \/ 3<\/div>/);
  assert.match(html, /\+ 3 partial, not counted/);
  assert.match(html, /cov-list-covered-functional" data-count="0"/);
  assert.match(html, /No covered test cases\./);
});

test("detail: a partial case is labelled with its rationale inside the missing list", async () => {
  const html = await renderDetail([entry("c1", "partial", "touches reset.py, not confirmed")]);
  assert.match(html, /Partial match, not confirmed — touches reset\.py, not confirmed/);
  assert.match(html, /\(1 partial\)/);                         // section summary
});

test("detail: a confirmed case gets no partial label", async () => {
  const html = await renderDetail([entry("c1", "covered")]);
  assert.doesNotMatch(html, /Partial match/);
  assert.doesNotMatch(html, /partial, not counted/);
});

test("detail: an entry saved before status existed counts as covered", async () => {
  const html = await renderDetail([entry("c1", undefined), entry("c2", undefined)]);
  assert.match(html, /2 \/ 3<\/div>/);
  assert.doesNotMatch(html, /Partial match/);
});

test("detail: the rationale is escaped, not injected as HTML", async () => {
  const html = await renderDetail([entry("c1", "partial", '<img src=x onerror="alert(1)">')]);
  assert.doesNotMatch(html, /<img src=x/);
  assert.match(html, /&lt;img src=x onerror=&quot;alert\(1\)&quot;&gt;/);
});

test("detail: the New tests found tile uses the server's comparison", async () => {
  const html = await renderDetail([entry("c1", "covered")], { newly_covered: ["c1"], no_longer_covered: [] });
  assert.match(html, /line-height:1">1<\/div><div class="muted"[^>]*>New tests found/);
});
