import assert from "node:assert/strict";
import test from "node:test";

import { harness, makeFile, window } from "./features-harness.js";

test.after(() => window.close());

test("registers window hooks without fetching; cards, title and the hidden project picker", async (t) => {
  const h = harness(t);
  await h.mount();
  assert.equal(h.requests.length, 0);
  for (const k of ["loadFeatures", "showFeatureList", "showFeatureCreate", "syncFeatureProjects", "openFeature", "watchFeatureGen"])
    assert.equal(typeof window[k], "function", k);
  assert.equal(h.$("#features-page-title").textContent, "Features");
  await h.open();
  assert.deepEqual(h.requests.map((r) => r[1]), ["/api/features?project_id=pA"]);
  assert.equal(h.$("#features-page-title").textContent, "Tour QA");
  assert.equal(h.$("#features-project-context").textContent, "1 feature");
  assert.equal(h.$("#f-project").value, "pA");
  const cards = h.container.querySelectorAll("[data-feature-card]");
  assert.equal(cards[0].querySelector(".entity-name").innerHTML, "Login &lt;b&gt;x&lt;/b&gt;");
  assert.equal(cards[0].querySelector(".entity-meta").textContent, "Version 2 · 1 test case · WQ-1");
  assert.equal(cards[1].querySelector(".entity-meta").textContent, "Version 1 · 0 test cases");
  assert.equal(h.$("#feature-new-btn").style.display, "");
});

test("card click, menu, rename, import sheet and delete", async (t) => {
  const h = harness(t);
  await h.open();
  const card = (id) => h.$(`[data-feature-card="${id}"]`);
  await h.click(card("f2").querySelector(".entity-name"));
  assert.deepEqual(h.calls.open, ["f2"]);
  await h.click(card("f2").querySelector(".entity-menu-btn"));
  assert.equal(card("f2").classList.contains("menu-open"), true);
  await h.flush(() => document.dispatchEvent(new window.KeyboardEvent("keydown", { key: "Escape" })));
  assert.equal(card("f2").classList.contains("menu-open"), false);
  const menu = (id, i) => card(id).querySelectorAll(".entity-menu button")[i];
  await h.click(menu("f1", 1));
  assert.deepEqual(h.calls.sheet, [["f1", "pA"]]);
  assert.deepEqual(h.calls.open, ["f2"]);
  h.state.promptAnswer = "Login 2";
  await h.click(menu("f1", 0));
  assert.deepEqual(h.calls.prompt[0], ["Rename feature", "Feature name", "Login <b>x</b>"]);
  assert.ok(h.requests.some((r) => r[0] === "PATCH" && r[1] === "/api/features/f1" && r[2].name === "Login 2"));
  assert.deepEqual(h.calls.toast.at(-1), ["Feature renamed", "ok"]);
  await h.click(menu("f2", 2));
  const cc = h.calls.cc[0];
  assert.equal(cc.summary, '<b>Signup &lt;i&gt;</b><div class="muted" style="margin-top:6px">Version 3 · 2 test cases</div>');
  assert.deepEqual(h.calls.feature, ["f2"]);
  await h.flush(() => cc.onConfirm());
  assert.ok(h.requests.some((r) => r[0] === "DELETE" && r[1] === "/api/features/f2"));
  assert.deepEqual(h.calls.feature, ["f2", null, null]);
  assert.equal(h.calls.status, 1);
  assert.match(h.calls.toast.at(-1)[0], /^Feature deleted · 4 orphan test case\(s\) removed · 1 shared/);
});

