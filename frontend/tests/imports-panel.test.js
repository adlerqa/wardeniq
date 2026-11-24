import assert from "node:assert/strict";
import { createRequire } from "node:module";
import test from "node:test";
import { fileURLToPath } from "node:url";
import vm from "node:vm";
import { build } from "esbuild";
import { JSDOM } from "jsdom";
import React, { act } from "react";

// Create the DOM globals before react-dom loads (see api-tokens-panel.test.js).
const dom = new JSDOM("<!doctype html><body></body>", { url: "http://localhost/" });
const { window } = dom;
const { document } = window;
Object.assign(globalThis, { window, document, IS_REACT_ACT_ENVIRONMENT: true });
const { createRoot } = await import("react-dom/client");
test.after(() => window.close());

async function bundle(file) {
  const entry = fileURLToPath(new URL(`../src/features/imports/components/${file}`, import.meta.url));
  const out = await build({
    entryPoints: [entry],
    bundle: true,
    write: false,
    format: "cjs",
    platform: "neutral",
    jsx: "automatic",
    external: ["react", "react/jsx-runtime", "react-dom"],
    loader: { ".css": "empty" },
    logLevel: "silent",
  });
  return out.outputFiles[0].text;
}
const SHEET = await bundle("ImportSheetModal.jsx");
const LIBRARY = await bundle("ImportLibraryModal.jsx");
const require = createRequire(import.meta.url);
const settle = () => new Promise((r) => setTimeout(r, 0));

const IMPORT_ITEMS = [
  {
    title: "Request reset link",
    action: "matched",
    row_number: 2,
    category: "api_tests",
    priority: "High",
    method: "POST",
    endpoint: "/api/reset",
    steps_preview: ["Open", "Submit"],
    expected_result: "202",
    breakdown: { intent_similarity: 0.14 },
    project_imported_row_id: "r1",
    identity_hash: "h1",
  },
  { title: "Weekly chart", action: "stored", row_index: 4, steps_count: 1, identity_hash: "h2", already_uploaded: true },
];
const LIB_ITEMS = [
  { identity_hash: "h1", title: "Request reset link", original_filename: "s.csv", sheet: "Sheet1", feature_import_id: "i1", score: 0.9, is_in_feature: true, source_row_number: 2, priority: "High", method: "POST", endpoint: "/api/reset" },
  { identity_hash: "h2", title: "Weekly chart", original_filename: "s.csv", sheet: "Sheet1", feature_import_id: "i1", score: 0.2, is_in_feature: false, source_row_number: 6 },
  { identity_hash: "h3", title: "Other", original_filename: "t.csv", sheet: "", feature_import_id: "i2", score: 0.5, is_in_feature: false },
];

function harness(t, code, routes) {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const name = document.createElement("div");
  name.id = "d-name";
  name.textContent = "Password reset";
  document.body.appendChild(name);
  const calls = { toast: [], openFeature: [], loadFeatures: 0, confirm: [] };
  Object.assign(window, {
    toast: (m, e) => calls.toast.push([m, !!e]),
    getCurrentFeatureId: () => "f1",
    getCurrentProject: () => "p1",
    openFeature: (f) => calls.openFeature.push(f),
    loadFeatures: () => calls.loadFeatures++,
    openCaseConfirmation: (o) => calls.confirm.push(o),
  });
  const requests = [];
  async function fakeFetch(path, opts = {}) {
    requests.push([opts.method || "GET", path, opts.body]);
    const key = Object.keys(routes).find((k) => path.startsWith(k.split(" ")[1]) && (opts.method || "GET") === k.split(" ")[0]);
    const [status, body] = routes[key](path, opts);
    return { status, ok: status < 300, text: async () => JSON.stringify(body), json: async () => body };
  }
  const timers = [];
  const fakeTimeout = (fn, ms) => {
    timers.push([fn, ms]);
    return timers.length;
  };
  const module = { exports: {} };
  vm.runInNewContext(code, {
    module, exports: module.exports, require, window, document, console,
    fetch: fakeFetch, setTimeout: fakeTimeout, FormData: window.FormData, Date,
  });
  const root = createRoot(container);
  t.after(async () => {
    await act(async () => root.unmount());
    container.remove();
    name.remove();
  });
  const $ = (sel) => container.querySelector(sel);
  return {
    container, requests, calls, timers, root, $,
    async mount() {
      await act(async () => root.render(React.createElement(module.exports.default)));
    },
    async run(fn) {
      await act(async () => {
        await fn();
        await settle();
      });
    },
    async click(el) {
      await act(async () => {
        el.dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
        await settle();
      });
    },
    async runTimers() {
      while (timers.length) {
        const [fn] = timers.shift();
        await act(async () => {
          await fn();
          await settle();
        });
      }
    },
  };
}

