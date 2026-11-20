import assert from "node:assert/strict";
import test from "node:test";
import { JSDOM } from "jsdom";
import {
  computeDropdownPlacement,
  isEnhanceableSelect,
  nextEnabledRow,
  readSelectItems,
  typeaheadRow,
} from "../src/components/forms/selectDropdownModel.js";

const rect = (top, height = 40, left = 100, width = 260) => ({
  top,
  bottom: top + height,
  left,
  width,
  height,
});

test("panel opens below the field and matches its width", () => {
  const p = computeDropdownPlacement(rect(100), 900);
  assert.equal(p.placement, "bottom");
  assert.equal(p.top, 144);
  assert.equal(p.left, 100);
  assert.equal(p.width, 260);
  assert.equal(p.maxHeight, 320);
});

test("panel stays below while there is reasonable room", () => {
  const p = computeDropdownPlacement(rect(650), 900); // ~198px below
  assert.equal(p.placement, "bottom");
  assert.ok(p.maxHeight <= 900 - 690);
});

test("panel flips above only when the field sits at the viewport bottom", () => {
  const p = computeDropdownPlacement(rect(820), 900);
  assert.equal(p.placement, "top");
  assert.equal(p.width, 260);
});

test("readSelectItems flattens options and optgroups", () => {
  const { document } = new JSDOM(`<select id="s">
    <option value="">All</option>
    <optgroup label="G"><option value="a">Alpha</option><option value="b" disabled>Beta</option></optgroup>
    <option value="c" selected>Charlie</option></select>`).window;
  const rows = readSelectItems(document.getElementById("s"));
  assert.deepEqual(
    rows.map((r) => (r.kind === "group" ? `#${r.label}` : `${r.label}${r.disabled ? "!" : ""}${r.selected ? "*" : ""}`)),
    ["All", "#G", "Alpha", "Beta!", "Charlie*"],
  );
  assert.equal(nextEnabledRow(rows, 2, 1), 4); // skips disabled Beta
  assert.equal(typeaheadRow(rows, 0, "ch"), 4);
});

test("only single-value enabled selects are enhanced", () => {
  const { document } = new JSDOM(`<select id="a"></select><select id="b" multiple></select>
    <select id="c" disabled></select><select id="d" data-native-select></select>`).window;
  assert.equal(isEnhanceableSelect(document.getElementById("a")), true);
  for (const id of ["b", "c", "d"]) assert.equal(isEnhanceableSelect(document.getElementById(id)), false);
});