test("empty list hides + New feature; error shows Retry", async (t) => {
  let fail = false;
  const h = harness(t, { "GET /api/features?project_id=pA": () => (fail ? [500, { detail: "List down" }] : [200, { features: [] }]) });
  await h.open();
  assert.match(h.$("#feat-list").textContent, /No features yet/);
  assert.equal(h.$("#feature-new-btn").style.display, "none");
  fail = true;
  await h.flush(() => window.loadFeatures());
  assert.match(h.$("#feat-list").textContent, /Couldn't load featuresList down/);
  assert.equal(h.$("#feature-new-btn").style.display, "none");
  fail = false;
  await h.click(h.$("#feat-list .ghost"));
  assert.match(h.$("#feat-list").textContent, /No features yet/);
  await h.click(h.$("#feat-list .go"));
  assert.equal(h.$("#feature-list-page").hidden, true);
  assert.equal(h.$("#feature-create-page").hidden, false);
});

test("page switch: create, workspace, back to the list, and back to projects", async (t) => {
  const h = harness(t);
  await h.open();
  await h.click(h.$("#feature-new-btn"));
  assert.equal(h.$("#feature-create-page").hidden, false);
  await h.flush(() => window.__openFeature("f2"));
  assert.deepEqual([h.$("#feature-list-page").hidden, h.$("#feature-create-page").hidden, h.$("#detail-card").hidden], [true, true, false]);
  assert.equal(h.$("#d-name").textContent, "Signup <i>");
  await h.flush(() => window.showFeatureList());
  assert.equal(h.$("#feature-list-page").hidden, false);
  assert.ok(h.calls.backbar >= 3);
  await h.click(h.$("#features-back-project"));
  assert.equal(h.calls.projects, 1);
});

test("create page: Jira epics, reset, and the test type mix", async (t) => {
  const h = harness(t);
  await h.open();
  await h.setValue(h.$("#f-name"), "dirty");
  await h.flush(() => window.showFeatureCreate());
  assert.equal(h.$("#f-name").value, "");
  assert.deepEqual([...h.$("#f-key").options].map((o) => o.textContent), ["No Jira epic", "WQ-7 — Epic"]);
  assert.equal(h.$("#f-key-status").textContent, "1 unassociated Epic(s) available from WQ");
  h.state.noJira = true;
  await h.flush(() => window.showFeatureCreate());
  assert.equal(h.$("#f-key-status").textContent, "No Jira project is linked to this project.");
  const vals = () => ["functional", "ui", "e2e", "api", "nfr"].map((x) => h.$(`#foc-${x}`).value).concat(h.$("#foc-total").textContent);
  const api = h.$("#foc-api");
  await h.flush(() => api.dispatchEvent(new window.Event("pointerdown", { bubbles: true })));
  await h.setValue(api, "50");
  assert.deepEqual(vals(), ["0", "10", "20", "50", "20", "100%"]);
  await h.setValue(api, "90");
  assert.deepEqual(vals(), ["0", "0", "0", "90", "10", "100%"]);
  assert.equal(h.$("#foc-api-v").textContent, "90%");
  assert.equal(api.style.getPropertyValue("--fill"), "90%");
});

test("generate: validation, request, sheet, progress and completion", async (t) => {
  const h = harness(t);
  await h.open();
  await h.flush(() => window.showFeatureCreate());
  await h.click(h.$("#f-go"));
  assert.equal(h.$("#f-status").innerHTML, '<span class="err">Enter a feature name to continue.</span>');
  await h.setValue(h.$("#f-name"), "  New ");
  await h.click(h.$("#f-go"));
  assert.match(h.$("#f-status").textContent, /Add at least one source/);
  await h.setValue(h.$("#f-text"), "req");
  await h.setValue(h.$("#f-confluence"), "https://c/1, https://c/2");
  await h.setValue(h.$("#f-key"), "WQ-7", "change");
  await h.setValue(h.$("#f-match-key"), " HOLDS ");
  await h.setFiles(h.$("#f-file"), [makeFile("a.pdf")]);
  Object.defineProperty(h.$("#f-sheet"), "files", { value: [makeFile("s.csv")], configurable: true });
  h.requests.length = 0;
  await h.click(h.$("#f-go"));
  const post = h.requests.find((r) => r[1] === "/api/features");
  assert.deepEqual(post[2], [
    ["name", "New"],
    ["project_id", "pA"],
    ["key", "WQ-7"],
    ["match_key", "HOLDS"],
    ["files", "FILE:a.pdf"],
    ["text", "req"],
    ["focus", '{"functional":20,"ui":20,"e2e":20,"api":20,"nfr":20}'],
    ["confluence_url", "https://c/1"],
    ["confluence_url", "https://c/2"],
  ]);
  assert.ok(h.requests.some((r) => r[1] === "/api/projects/pA/features/fN/tests/import"));
  assert.deepEqual(h.calls.toast.slice(-2), [["Generation started", "ok"], ["Sheet queued for import (s.csv)", "ok"]]);
  assert.equal(h.$("#f-status").innerHTML, '<span class="ok">✓ 2 document(s) accepted · 7 chunk(s) prepared.</span> Live progress below.');
  assert.equal(h.$("#f-go").disabled, true);
  assert.equal(h.calls.job.id, "jN");
  await h.flush(() => h.calls.job.cb({ status: "running", stage: "Embedding <x>", logs: [{ progress: 10, stage: "start" }], result: { cases_new: 2 } }));
  assert.equal(h.$("#f-status").innerHTML, '<span class="muted">Embedding &lt;x&gt;</span> — 2 new + 0 reused cases · 0 new + 0 reused steps');
  assert.equal(h.$("#f-log").textContent, " 10%  start");
  await h.flush(() =>
    h.calls.job.cb({
      status: "done",
      logs: [],
      result: { cases_new: 3, cases_reused: 1, testgen_filter: { rejected: 1, generated: 4, persisted: 3, rejected_by_reason: { dup: 1 } }, warnings: ["w"], errors: [] },
    }),
  );
  assert.equal(
    h.$("#f-status").innerHTML,
    '<span class="ok">✓ Done</span> — 3 new + 1 reused cases · 0 new + 0 reused steps<br><span class="muted">4 generated, 3 persisted (1 dup)</span><br><span class="warn">w</span>',
  );
  assert.equal(h.$("#f-log").style.display, "none");
  assert.equal(h.$("#f-go").disabled, false);
  assert.deepEqual(h.calls.open, ["fN"]);
  assert.deepEqual(h.calls.toast.at(-1), ["Generation complete — 3 new, 1 reused test cases.", "ok"]);
});

test("generate: a failed start keeps the page usable", async (t) => {
  const h = harness(t, { "POST /api/features": () => [400, { detail: "Bad doc" }] });
  await h.open();
  await h.flush(() => window.showFeatureCreate());
  await h.setValue(h.$("#f-name"), "X");
  await h.setValue(h.$("#f-text"), "y");
  await h.click(h.$("#f-go"));
  assert.equal(h.$("#f-status").innerHTML, '<span class="err">✕ Couldn\'t start generation: Bad doc</span>');
  assert.deepEqual(h.calls.toast.at(-1), ["Generation failed: Bad doc", "err"]);
  assert.equal(h.$("#f-go").disabled, false);
});
