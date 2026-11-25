import assert from "node:assert/strict";
import test from "node:test";

import {
  barPercents,
  branchMap,
  completeText,
  coverageTotals,
  emptyReasonLine,
  filterPickerRepos,
  formatMindmapStage,
  hasEmptyReason,
  progressBits,
  repoAnalysisDefaultChecked,
  repoKindClass,
  repoKindLabel,
  statusRank,
  withoutConnected,
} from "../src/features/mind-map/lib/mindmap.js";

test("analysis stage text and progress", () => {
  assert.equal(formatMindmapStage(""), "Preparing implementation coverage review…");
  assert.equal(formatMindmapStage("Fetching GitHub code for a/b"), "Downloading repository code…");
  assert.equal(formatMindmapStage("fetching gitlab code"), "Downloading repository code…");
  assert.equal(formatMindmapStage("reusing index x"), "Reusing the existing code index for unchanged repositories…");
  assert.equal(formatMindmapStage("indexed 40 files"), "Indexing implementation files and preparing coverage checks…");
  assert.equal(formatMindmapStage("reviewing — Login"), "Reviewing coverage for Login…");
  assert.equal(formatMindmapStage("custom"), "custom");
  assert.equal(progressBits({ code_chunks: 12, features_mapped: 1 }), "12 implementation chunks indexed · 1 feature reviewed");
  assert.equal(progressBits({}), "");
  assert.equal(
    completeText({ code_chunks: 5, features_mapped: 2, tests_skipped: 3 }),
    "Review complete · 5 implementation chunks indexed · 2 features reviewed · 3 test files excluded",
  );
  assert.equal(completeText({}), "Review complete · 0 implementation chunks indexed · 0 features reviewed");
});

test("repo kinds, branches and the picker list", () => {
  assert.equal(repoKindLabel("test"), "Test");
  assert.equal(repoKindLabel(undefined), "BE");
  assert.equal(repoKindClass("FE"), "fe");
  assert.equal(repoAnalysisDefaultChecked("infra"), false);
  assert.equal(repoAnalysisDefaultChecked("INFRA"), false);
  assert.equal(repoAnalysisDefaultChecked("BE"), true);
  assert.deepEqual(branchMap([{ id: "a", branch: " dev " }, { id: "b", branch: "" }]), { a: "dev" });
  const acc = [{ full_name: "o/A" }, { full_name: "o/b" }, { full_name: "x/c" }];
  assert.deepEqual(withoutConnected(acc, [{ full_name: "O/a" }]).map((r) => r.full_name), ["o/b", "x/c"]);
  assert.deepEqual(filterPickerRepos(acc, "O/").map((r) => r.full_name), ["o/A", "o/b"]);
  assert.equal(filterPickerRepos(Array.from({ length: 400 }, (_, i) => ({ full_name: `r${i}` })), "").length, 300);
});

test("coverage totals, bar and empty-reason lines", () => {
  const feats = [{ counts: { covered: 1, partial: 2, uncovered: 1 } }, { counts: { covered: 3, partial: 0, uncovered: 0 } }];
  assert.deepEqual(coverageTotals(feats), { covered: 4, partial: 2, uncovered: 1 });
  assert.deepEqual(barPercents({ covered: 1, partial: 1, uncovered: 1 }, 3), { covered: 33, partial: 33, uncovered: 33 });
  assert.deepEqual([statusRank("covered"), statusRank("uncovered"), statusRank("x")], [0, 2, 3]);
  assert.deepEqual(emptyReasonLine({ repo: "a", error: "404" }), { repo: "a", text: " (branch default) — fetch error: 404" });
  assert.equal(
    emptyReasonLine({ repo: "a", branch: "dev", reused: true, impl_files: 3 }).text,
    " (branch dev): 3 implementation file(s) indexed (reused, unchanged since last run)",
  );
  assert.equal(
    emptyReasonLine({ repo: "a", branch: "main", files_in_repo: 40, impl_files: 0, test_files: 12, non_impl_files: 28 }).text,
    " (branch main): 40 file(s) total, 0 remaining after excluding 12 test file(s) and 28 non-implementation file(s)",
  );
  assert.equal(hasEmptyReason(null), false);
  assert.equal(hasEmptyReason({ per_repo: [], errors: [] }), false);
  assert.equal(hasEmptyReason({ note: "x" }), true);
});
