import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";

// Rendering hardening: values that come from users, imports or the LLM must be
// escaped before they reach innerHTML -- including inside class attributes -- and
// the Mind Map tooltip must not turn attribute text back into live markup.

const dir = new URL("../src/compat/runtime/controllers/", import.meta.url);
const read = (f) => readFileSync(new URL(f, dir), "utf8");
const coreSource = read("00-core.js");
const escSource = coreSource.slice(
  coreSource.indexOf("const esc = (s) =>"),
  coreSource.indexOf("const escAttr = esc;") + "const escAttr = esc;".length,
);
const mmSource = read("09-mind-map-and-jobs.js");
const tipSource = mmSource.slice(
  mmSource.indexOf("const mmTip = "),
  mmSource.indexOf("const mmPct = "),
);

// Decode an HTML attribute value the way the browser parser does (enough for esc()).
const decodeAttr = (v) =>
  v
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&amp;/g, "&");

// Minimal DOM stand-ins: enough for mmSafeTipNodes to walk a parsed tree.
const el = (tagName, attrs = {}, children = []) => ({
  nodeType: 1,
  tagName,
  childNodes: children,
  getAttribute: (k) => attrs[k] ?? null,
});
const txt = (v) => ({ nodeType: 3, nodeValue: v });
function makeDocument() {
  const mk = (tag) => ({
    tag,
    className: "",
    children: [],
    appendChild(c) {
      this.children.push(c);
      return c;
    },
  });
  return {
    createDocumentFragment: () => mk("#fragment"),
    createElement: (t) => mk(t),
    createTextNode: (v) => ({ tag: "#text", value: v }),
  };
}
const collectTags = (n, acc = []) => {
  acc.push(n.tag);
  (n.children || []).forEach((c) => collectTags(c, acc));
  return acc;
};
const collectText = (n) =>
  n.tag === "#text" ? n.value : (n.children || []).map(collectText).join("");

function loadTip(parsedBody) {
  const context = vm.createContext({
    document: makeDocument(),
    DOMParser: class {
      parseFromString() {
        return { body: parsedBody };
      }
    },
  });
  vm.runInContext(escSource, context);
  vm.runInContext(
    tipSource + "\nthis.mmTip = mmTip; this.mmSafeTipNodes = mmSafeTipNodes;",
    context,
  );
  return context;
}

test("mmTip keeps escaped values escaped through the attribute round-trip", () => {
  const ctx = loadTip(el("BODY"));
  const payload = '<img src=x onerror="alert(1)">';
  const markup = vm.runInContext(
    `"<b>" + esc(${JSON.stringify(payload)}) + "</b>"`,
    ctx,
  );
  const attr = ctx.mmTip(markup);
  const value = attr.match(/^data-tip="([^"]*)"$/)[1];
  // What getAttribute() returns is exactly the escaped markup -- no live <img>.
  assert.equal(decodeAttr(value), markup);
  assert.ok(!decodeAttr(value).includes("<img"));
});

test("mmSafeTipNodes keeps formatting tags and drops anything else", () => {
  const body = el("BODY", {}, [
    el("B", {}, [txt("Feature")]),
    el("BR"),
    el("SPAN", { class: "mm-t-covered" }, [txt("covered")]),
    el("IMG", { src: "x", onerror: "alert(1)" }),
    el("A", { href: "javascript:alert(1)" }, [txt("link")]),
    el("SPAN", { class: 'x" onclick="y' }, [txt("odd")]),
  ]);
  const ctx = loadTip(body);
  const frag = ctx.mmSafeTipNodes("ignored by fake parser");
  const tags = collectTags(frag);
  assert.ok(!tags.includes("img"));
  assert.ok(!tags.includes("a"));
  assert.deepEqual(
    tags.filter((t) => !t.startsWith("#")),
    ["b", "br", "span", "span"],
  );
  const spans = frag.children.filter((c) => c.tag === "span");
  assert.equal(spans[0].className, "mm-t-covered");
  assert.equal(spans[1].className, "");
  assert.equal(collectText(frag), "Featurecoveredlinkodd");
});

test("the Mind Map tooltip is never filled via innerHTML from an attribute", () => {
  assert.ok(!/innerHTML\s*=\s*[^;]*getAttribute\(/.test(mmSource));
  assert.ok(mmSource.includes('mmSafeTipNodes(t.getAttribute("data-tip"))'));
});

test("record fields interpolated into class attributes are escaped", () => {
  const offenders = [];
  for (const f of readdirSync(dir).filter((n) => n.endsWith(".js"))) {
    const src = read(f);
    const re = /class="[^"]*\$\{\s*(?:c|cs|it)\.(?:type|status|category)\s*\}/g;
    for (const m of src.matchAll(re)) offenders.push(`${f}: ${m[0]}`);
  }
  assert.deepEqual(offenders, []);
});
