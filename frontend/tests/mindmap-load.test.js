import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";

// The Mind Map controller is a plain script, so run it in a vm context with stubs for the
// globals it expects.
const source = readFileSync(
  new URL("../src/compat/runtime/controllers/09-mind-map-and-jobs.js", import.meta.url),
  "utf8",
);

function harness(api) {
  const nodes = new Map();
  const $ = (selector) => {
    if (!nodes.has(selector)) {
      nodes.set(selector, { innerHTML: "", value: "test-proj", hidden: false, textContent: "" });
    }
    return nodes.get(selector);
  };

  const context = vm.createContext({
    $,
    api,
    currentProject: "test-proj",
    esc: (s) => String(s || ""),
    repoKindClass: () => "github",
    repoKindLabel: () => "GitHub",
    repoAnalysisDefaultChecked: () => true,
    typeLabel: () => "Feature",
    skIn: () => {},
    skeleton: { rows: () => "" },
    toast: () => {},
    watchJob: () => {},
    document: {
      addEventListener: () => {},
      querySelector: (sel) => $(sel),
      querySelectorAll: () => [],
      createElement: () => ({ style: {}, appendChild: () => {} }),
      body: { appendChild: () => {} },
    },
    window: {},
  });

  vm.runInContext(source, context);
  return { $, context };
}

const REPOS = { repos: [{ id: "repo1", full_name: "test/repo", kind: "github" }] };

function apiWith(mindmap) {
  return async (path) => {
    if (path.includes("/repos?repo_type=app")) return REPOS;
    if (path.includes("/mindmap")) return mindmap;
    if (path.includes("/branches")) return { branches: ["main"] };
    return {};
  };
}

test("page load renders the repo checkboxes and the indexed-code diagnostics", async () => {
  const h = harness(
    apiWith({
      features: [],
      last_analysis: { per_repo: [{ repo: "test/repo", branch: "main", impl_files: 42 }] },
    }),
  );

  // The order the Mind Map page uses on load and on project change.
  await h.context.loadMindmapRepos();
  await h.context.loadMindmap();

  const reposHtml = h.$("#mm-repos").innerHTML;
  assert.match(reposHtml, /mm-repo-chk/, "repo checkboxes are rendered");
  assert.match(reposHtml, /test\/repo/, "the repository name is shown");

  const diagHtml = h.$("#mm-diag").innerHTML;
  assert.match(diagHtml, /Indexed code by repository/, "the diagnostics panel is rendered");
  assert.match(diagHtml, /42 impl indexed/, "it shows the indexed file count");
});

test("page load clears stale diagnostics when the project has no analysis", async () => {
  const h = harness(apiWith({ features: [], last_analysis: null }));
  h.$("#mm-diag").innerHTML = "<div>left over from another project</div>";

  await h.context.loadMindmap();

  assert.equal(h.$("#mm-diag").innerHTML, "");
});
