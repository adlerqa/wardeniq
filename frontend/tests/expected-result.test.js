import assert from "node:assert/strict";
import { createRequire } from "node:module";
import test from "node:test";
import { fileURLToPath } from "node:url";
import vm from "node:vm";
import { build } from "esbuild";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

// The structured "Expected result" values in a test case's detail (React CaseDetail).
const entry = fileURLToPath(new URL("../src/features/test-cases/components/CaseDetail.jsx", import.meta.url));
const bundled = await build({
  entryPoints: [entry], bundle: true, write: false, format: "cjs", platform: "neutral", jsx: "automatic",
  external: ["react", "react/jsx-runtime", "react-dom"], logLevel: "silent",
});
const require = createRequire(import.meta.url);
const module = { exports: {} };
vm.runInNewContext(bundled.outputFiles[0].text, { module, exports: module.exports, require, console });
const render = (value) => renderToStaticMarkup(React.createElement(module.exports.ExpectedValue, { value }));

test("renders nested objects as readable JSON", () => {
  const html = render({ session: { id: 123, active: true } });
  assert.ok(html.includes("&quot;id&quot;:"));
  assert.ok(html.includes("123"));
  assert.ok(html.includes("&quot;active&quot;:"));
  assert.ok(html.includes("true"));
  assert.ok(!html.includes("[object Object]"));
});

test("renders arrays containing nested objects", () => {
  const html = render([{ name: "first" }, { name: "second" }]);
  assert.ok(html.includes("&quot;name&quot;:"));
  assert.ok(html.includes("first"));
  assert.ok(html.includes("second"));
  assert.ok(!html.includes("[object Object]"));
});

test("escapes HTML inside nested objects", () => {
  const html = render({ session: { name: '<img src=x onerror="alert(1)">' } });
  assert.ok(!html.includes("<img"));
  assert.ok(html.includes("&lt;img"));
});

test("preserves primitive values", () => {
  assert.ok(render({ status_code: 200 }).includes("200"));
});

test("handles null values without rendering object text", () => {
  assert.ok(!render({ session: null }).includes("[object Object]"));
});