async function chooseFile(h, name = "sample.csv") {
  const input = h.$("#imp-file");
  const file = new window.File(["Title\nA\n"], name, { type: "text/csv" });
  Object.defineProperty(input, "files", { value: [file], configurable: true });
  await act(async () => {
    input.dispatchEvent(new window.Event("change", { bubbles: true }));
  });
}

test("import dialog: opens via window hooks, file pick and clear", async (t) => {
  const h = harness(t, SHEET, {});
  await h.mount();
  assert.ok(!h.$("#imp-modal").classList.contains("show"));
  assert.equal(h.$("#imp-subtitle").textContent, "Upload a spreadsheet and link tests to this feature.");
  await h.run(() => window.importSheetForFeature("f1", "p1"));
  assert.ok(h.$("#imp-modal").classList.contains("show"));
  assert.equal(h.$("#imp-subtitle").innerHTML, "Updating: <b>Password reset</b>");
  assert.equal(h.$("#imp-progress").hidden, true);
  await h.click(h.$("#imp-upload"));
  assert.deepEqual(h.calls.toast, [["Pick a file first", true]]);
  await chooseFile(h);
  assert.equal(h.$("#imp-selected").textContent, "Selected: sample.csv");
  await h.click(h.$("#imp-file-clear"));
  assert.equal(h.$("#imp-selected").textContent, "Selected: none");
  await h.click(h.$("#imp-cancel"));
  assert.ok(!h.$("#imp-modal").classList.contains("show"));
  await act(async () => h.root.unmount());
  assert.equal(window.importSheetForFeature, undefined);
  assert.equal(window.openImportSheetModal, undefined);
});

test("import dialog: upload, poll, review and save", async (t) => {
  let polls = 0;
  const h = harness(t, SHEET, {
    "POST /api/projects/p1/features/f1/tests/import": () => [200, { feature_import_id: "i1" }],
    "GET /api/features/f1/tests/import/i1/status": () =>
      ++polls === 1
        ? [200, { data: { details: "Parsing sheet…" } }]
        : [200, { data: { completed: true, result_json: { items: IMPORT_ITEMS, rejected_count: 1 } } }],
    "POST /api/features/f1/tests/import/i1/review": () => [200, { data: { included: 2, excluded: 0 } }],
  });
  await h.mount();
  await h.run(() => window.openImportSheetModal("f1", "p1"));
  await chooseFile(h, "wq.csv");
  await h.click(h.$("#imp-upload"));
  assert.equal(h.$("#imp-status").textContent, "Parsing sheet…");
  assert.equal(h.$("#imp-progress").hidden, false);
  assert.ok(h.$("#imp-upload").disabled);
  await h.runTimers();
  assert.equal(h.$("#imp-heading").textContent, "Spreadsheet import finished");
  assert.equal(h.$("#imp-subtitle").innerHTML, "Imported into <b>Password reset</b>");
  assert.equal(h.$("#imp-cancel").textContent, "Close");
  assert.equal(h.$("#imp-upload").style.display, "none");
  assert.equal(h.$("#imp-progress").hidden, true);
  const kpis = [...h.container.querySelectorAll(".sheet-kpi")].map((k) => k.textContent);
  assert.deepEqual(kpis, ["Included1OK", "Stored for later1BOX", "Rejected1!", "Duplicate merges1NET"]);
  assert.equal(h.container.querySelector(".sheet-chip-row").textContent, "wq.csvFirst import for this feature");
  const cards = h.container.querySelectorAll("#imp-review-list .sheet-test-card");
  assert.equal(cards[0].className, "sheet-test-card included");
  assert.equal(
    cards[0].querySelector(".sheet-card-meta").textContent,
    "Source row 2api_testsHighPOST /api/reset",
  );
  assert.equal(cards[0].querySelector(".sheet-detail-box").textContent, "Steps: Open · SubmitExpected: 202");
  assert.equal(cards[0].querySelector(".sheet-reason").textContent, "Reason: intent similarity 0.14");
  assert.equal(cards[1].className, "sheet-test-card pending");
  assert.equal(cards[1].querySelector(".sheet-card-meta").textContent, "Source row 5No endpoint");
  assert.equal(h.calls.loadFeatures, 1);
  await h.runTimers();
  assert.deepEqual(h.calls.openFeature, ["f1"]);

  await h.click(cards[1].querySelectorAll(".imp-review-controls button")[0]);
  assert.equal(cards[1].className, "sheet-test-card included");
  assert.equal(cards[1].querySelector(".sheet-card-top .sheet-pill").textContent, "Included");
  assert.deepEqual(
    [...cards[1].querySelectorAll(".imp-review-controls button")].map((b) => b.className),
    ["go", "ghost"],
  );
  const note = cards[0].querySelector(".imp-review-controls input");
  const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
  await act(async () => {
    setter.call(note, "check copy");
    note.dispatchEvent(new window.Event("input", { bubbles: true }));
  });
  await h.click([...h.container.querySelectorAll("button")].find((b) => b.textContent === "Save review"));
  const [, , body] = h.requests.at(-1);
  assert.deepEqual(JSON.parse(body).reviews.map((r) => [r.identity_hash, r.action, r.note]), [
    ["h1", "include", "check copy"],
    ["h2", "include", ""],
  ]);
  assert.deepEqual(h.calls.toast.at(-1), ["Review saved · 2 included, 0 removed", false]);

  await chooseFile(h, "next.csv");
  assert.equal(h.$("#imp-summary").textContent, "");
  assert.equal(h.$("#imp-cancel").textContent, "Cancel");
  assert.equal(h.$("#imp-upload").style.display, "");
});

