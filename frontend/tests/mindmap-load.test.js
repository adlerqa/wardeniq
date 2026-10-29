import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";

// Read the mind map controller source
const source = readFileSync(
  new URL("../src/compat/runtime/controllers/09-mind-map-and-jobs.js", import.meta.url),
  "utf8"
);

function harness(api) {
  const nodes = new Map();
  // Mock the jQuery-like selector used in the codebase
  const $ = (selector) => {
    if (!nodes.has(selector)) {
      nodes.set(selector, { innerHTML: "", value: "test-proj", hidden: false, textContent: "" });
    }
    return nodes.get(selector);
  };

  // Provide the global dependencies and stubs the controller expects
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
      body: { appendChild: () => {} }
    },
    window: {}
  });

  vm.runInContext(source, context);
  return { $, context };
}

test("page load sequence renders repo checkboxes and diagnostic panel", async () => {
  // 1. Stub the API to return the distinct responses the controller expects
  const h = harness(async (path) => {
    if (path.includes("/repos?repo_type=app")) {
      return { repos: [{ id: "repo1", full_name: "test/repo", kind: "github" }] };
    }
    if (path.includes("/mindmap")) {
      return {
        features: [],
        last_analysis: {
          per_repo: [{ repo: "test/repo", branch: "main", impl_files: 42 }]
        }
      };
    }
    if (path.includes("/branches")) {
      return { branches: ["main"] };
    }
    return {};
  });

  // 2. Execute the page-load path the maintainer requested
  await h.context.loadMindmapRepos();
  await h.context.loadMindmap();

  // 3. Assert the repo checkboxes are populated (Fixes the new regression)
  const reposHtml = h.$("#mm-repos").innerHTML;
  assert.match(reposHtml, /mm-repo-chk/, "Should render checkbox inputs");
  assert.match(reposHtml, /test\/repo/, "Should render the repository name");

  // 4. Assert the diagnostics panel survives and renders (Fixes original Issue #103)
  const diagHtml = h.$("#mm-diag").innerHTML;
  assert.match(diagHtml, /Indexed code by repository/, "Should render the diagnostics panel summary");
  assert.match(diagHtml, /42 impl indexed/, "Should render the mock impl_files count");
});