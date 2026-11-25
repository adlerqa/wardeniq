import assert from "node:assert/strict";
import { createRequire } from "node:module";
import test from "node:test";
import { fileURLToPath } from "node:url";
import vm from "node:vm";
import { build } from "esbuild";
import { JSDOM } from "jsdom";
import React, { act } from "react";

// The Mind Map screen (features/mind-map): window.initMindmap() — called by
// navigateTo("mindmap") — loads the projects, the repo list and the map.
// Was a vm test of loadMindmapRepos / loadMindmap in 09-mind-map-and-jobs.js.

const dom = new JSDOM("<!doctype html><body></body>", { url: "http://localhost/" });
const { window } = dom;
const { document } = window;
Object.assign(globalThis, { window, document, IS_REACT_ACT_ENVIRONMENT: true });
const { createRoot } = await import("react-dom/client");
test.after(() => window.close());

const entry = fileURLToPath(new URL("../src/features/mind-map/pages/MindMapPage.jsx", import.meta.url));
const bundled = await build({
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
const require = createRequire(import.meta.url);
const settle = () => new Promise((r) => setTimeout(r, 0));

const REPOS = { repos: [{ id: "repo1", full_name: "test/repo", kind: "BE", default_branch: "main" }] };

function harness(t, mindmap) {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const graph = [];
  Object.assign(window, {
    loadProjects: async () => {
      window.allProjects = [{ id: "test-proj", name: "P", repo_count: 1, feature_count: 0 }];
    },
    getCurrentProject: () => "test-proj",
    setMindmapGraphData: (d) => graph.push(d),
    toast: () => {},
  });
  let current = mindmap;
  async function fakeFetch(path) {
    const body = path.includes("/repos?repo_type=app")
      ? REPOS
      : path.includes("/mindmap")
        ? current
        : path.includes("/branches")
          ? { branches: ["main"] }
          : {};
    return { status: 200, ok: true, text: async () => JSON.stringify(body) };
  }
  const module = { exports: {} };
  vm.runInNewContext(bundled.outputFiles[0].text, {
    module, exports: module.exports, require, window, document, console, fetch: fakeFetch, setTimeout,
    clearTimeout, DOMPoint: class {},
  });
  const root = createRoot(container);
  t.after(async () => {
    await act(async () => root.unmount());
    container.remove();
  });
  return {
    container,
    graph,
    setMindmap: (m) => (current = m),
    $: (s) => container.querySelector(s),
    async open() {
      await act(async () => root.render(React.createElement(module.exports.default)));
      await act(async () => {
        await window.initMindmap();
        for (let i = 0; i < 6; i++) await settle();
      });
    },
    async refresh() {
      await act(async () => {
        container.querySelector("#mm-refresh").click();
        for (let i = 0; i < 6; i++) await settle();
      });
    },
  };
}

test("page load renders the repo checkboxes and the indexed-code diagnostics", async (t) => {
  const h = harness(t, {
    features: [],
    last_analysis: { per_repo: [{ repo: "test/repo", branch: "main", impl_files: 42 }] },
  });
  await h.open();

  const reposHtml = h.$("#mm-repos").innerHTML;
  assert.match(reposHtml, /mm-repo-chk/, "repo checkboxes are rendered");
  assert.match(reposHtml, /test\/repo/, "the repository name is shown");

  const diagHtml = h.$("#mm-diag").innerHTML;
  assert.match(diagHtml, /Indexed code by repository/, "the diagnostics panel is rendered");
  assert.match(diagHtml, /42 impl indexed/, "it shows the indexed file count");
  assert.equal(h.graph.length, 1, "the graph receives the loaded data");
});

test("page load clears stale diagnostics when the project has no analysis", async (t) => {
  const h = harness(t, {
    features: [],
    last_analysis: { per_repo: [{ repo: "test/repo", branch: "main", impl_files: 42 }] },
  });
  await h.open();
  assert.match(h.$("#mm-diag").innerHTML, /Indexed code by repository/);

  h.setMindmap({ features: [], last_analysis: null });
  await h.refresh();

  assert.equal(h.$("#mm-diag").innerHTML, "");
});