test("import dialog: upload error and empty sheet", async (t) => {
  let mode = "fail";
  const h = harness(t, SHEET, {
    "POST /api/projects/p1/features/f1/tests/import": () =>
      mode === "fail" ? [400, { detail: "Unsupported file" }] : [200, { feature_import_id: "i2", alreadyUploaded: true }],
    "GET /api/features/f1/tests/import/i2/status": () => [
      200,
      { data: { completed: true, result_json: { items: [], alreadyUploaded: true } } },
    ],
  });
  await h.mount();
  await h.run(() => window.openImportSheetModal());
  await chooseFile(h);
  await h.click(h.$("#imp-upload"));
  assert.equal(h.$("#imp-status").innerHTML, '<span class="err">Unsupported file</span>');
  assert.equal(h.$("#imp-upload").disabled, false);
  assert.deepEqual(h.calls.toast.at(-1), ["Unsupported file", true]);
  mode = "ok";
  await h.click(h.$("#imp-upload"));
  await h.runTimers();
  assert.deepEqual(h.calls.toast.at(-1), ["Already uploaded · reusing saved import", false]);
  assert.equal(h.$("#imp-status").innerHTML, '<span class="ok">✓ Already uploaded · no parsing was repeated</span>');
  assert.equal(h.$("#imp-summary").textContent, "");
  assert.equal(h.$("#imp-cancel").textContent, "Close");
  assert.equal(h.calls.loadFeatures, 0);
});

