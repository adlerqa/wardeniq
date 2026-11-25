import assert from "node:assert/strict";
import test from "node:test";

import {
  cardMeta,
  confluenceChoices,
  createBody,
  defaultRepoLabel,
  jiraChoices,
  pickCurrent,
  pickerRows,
  stagedRepoBodies,
  statsText,
} from "../src/features/projects/lib/projects.js";

test("card and header text", () => {
  assert.equal(cardMeta({ feature_count: 1, repo_count: 1 }), "1 feature · 1 repository");
  assert.equal(cardMeta({ feature_count: 0, repo_count: 2 }), "0 features · 2 repositories");
  assert.equal(statsText({ feature_count: 1, repo_count: 1 }), "1 repositories · 1 features");
});

test("current project after a reload", () => {
  const list = [{ id: "a" }, { id: "b" }];
  assert.equal(pickCurrent(list, "b"), "b");
  assert.equal(pickCurrent(list, "zz"), "a");
  assert.equal(pickCurrent(list, null), "a");
  assert.equal(pickCurrent([], "a"), "");
});

test("Jira / Confluence choices", () => {
  const j = jiraChoices([{ key: "A", name: "Alpha" }, { key: "B", name: "B", in_use: true }]);
  assert.deepEqual(j.options, [{ value: "A", name: "Alpha", label: "A — Alpha" }]);
  assert.equal(j.status, "1 project(s) available · 1 already linked");
  assert.equal(jiraChoices([]).status, "0 project(s) available");
  assert.equal(confluenceChoices([{ key: "S", name: "Sp" }]).status, "1 space(s) available");
});

test("create wizard: pickers, labels and request bodies", () => {
  assert.equal(defaultRepoLabel("o/web-app_ui"), "web app ui");
  const avail = [{ full_name: "o/a" }, { full_name: "o/b" }, { full_name: "o/c" }];
  const rows = pickerRows(avail, [{ full_name: "o/a", label: "A" }], [{ full_name: "o/b" }]);
  assert.deepEqual(rows.map((r) => [r.repo.full_name, r.staged && r.staged.label]), [["o/a", "A"], ["o/c", null]]);
  assert.deepEqual(
    createBody({ name: "N", description: "", jira: { value: "A", name: "", label: "A — x" }, confluence: null, provider: "gitlab" }),
    {
      name: "N",
      description: "",
      jira_project_key: "A",
      jira_project_name: "A — x",
      confluence_space_key: null,
      confluence_space_name: null,
      default_git_provider: "gitlab",
    },
  );
  assert.deepEqual(stagedRepoBodies([{ full_name: "o/a", label: "  " }], [{ full_name: "o/t", label: "T", kind: "" }], "github"), [
    { repo_full_name: "o/a", label: "o/a", repo_type: "app", git_provider: "github", kind: "BE" },
    { repo_full_name: "o/t", label: "T", repo_type: "test", git_provider: "github", kind: "test" },
  ]);
});
