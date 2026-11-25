import assert from "node:assert/strict";
import test from "node:test";

import {
  fmtTok,
  fmtUsd,
  keepValue,
  modelRows,
  modelText,
  projectOptions,
  recentRow,
  recentText,
  rowShown,
  statCards,
} from "../src/features/usage/lib/usage.js";

test("number formats and KPI cards", () => {
  assert.equal(fmtTok(null), "0");
  assert.equal(fmtUsd(null), "—");
  assert.equal(fmtUsd(0.4321), "$0.4321");
  assert.equal(fmtUsd(12.5), "$12.50");
  assert.deepEqual(statCards({}).map((c) => c.value), ["0", "0", "0", "—"]);
});

test("models, project options and kept filters", () => {
  assert.deepEqual(modelRows({ a: { total_tokens: 1 }, b: { total_tokens: 5 } }).map(([m]) => m), ["b", "a"]);
  assert.deepEqual(projectOptions([{ name: "Tour" }, { project_id: "p9" }, {}], ["Zeta", "", "Tour"]), ["Tour", "p9", "Unassigned", "Zeta"]);
  assert.equal(keepValue("p9", ["p9"]), "p9");
  assert.equal(keepValue("gone", ["p9"]), "");
});

test("row text and filters", () => {
  const r = recentRow({ type: "analysis", status: "failed", by_model: {} });
  assert.deepEqual([r.process, r.project, r.feature, r.statusClass, r.models, r.cost], ["analysis", "—", "—", "err", "—", "—"]);
  assert.equal(recentRow({ status: "running" }).statusClass, "warn");
  assert.equal(recentText(r), "analysis——failed—0—");
  assert.equal(modelText(["m", { estimated: true, kind: "llm", calls: 2 }]), "m ~estllm2000—");
  assert.equal(rowShown("Tour QA", " tour "), true);
  assert.equal(rowShown("Zeta", "tour"), false);
  assert.equal(rowShown("x", ""), true);
});
