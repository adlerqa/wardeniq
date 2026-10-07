import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";

// issue #108: the Upload Documents file picker had no way to remove a single
// selected file short of reselecting all of them. Exercises the real controller
// source (same harness style as login-boot-status.test.js) with a minimal DOM/
// DataTransfer stub, rather than re-implementing the removal logic in the test.

const coreSource = readFileSync(
  new URL("../src/compat/runtime/controllers/00-core.js", import.meta.url), "utf8",
);
// Pull the real `esc()` out of 00-core.js rather than reimplementing an
// approximation -- the escaping test below only means something if it exercises
// the actual escaper the app ships.
const escSource = coreSource.slice(
  coreSource.indexOf("const esc = (s) =>"),
  coreSource.indexOf("const escAttr = esc;") + "const escAttr = esc;".length,
);

const source = readFileSync(
  new URL("../src/compat/runtime/controllers/03-features-and-usage.js", import.meta.url), "utf8",
).split("const FOCUS_TYPES")[0];

class FakeDataTransfer {
  constructor() {
    this._files = [];
    this.items = { add: (f) => this._files.push(f) };
  }
  get files() {
    return this._files;
  }
}

function makeFile(name, size = 100) {
  return { name, size };
}

function harness() {
  const nodes = new Map();
  const $ = (selector) => {
    if (!nodes.has(selector)) {
      nodes.set(selector, {
        hidden: true, textContent: "", innerHTML: "", value: "", files: [],
        style: {}, addEventListener() {}, onclick: null, onchange: null,
      });
    }
    return nodes.get(selector);
  };
  const fileInput = $("#f-file");
  const win = {};
  const context = vm.createContext({
    $, window: win, DataTransfer: FakeDataTransfer,
    setTimeout: () => 0, clearTimeout: () => {},
    api: async () => ({}), currentProject: null, fmtUsd: (n) => `$${n}`,
  });
  vm.runInContext(escSource, context);
  vm.runInContext(source, context);
  return { $, context, fileInput, window: win };
}

test("selecting files renders each one as a row with its own remove control", () => {
  const h = harness();
  h.fileInput.files = [makeFile("a.pdf"), makeFile("b.docx")];
  h.context.renderFeatureFileList();
  const html = h.$("#f-filelist").innerHTML;
  assert.match(html, /2 file\(s\)/);
  assert.match(html, /a\.pdf/);
  assert.match(html, /b\.docx/);
  assert.match(html, /onclick="rmUploadFile\(0\)"/);
  assert.match(html, /onclick="rmUploadFile\(1\)"/);
});

test("removing one file drops only that file and keeps the others, in order", () => {
  const h = harness();
  h.fileInput.files = [makeFile("a.pdf"), makeFile("b.docx"), makeFile("c.md")];
  h.context.renderFeatureFileList();
  h.window.rmUploadFile(1); // remove b.docx
  assert.deepEqual(h.fileInput.files.map((f) => f.name), ["a.pdf", "c.md"]);
  const html = h.$("#f-filelist").innerHTML;
  assert.doesNotMatch(html, /b\.docx/);
  assert.match(html, /a\.pdf/);
  assert.match(html, /c\.md/);
});

test("removing the only selected file clears the list entirely", () => {
  const h = harness();
  h.fileInput.files = [makeFile("only.pdf")];
  h.context.renderFeatureFileList();
  h.window.rmUploadFile(0);
  assert.equal(h.fileInput.files.length, 0);
  assert.equal(h.$("#f-filelist").innerHTML, "");
});

test("removal re-indexes so a second removal still targets the right file", () => {
  const h = harness();
  h.fileInput.files = [makeFile("a.pdf"), makeFile("b.docx"), makeFile("c.md")];
  h.context.renderFeatureFileList();
  h.window.rmUploadFile(0); // remove a.pdf -> [b.docx, c.md], re-rendered
  h.window.rmUploadFile(0); // remove (new) index 0 -> b.docx
  assert.deepEqual(h.fileInput.files.map((f) => f.name), ["c.md"]);
});

test("a filename with HTML-significant characters is escaped, not injected", () => {
  const h = harness();
  h.fileInput.files = [makeFile("<img onerror=alert(1)>.pdf")];
  h.context.renderFeatureFileList();
  const html = h.$("#f-filelist").innerHTML;
  assert.doesNotMatch(html, /<img onerror/);
  assert.match(html, /&lt;img/);
});

test("clearing the input (0 files) renders an empty list, not a stale row", () => {
  const h = harness();
  h.fileInput.files = [makeFile("a.pdf")];
  h.context.renderFeatureFileList();
  h.fileInput.files = [];
  h.context.renderFeatureFileList();
  assert.equal(h.$("#f-filelist").innerHTML, "");
});