test("library dialog: groups, toggles, save", async (t) => {
  let items = LIB_ITEMS;
  const h = harness(t, LIBRARY, {
    "GET /api/features/f1/imported-sheets": () => [200, { data: { imported_sheet_tests: items } }],
    "POST /api/features/f1/imported-sheets/add": () => [200, {}],
    "POST /api/features/f1/imported-sheets/remove": () => [200, {}],
  });
  await h.mount();
  assert.equal(h.requests.length, 0);
  await h.run(() => window.openImportLibraryModal("f1"));
  assert.ok(h.$("#implib-modal").classList.contains("show"));
  assert.equal(h.$("#implib-loaded-count").textContent, "3 rows loaded");
  assert.deepEqual(
    [...h.container.querySelectorAll("#implib-stats .sheet-kpi .v")].map((v) => v.textContent),
    ["2", "3", "1", "2"],
  );
  const groups = h.container.querySelectorAll("details.sheet-group");
  assert.deepEqual([...groups].map((g) => g.open), [true, false]);
  assert.equal(groups[0].querySelector(".sheet-group-title").textContent, "s.csv Sheet1");
  assert.equal(groups[0].querySelector(".sheet-group-sub").textContent, "2 rows total · 1 included");
  const row = groups[0].querySelectorAll(".sheet-test-card")[0];
  assert.equal(row.querySelector(".sheet-card-meta").textContent, "HighPOST /api/resetScore 0.90");
  assert.equal(row.querySelector(".sheet-card-top .sheet-pill").textContent, "Included");
  assert.ok(h.$("#implib-save").disabled);

  await h.click(groups[1].querySelector("[data-implib-action='toggle-add']"));
  assert.ok(groups[1].open === false, "toggling a row does not collapse or open groups");
  assert.ok(!h.$("#implib-save").disabled);
  await h.click(groups[0].querySelector("[data-implib-action='remove-all']"));
  assert.equal(groups[0].querySelector(".sheet-group-sub").textContent, "2 rows total · 0 included");
  assert.deepEqual(
    [...h.container.querySelectorAll("#implib-stats .sheet-kpi .v")].map((v) => v.textContent),
    ["2", "3", "1", "2"],
  );

  items = LIB_ITEMS.map((it) => ({ ...it, is_in_feature: it.identity_hash === "h3" }));
  await h.click(h.$("#implib-save"));
  const posts = h.requests.filter(([m]) => m === "POST").map(([, p, b]) => [p, JSON.parse(b)]);
  assert.deepEqual(posts, [
    ["/api/features/f1/imported-sheets/add", { identity_hashes: ["h3"] }],
    ["/api/features/f1/imported-sheets/remove", { identity_hashes: ["h1"] }],
  ]);
  assert.deepEqual(h.calls.toast.at(-1), ["Imported sheet changes saved", false]);
  assert.deepEqual(h.calls.openFeature, ["f1"]);
  assert.ok(h.$("#implib-save").disabled);
  assert.equal(h.$("#implib-save").textContent, "Save changes");
});

test("library dialog: delete sheet confirmation, empty and error states", async (t) => {
  let mode = "rows";
  const h = harness(t, LIBRARY, {
    "GET /api/features/f1/imported-sheets": () =>
      mode === "fail"
        ? [500, { detail: "db down" }]
        : [200, { data: { imported_sheet_tests: mode === "rows" ? LIB_ITEMS : [] } }],
    "POST /api/features/f1/imported-sheets/remove": () => [200, {}],
  });
  await h.mount();
  await h.run(() => window.reuseImportsForFeature());
  await h.click(h.container.querySelector("[data-implib-action='delete-sheet']"));
  const opts = h.calls.confirm[0];
  assert.equal(opts.title, "Delete imported sheet");
  assert.equal(opts.copy, "Permanently delete s.csv · Sheet1?");
  assert.match(opts.summary, /across every feature in this project/);
  assert.equal(opts.confirmLabel, "Delete sheet");
  assert.equal(opts.danger, true);
  mode = "empty";
  await h.run(() => opts.onConfirm());
  const [, , body] = h.requests.find(([m]) => m === "POST");
  assert.deepEqual(JSON.parse(body), {
    delete_from_system: true,
    feature_import_id: "i1",
    original_filename: "s.csv",
    sheet_name: "Sheet1",
  });
  assert.deepEqual(h.calls.toast.at(-1), ["Deleted imported sheet permanently", false]);
  assert.equal(
    h.$("#implib-list").textContent,
    "No imported tests in this project yet. Upload a sheet from Import Sheet first.",
  );
  assert.equal(h.$("#implib-loaded-count").textContent, "0 rows loaded");
  mode = "fail";
  await h.click(h.$("#implib-cancel"));
  await h.run(() => window.openImportLibraryModal("f1"));
  assert.equal(h.$("#implib-list").innerHTML, '<div class="err">db down</div>');
  assert.equal(h.$("#implib-stats").textContent, "");
  assert.ok(h.$("#implib-save").disabled);
});
