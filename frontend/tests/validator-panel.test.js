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

const entry = fileURLToPath(
  new URL("../src/features/validator/pages/ValidatorPage.jsx", import.meta.url),
);
const bundled = await build({
  entryPoints: [entry],
  bundle: true,
  write: false,
  format: "cjs",
  platform: "neutral",
  jsx: "automatic",
  external: ["react", "react/jsx-runtime", "react-dom"],
  logLevel: "silent",
});
const code = bundled.outputFiles[0].text;
const require = createRequire(import.meta.url);

const QUESTIONS = [
  { id: "q1", category: "business_rules", question: "Which rule wins?", options: ["A", "B"] },
  { id: "q2", category: "edge_cases", question: "What happens?", options: ["C", "D"] },
];
const SCORE = {
  clarityScore: 50,
  rating: "Fair",
  weakAreas: ["edge_cases"],
  questionResults: [
    { category: "business_rules", question: "Which rule wins?", isCorrect: true, selectedOption: "B", comment: "note" },
    { category: "edge_cases", question: "What happens?", isCorrect: false, selectedOption: "C", correctOption: "D" },
  ],
};

function harness(t, routes, { feature = "f1", confirm = true } = {}) {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const name = document.createElement("h2");
  name.id = "d-name";
  name.textContent = "Login";
  document.body.appendChild(name);
  for (const k of ["toast", "uiConfirm", "getCurrentFeatureId", "watchJob", "usageLogLines", "initValidator"])
    delete window[k];
  const ui = [];
  const jobs = [];
  window.getCurrentFeatureId = () => feature;
  window.toast = (...a) => ui.push(["toast", ...a]);
  window.uiConfirm = async (...a) => {
    ui.push(["confirm", ...a]);
    return confirm;
  };
  window.usageLogLines = () => [];
  window.watchJob = (jobId, onTick) => {
    const job = { jobId, onTick, stopped: false };
    jobs.push(job);
    return () => {
      job.stopped = true;
    };
  };
  const requests = [];
  async function fakeFetch(path, init = {}) {
    const method = init.method || "GET";
    requests.push({ method, path, body: init.body ? JSON.parse(init.body) : undefined });
    const handler = routes[`${method} ${path}`];
    const [status, body] = handler ? handler() : [404, {}];
    return { status, ok: status < 300, text: async () => JSON.stringify(body) };
  }
  const module = { exports: {} };
  vm.runInNewContext(code, {
    module, exports: module.exports, require, window, document, console,
    fetch: fakeFetch, setTimeout, clearTimeout,
  });
  const root = createRoot(container);
  t.after(async () => {
    await act(async () => root.unmount());
    container.remove();
    name.remove();
  });
  const buttons = () => [...container.querySelectorAll("button")];
  return {
    container, requests, ui, jobs, root,
    async mount() {
      await act(async () => root.render(React.createElement(module.exports.default)));
    },
    async open() {
      await act(async () => window.initValidator());
    },
    async tick(job, j) {
      await act(async () => job.onTick(j));
    },
    text: () => container.textContent,
    button: (label) => buttons().find((b) => b.textContent.trim() === label),
    async click(el) {
      await act(async () => el.dispatchEvent(new window.MouseEvent("click", { bubbles: true })));
    },
  };
}

test("registers window.initValidator without fetching; removes it on unmount", async (t) => {
  const h = harness(t, {});
  await h.mount();
  assert.equal(typeof window.initValidator, "function");
  assert.deepEqual(h.requests, []);
  assert.match(h.text(), /Please select a feature first to run the requirements validator\./);
  await act(async () => h.root.unmount());
  assert.equal(window.initValidator, undefined);
});

test("no validator yet: message and Generate; generate follows the job to questions", async (t) => {
  let latest = { mode: "none" };
  const h = harness(t, {
    "GET /api/features/f1/validator/latest": () => [200, latest],
    "POST /api/features/f1/validator": () => [200, { mode: "generating", job_id: "j1", run: { id: "r1" } }],
  });
  await h.mount();
  await h.open();
  assert.match(h.text(), /Login — MCQ Validator/);
  assert.match(h.text(), /No validator generated yet\./);
  assert.equal(h.button("Generate Validator").hidden, false);
  assert.equal(h.button("↻ Retake Validator").hidden, true);

  await h.click(h.button("Generate Validator"));
  assert.deepEqual(h.requests.at(-1).body, { forceNew: false });
  assert.equal(h.jobs[0].jobId, "j1");
  assert.match(h.text(), /Generating validator questions…/);
  assert.ok(h.container.querySelector('[role="status"][aria-label="Generating validator questions"]'));

  await h.tick(h.jobs[0], { status: "running", progress: 40, stage: "Generating questions", logs: [{ progress: 40, stage: "Generating questions" }] });
  assert.match(h.container.querySelector(".job-log").textContent, / 40%  Generating questions/);

  latest = { mode: "questions", run: { id: "r1" }, questions: QUESTIONS, answers: [] };
  await h.tick(h.jobs[0], { status: "succeeded", progress: 100 });
  assert.match(h.text(), /BUSINESS RULES|business rules/i);
  assert.match(h.text(), /1\. Which rule wins\?/);
  assert.equal(h.button("↻ Retake Validator").hidden, false);
});

