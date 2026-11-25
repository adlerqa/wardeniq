import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import test from "node:test";

// Rendering hardening: values that come from users, imports or the LLM must be
// escaped before they reach innerHTML -- including inside class attributes -- and
// the Mind Map tooltip must not turn attribute text back into live markup.

const dir = new URL("../src/compat/runtime/controllers/", import.meta.url);
const read = (f) => readFileSync(new URL(f, dir), "utf8");
// The Mind Map graph is React now (features/mind-map): its tooltips are built
// in lib/graph.js and shown by hooks/useCoverageGraph.js.
const mmHookSource = readFileSync(
  new URL("../src/features/mind-map/hooks/useCoverageGraph.js", import.meta.url),
  "utf8",
);
const { caseTip, featTip, mmSafeTipNodes } = await import("../src/features/mind-map/lib/graph.js");

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

const fakeParser = (parsedBody) =>
  class {
    parseFromString() {
      return { body: parsedBody };
    }
  };

test("graph tooltips keep record values escaped in the data-tip markup", () => {
  const payload = '<img src=x onerror="alert(1)">';
  const feat = featTip({ label: payload, version: 1, counts: { covered: 0 }, total: 1, repos: [payload] });
  const cs = caseTip({ title: payload, status: "covered", type: "api", rationale: payload, files: [payload] });
  for (const markup of [feat, cs]) {
    // The attribute holds exactly this markup; the values in it stay escaped.
    assert.ok(!markup.includes("<img"));
    assert.ok(markup.includes("&lt;img src=x onerror=&quot;alert(1)&quot;&gt;"));
  }
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
  const frag = mmSafeTipNodes("ignored by fake parser", makeDocument(), fakeParser(body));
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
  assert.ok(!/innerHTML/.test(mmHookSource));
  assert.ok(mmHookSource.includes('mmSafeTipNodes(t.getAttribute("data-tip"))'));
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
