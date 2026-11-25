import assert from "node:assert/strict";
import test from "node:test";

import { harness, makeFile, window } from "./features-harness.js";

// Issue #108: each selected file on the "New feature" page has its own remove
// control. The input's FileList is read-only, so removal rebuilds it through a
// DataTransfer and reassigns input.files — the upload reads that same input.

test.after(() => window.close());

async function openCreate(t) {
  const h = harness(t);
  await h.open();
  await h.flush(() => window.showFeatureCreate());
  return h;
}
const removeBtn = (h, i) => h.$("#f-filelist").querySelectorAll("button")[i];

test("selecting files renders each one as a row with its own remove control", async (t) => {
  const h = await openCreate(t);
  await h.setFiles(h.$("#f-file"), [makeFile("a.pdf"), makeFile("b.docx")]);
  const list = h.$("#f-filelist");
  assert.match(list.textContent, /2 file\(s\)/);
  assert.deepEqual([...list.querySelectorAll(".f-file-name")].map((e) => e.textContent), ["a.pdf", "b.docx"]);
  assert.deepEqual([...list.querySelectorAll("button")].map((b) => b.getAttribute("aria-label")), ["Remove a.pdf", "Remove b.docx"]);
});

test("removing one file drops only that file and keeps the others, in order", async (t) => {
  const h = await openCreate(t);
  const input = h.$("#f-file");
  await h.setFiles(input, [makeFile("a.pdf"), makeFile("b.docx"), makeFile("c.md")]);
  await h.click(removeBtn(h, 1));
  assert.deepEqual([...input.files].map((f) => f.name), ["a.pdf", "c.md"]);
  assert.doesNotMatch(h.$("#f-filelist").textContent, /b\.docx/);
  assert.match(h.$("#f-filelist").textContent, /a\.pdf.*c\.md/);
});

test("removing the only selected file clears the list entirely", async (t) => {
  const h = await openCreate(t);
  const input = h.$("#f-file");
  await h.setFiles(input, [makeFile("only.pdf")]);
  await h.click(removeBtn(h, 0));
  assert.equal(input.files.length, 0);
  assert.equal(h.$("#f-filelist").innerHTML, "");
});

test("removal re-indexes so a second removal still targets the right file", async (t) => {
  const h = await openCreate(t);
  const input = h.$("#f-file");
  await h.setFiles(input, [makeFile("a.pdf"), makeFile("b.docx"), makeFile("c.md")]);
  await h.click(removeBtn(h, 0));
  await h.click(removeBtn(h, 0));
  assert.deepEqual([...input.files].map((f) => f.name), ["c.md"]);
});

test("a filename with HTML-significant characters is escaped, not injected", async (t) => {
  const h = await openCreate(t);
  await h.setFiles(h.$("#f-file"), [makeFile("<img onerror=alert(1)>.pdf")]);
  assert.equal(h.$("#f-filelist img"), null);
  assert.equal(h.$("#f-filelist .f-file-name").innerHTML, "&lt;img onerror=alert(1)&gt;.pdf");
});

test("clearing the input (0 files) renders an empty list, not a stale row", async (t) => {
  const h = await openCreate(t);
  await h.setFiles(h.$("#f-file"), [makeFile("a.pdf")]);
  await h.setFiles(h.$("#f-file"), []);
  assert.equal(h.$("#f-filelist").innerHTML, "");
});