test("answer, validation toast, submit shows results", async (t) => {
  const h = harness(t, {
    "GET /api/features/f1/validator/latest": () => [200, {
      mode: "questions", run: { id: "r9" }, questions: QUESTIONS,
      answers: [{ question_id: "q1", selected_index: 1, confidence: 4, comment: "" }],
    }],
    "POST /api/validator/runs/r9/submit": () => [200, SCORE],
  });
  await h.mount();
  await h.open();
  assert.equal(h.button("B").getAttribute("aria-pressed"), "true");
  assert.equal(h.button("4").getAttribute("aria-pressed"), "true");

  await h.click(h.button("Submit Answers"));
  assert.deepEqual(h.ui.at(-1), ["toast", "Please answer all questions before submitting.", true]);
  assert.equal(h.requests.filter((r) => r.method === "POST").length, 0);

  await h.click(h.button("C"));
  const input = h.container.querySelectorAll("input")[1];
  const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
  await act(async () => {
    setter.call(input, "why");
    input.dispatchEvent(new window.Event("input", { bubbles: true }));
  });
  await h.click(h.button("Submit Answers"));
  assert.deepEqual(h.requests.at(-1).body, {
    answers: [
      { questionId: "q1", selectedIndex: 1, confidence: 4, comment: "" },
      { questionId: "q2", selectedIndex: 0, confidence: 3, comment: "why" },
    ],
  });
  assert.deepEqual(h.ui.at(-1), ["toast", "Answers submitted!", undefined]);
  assert.match(h.text(), /50%/);
  assert.match(h.text(), /Fair/);
  assert.match(h.text(), /edge cases/);
  assert.match(h.text(), /These categories scored below 60% accuracy/);
  assert.match(h.text(), /Your Answer: C/);
  assert.match(h.text(), /Correct Answer: D/);
  assert.match(h.text(), /Note: note/);
  assert.equal(h.button("Submit Answers"), undefined);
});

test("score mode shows results; retake asks and starts a fresh run", async (t) => {
  const h = harness(t, {
    "GET /api/features/f1/validator/latest": () => [200, { mode: "score", run: { id: "r2" }, score: { ...SCORE, weakAreas: [] } }],
    "POST /api/features/f1/validator": () => [200, { mode: "generating", job_id: "j2", run: { id: "r3" } }],
  });
  await h.mount();
  await h.open();
  assert.match(h.text(), /None/);
  assert.match(h.text(), /Strong requirement clarity across all categories\./);
  await h.click(h.button("↻ Retake Validator"));
  // Label and danger flag are left undefined, so uiConfirm's defaults apply as before.
  assert.deepEqual(h.ui[0].slice(0, 3), [
    "confirm",
    "Are you sure you want to retake the validator? This will generate completely fresh questions.",
    "Retake Validator",
  ]);
  assert.deepEqual(h.requests.at(-1).body, { forceNew: true });
  assert.equal(h.jobs[0].jobId, "j2");
});

test("failed job and load error", async (t) => {
  const h = harness(t, {
    "GET /api/features/f1/validator/latest": () => [200, { mode: "generating", run: { id: "r4", job_id: "j4" } }],
  });
  await h.mount();
  await h.open();
  await h.tick(h.jobs[0], { status: "failed", error: "LLM down" });
  assert.match(h.text(), /LLM down/);
  assert.equal(h.button("Generate Validator").hidden, false);

  const h2 = harness(t, {
    "GET /api/features/f1/validator/latest": () => [500, { detail: "db down" }],
  });
  await h2.mount();
  await h2.open();
  assert.match(h2.text(), /db down/);
});

test("re-opening stops following the previous job", async (t) => {
  const h = harness(t, {
    "GET /api/features/f1/validator/latest": () => [200, { mode: "generating", run: { id: "r5", job_id: "j5" } }],
  });
  await h.mount();
  await h.open();
  await h.open();
  assert.equal(h.jobs[0].stopped, true);
  assert.equal(h.jobs[1].stopped, false);
});
