import assert from "node:assert/strict";
import test from "node:test";

import {
  breakdownReason,
  importKpis,
  initialReview,
  libraryChanges,
  libraryGroups,
  libraryKpis,
  priorityTone,
  reviewPayload,
  sortLibrary,
  sourceRow,
  stepsText,
} from "../src/features/imports/lib/imports.js";

test("row text helpers", () => {
  assert.equal(stepsText({ steps_preview: ["Open", "Submit"] }), "Open · Submit");
  assert.equal(stepsText({ steps_count: 3 }), "3 steps");
  assert.equal(stepsText({}), "0 steps");
  assert.equal(sourceRow({ row_number: 7, row_index: 1 }), "7");
  assert.equal(sourceRow({ row_index: 1 }), "2");
  assert.equal(sourceRow({}), "");
  assert.equal(priorityTone("HIGH"), "red");
  assert.equal(priorityTone("Medium"), "amber");
  assert.equal(
    breakdownReason({ feature_anchor: 1, route_family: 1, intent_similarity: 0.1449, title_similarity: 0.5 }),
    "feature anchor matches; route family matches feature context; intent similarity 0.14; title similarity 0.50",
  );
  assert.equal(breakdownReason({ intent_similarity: "high" }), "intent similarity high");
  assert.equal(breakdownReason(null), "");
});

test("review seed, payload and import KPIs", () => {
  const items = [
    { action: "matched", project_imported_row_id: "r1", identity_hash: "h1" },
    { action: "stored", identity_hash: "h2", already_uploaded: true },
  ];
  const review = initialReview(items);
  assert.deepEqual(review, [
    { rid: "r1", hash: "h1", included: true, note: "" },
    { rid: null, hash: "h2", included: false, note: "" },
  ]);
  review[1].note = "later";
  assert.deepEqual(reviewPayload(review), {
    reviews: [
      { project_imported_row_id: "r1", identity_hash: "h1", action: "include", note: "" },
      { project_imported_row_id: null, identity_hash: "h2", action: "exclude", note: "later" },
    ],
  });
  assert.deepEqual(importKpis(items, { rejected_count: 3 }), [
    ["Included", 1, "green", "OK"],
    ["Stored for later", 1, "amber", "BOX"],
    ["Rejected", 3, "red", "!"],
    ["Duplicate merges", 1, "purple", "NET"],
  ]);
});

test("library sort, groups, changes and KPIs", () => {
  const items = sortLibrary([
    { identity_hash: "c", original_filename: "b.csv", sheet: "S", score: 0.1, is_in_feature: true },
    { identity_hash: "a", original_filename: "a.csv", sheet: "S", score: 0.2, feature_import_id: "i1" },
    { identity_hash: "b", original_filename: "a.csv", sheet: "S", score: 0.9, feature_import_id: "i1", is_in_feature: true },
  ]);
  assert.deepEqual(items.map((i) => i.identity_hash), ["b", "a", "c"]);
  const groups = libraryGroups(items);
  assert.deepEqual(groups.map((g) => [g.key, g.rows.length]), [["i1::a.csv::S", 2], ["::b.csv::S", 1]]);
  const desired = { a: true, b: true, c: false };
  assert.deepEqual(libraryChanges(items, desired), { add: ["a"], remove: ["c"] });
  assert.deepEqual(libraryKpis(items, desired, groups.length), [
    ["Sheets", 2, "green", "DOC"],
    ["Rows", 3, "purple", "GRID"],
    ["Included", 2, "green", "OK"],
    ["Stored for later", 1, "amber", "BOX"],
  ]);
});
