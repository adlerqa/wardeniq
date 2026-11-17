import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";

const source = readFileSync(
  new URL("../src/compat/runtime/controllers/04-test-cases.js", import.meta.url),
  "utf8",
);

const start = source.indexOf("function expectedItemHtml(item)");
const end = source.indexOf("function expectedResultHtml(value)", start);

assert.notEqual(start, -1);
assert.notEqual(end, -1);

const functionSource = source.slice(start, end);

function render(value) {
  const context = vm.createContext({
    esc: (input) =>
      String(input)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;"),
  });

  vm.runInContext(`${functionSource}; this.render = expectedValueHtml;`, context);
  return context.render(value);
}

test("renders nested objects as readable JSON", () => {
  const html = render({
    session: { id: 123, active: true },
  });

  assert.ok(html.includes("&quot;id&quot;:"));
  assert.ok(html.includes("123"));
  assert.ok(html.includes("&quot;active&quot;:"));
  assert.ok(html.includes("true"));
  assert.ok(!html.includes("[object Object]"));
});

test("renders arrays containing nested objects", () => {
  const html = render([
    { name: "first" },
    { name: "second" },
  ]);

  assert.ok(html.includes("&quot;name&quot;:"));
  assert.ok(html.includes("first"));
  assert.ok(html.includes("second"));
  assert.ok(!html.includes("[object Object]"));
});

test("escapes HTML inside nested objects", () => {
  const html = render({
    session: { name: '<img src=x onerror="alert(1)">' },
  });

  assert.ok(!html.includes("<img"));
  assert.ok(html.includes("&lt;img"));
});

test("preserves primitive values", () => {
  const html = render({
    status_code: 200,
  });

  assert.ok(html.includes("200"));
});

test("handles null values without rendering object text", () => {
  const html = render({
    session: null,
  });

  assert.ok(!html.includes("[object Object]"));
});