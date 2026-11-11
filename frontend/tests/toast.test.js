
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { test } from "node:test";

const src = readFileSync(
  join(
    dirname(fileURLToPath(import.meta.url)),
    "../src/compat/runtime/controllers/00-core.js",
  ),
  "utf8",
);

const start = src.indexOf("function toast(msg, opt)");
const end = src.indexOf("// confirmModal", start);

assert.ok(start >= 0 && end > start, "toast function should exist");

const toastSrc = src.slice(start, end);

test("toast supports the warning type with a default title and icon", () => {
  assert.match(toastSrc, /warn:\s*"Warning"/);
  assert.match(toastSrc, /warn:\s*"⚠"/);
});

test("toast supports warning-specific duration", () => {
  assert.match(
    toastSrc,
    /type === "err" \|\| type === "warn"/,
  );
});

test("toast preserves legacy error and success behavior", () => {
  assert.match(toastSrc, /if \(opt === true\)/);
  assert.match(toastSrc, /type = "err"/);
  assert.match(toastSrc, /ok:\s*"Success"/);
  assert.match(toastSrc, /err:\s*"Something went wrong"/);
});

test("toast supports custom titles and types", () => {
  assert.match(toastSrc, /type = opt\.type/);
  assert.match(toastSrc, /title = opt\.title/);
});
