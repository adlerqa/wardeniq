import assert from "node:assert/strict";
import test from "node:test";

import { mmLayout, mmModel, mmWrap, treeRows, zoomStep } from "../src/features/mind-map/lib/graph.js";

const feat = (name, repos, counts, cases = []) => ({ feature: name, feature_id: name, version: 1, counts, cases, repos, reviewed_files: [] });

test("model: duplicate names, totals, repo groups and evidence hotspots", () => {
  const m = mmModel({
    features: [
      feat("Login", ["o/a"], { covered: 1, partial: 0, uncovered: 1 }, [
        { status: "uncovered", files: [] },
        { status: "covered", files: ["x.py", "y.py"] },
      ]),
      feat("Login", [], { covered: 0, partial: 0, uncovered: 0 }),
      feat("Reset", ["o/a", "o/b"], { covered: 2, partial: 1, uncovered: 0 }, [{ status: "covered", files: ["x.py"] }]),
    ],
  });
  assert.deepEqual(m.feats.map((f) => f.label), ["Login (1/2)", "Login (2/2)", "Reset"]);
  assert.deepEqual(m.feats[0].cases.map((c) => c.status), ["covered", "uncovered"]);
  assert.deepEqual(m.totals, { covered: 3, partial: 1, uncovered: 1 });
  assert.equal(m.grand, 5);
  assert.deepEqual(m.repos, ["o/a", "(no repository)", "o/b"]);
  assert.deepEqual(m.groups.get("o/a").map((f) => f.i), [0, 2]);
  assert.deepEqual(m.evidence, [
    { file: "x.py", cases: 2, feats: 2 },
    { file: "y.py", cases: 1, feats: 1 },
  ]);
});

test("layout choice and zoom limits", () => {
  const small = mmModel({ features: [feat("A", ["o/a"], { covered: 1 })] });
  assert.equal(mmLayout(small, "auto"), "radial");
  assert.equal(mmLayout(small, "tree"), "tree");
  const many = mmModel({ features: Array.from({ length: 10 }, (_, i) => feat(`F${i}`, ["o/a"], { covered: 1 })) });
  assert.equal(mmLayout(many, "auto"), "tree");
  const multi = mmModel({ features: [feat("A", ["o/a"], {}), feat("B", ["o/b"], {})] });
  assert.equal(mmLayout(multi, "auto"), "tree");
  assert.equal(zoomStep(1, 1.18), 1.18);
  assert.equal(zoomStep(2, 1.18), 2.2);
  assert.equal(zoomStep(0.55, 0.85), 0.5);
});

test("tree rows: buckets, expanded cases, +N more, empty filter", () => {
  const cases = Array.from({ length: 50 }, (_, i) => ({ status: i < 2 ? "partial" : "covered", title: `c${i}` }));
  const m = mmModel({
    features: [feat("A", ["o/a"], { covered: 48, partial: 2, uncovered: 0 }, cases), feat("B", ["o/a"], {})],
  });
  const closed = treeRows(m, null, null);
  assert.equal(closed.multi, false);
  assert.deepEqual(closed.groups[0].feats.map((it) => it.kids.map((k) => `${k.kind}:${k.k}`)), [
    ["bucket:covered", "bucket:partial"],
    ["bucket:na"],
  ]);
  assert.deepEqual(closed.groups[0].feats[0].kids.map((k) => k.y), [64, 94]);
  const open = treeRows(m, 0, null);
  const kids = open.groups[0].feats[0].kids;
  assert.equal(kids.length, 49);
  assert.deepEqual(kids.at(-1), { kind: "more", n: 2, y: 64 + 48 * 30 });
  assert.equal(open.H, Math.max(300, 64 + 50 * 30 + 34));
  assert.deepEqual(treeRows(m, 0, "uncovered").groups[0].feats[0].kids.map((k) => k.kind), ["none"]);
});

test("label wrapping", () => {
  assert.deepEqual(mmWrap("Password reset for locked out accounts", 21, 2), ["Password reset for", "locked out accounts"]);
  assert.deepEqual(mmWrap("", 21, 2), [""]);
});
