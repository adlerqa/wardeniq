import assert from "node:assert/strict";
import test from "node:test";

import { harness, window } from "./features-harness.js";

test.after(() => window.close());

const CASES = [
  { id: "w1", display_id: "W-1", title: "API works", type: "api", priority: "high", execution_status: "passed", steps: [{}, {}], association: { origin: "created" } },
  { id: "w2", title: "UI <b>", type: "ui", category: "ui", priority: "low", steps: [{}], association: { origin: "reused" } },
  { id: "w3", title: "Journey", type: "e2e", priority: "medium", steps: [], imported: true },
];
const FEATURE = {
  name: "Payments <b>", version: 3, key: "WQ-5", match_key: "PAY", test_cases: CASES,
  versions: [{ id: "fw0", version: 2, case_count: 2 }, { id: "fw1", version: 3, case_count: 3 }],
  version_diff: { mode: "version", version: 3, kept: 2, retired: [{ title: "Old", reason: "gone" }] },
  summary: "Pay invoices quickly.",
};
const COVERAGE = { summary: { code_pct: 62, automation_pct: 30, covered_cases: 2, partial_cases: 1, automated_cases: 1, total_cases: 3, ready: false, ready_threshold: 70 } };

function open(t, routes = {}) {
  const h = harness(t, {
    "GET /api/features/fw1": () => [200, FEATURE],
    "GET /api/features/fw1/coverage": () => [200, COVERAGE],
    "GET /api/jobs?status=running&limit=50": () => [200, { jobs: [] }],
    "POST /api/features/fw1/match-key": (o) => [200, { match_key: JSON.parse(o.body).match_key.toUpperCase() }],
    "POST /api/features/fw1/ready-threshold": (o) => [200, { ready_threshold: JSON.parse(o.body).threshold }],
    "POST /api/features/fw1/jira-sync": () => [200, { issue: "WQ-5" }],
    ...routes,
  });
  window.brandLoader = () => '<div class="loader"></div>';
  window.setCurrentFeature = (f) => h.calls.feature.push(f);
  let feature = null;
  window.getCurrentFeatureId = () => feature;
  const orig = window.setCurrentFeature;
  window.setCurrentFeature = (f) => {
    feature = f;
    orig(f);
  };
  return h;
}

test("opens a feature: header, overview, version info, coverage and case groups", async (t) => {
  const h = open(t);
  await h.open();
  await h.flush(() => window.__openFeature("fw1"));
  assert.equal(h.$("#detail-card").hidden, false);
  assert.equal(h.$("#d-name").textContent, "Payments <b>");
  assert.equal(h.$("#d-version-chip").textContent, "Version 3 · 3 cases");
  assert.equal(h.$("#d-version").value, "fw1");
  assert.equal(h.$("#d-jira").style.display, "");
  assert.equal(h.$("#d-match-key-input").value, "PAY");
  assert.match(h.$("#d-overview").textContent, /^Version 3 · WQ-5 · 3 test casesPay invoices quickly\.1API1UI validations0Business/);
  assert.match(h.$("#d-verinfo").textContent, /Version 3 diff: 2 cases carried over, 1 retired, new cases added by generation\./);
  assert.match(h.$("#d-coverage").textContent, /Code coverage \(cases implemented by PRs\)62%.*2 covered · 1 partial \(not counted\) · 1 automated of 3 cases.*below the 70% target/);
  assert.equal(h.$("#fc-threshold").value, "70");
  const groups = [...h.container.querySelectorAll("#d-cases details.case-group summary")].map((s) => s.textContent);
  assert.deepEqual(groups, ["API (1)", "UI validations (1)", "Business / functional (0)", "End-to-end (1)", "Edge & reliability (0)", "Integration (0)"]);
  const sub = (id) => h.$(`#d-cases [data-case-item="${id}"] .testcase-sub`).textContent;
  assert.deepEqual([sub("w1"), sub("w2"), sub("w3")], ["created · API · 2 steps", "reused · UI validation · 1 step", "End-to-end · 0 steps"]);
  assert.equal(h.$('#d-cases [data-case-item="w3"] .badge.reused').textContent, "Imported from sheet");
  assert.ok(h.calls.backbar > 0);
});

test("selection spans every group; match tag, threshold and Jira", async (t) => {
  const h = open(t);
  await h.open();
  await h.flush(() => window.__openFeature("fw1"));
  await h.click(h.container.querySelectorAll("#d-cases .case-select-all")[0]);
  assert.deepEqual([...h.container.querySelectorAll("#d-cases .case-select[data-case-id]")].map((x) => x.checked), [true, true, true]);
  assert.equal(h.$("#detail-card .case-bulk-toolbar").className, "case-bulk-toolbar show");
  assert.equal(h.$('[data-bulk-count="feature"]').textContent, "3 selected");
  await h.setValue(h.$("#d-match-key-input"), " hold ");
  await h.click(h.$("#d-match-key button"));
  assert.equal(h.$("#d-match-key-status").textContent, "saved · PRs tagged [HOLD] map here");
  await h.setValue(h.$("#fc-threshold"), "75");
  await h.click(h.$("#d-coverage button"));
  assert.ok(h.requests.some((r) => r[1] === "/api/features/fw1/ready-threshold" && r[2].threshold === 75));
  assert.deepEqual(h.calls.toast.at(-1), ["QA-readiness target set to 75% code coverage", "ok"]);
  await h.click(h.$("#d-jira"));
  assert.deepEqual(h.calls.toast.at(-1), ["Posted coverage to Jira WQ-5", "ok"]);
});

test("generation banner: attach to a running job, caption, done reloads", async (t) => {
  const h = open(t, { "GET /api/jobs?status=running&limit=50": () => [200, { jobs: [{ id: "jr", feature_id: "fw1", type: "generate" }] }] });
  await h.open();
  await h.flush(() => window.__openFeature("fw1"));
  assert.equal(h.calls.job.id, "jr");
  assert.match(h.$("#d-genbanner").innerHTML, /class="loader"/);
  assert.equal(h.$("#d-gencap").textContent, "this can take a minute; results will refresh automatically.");
  await h.flush(() => h.calls.job.cb({ status: "running", stage: "Drafting <x>", result: { cases_new: 2, cases_reused: 1 } }));
  assert.equal(h.$("#d-gencap").textContent, "Drafting <x> · 2 new · 1 reused so far");
  await h.flush(() => h.calls.job.cb({ status: "failed", error: "boom" }));
  assert.equal(h.$("#d-genbanner").innerHTML, '<div class="gen-banner err"><span>Generation failed: boom</span></div>');
});

test("a failed load shows the error in the case area", async (t) => {
  const h = open(t, { "GET /api/features/fw9": () => [404, { detail: "Gone" }] });
  await h.open();
  await h.flush(() => window.__openFeature("fw9"));
  assert.equal(h.$("#d-cases").innerHTML, '<div class="err">Gone</div>');
});
