import assert from "node:assert/strict";
import test from "node:test";

import {
  composeAction,
  editFields,
  filterSteps,
  stepBase,
  stepLine,
  stepType,
  typeLabel,
  usagePill,
} from "../src/features/step-library/lib/steps.js";

test("type and base from the keyword", () => {
  assert.equal(stepType("Given a user"), "given");
  assert.equal(stepType("  when x"), "when");
  assert.equal(stepType("Then y"), "then");
  assert.equal(stepType("And z"), "and");
  assert.equal(stepType("But z"), "and");
  assert.equal(stepType("Givenx"), "other");
  assert.equal(stepType(""), "other");
  assert.equal(stepBase("Given  a user "), "a user");
  assert.equal(stepBase("But nothing"), "nothing");
  assert.equal(stepBase("click save"), "click save");
});

test("list line: keyword only for Given/When/Then; others capitalised", () => {
  assert.deepEqual(stepLine("Then status is 200"), { type: "then", keyword: "Then", text: "status is 200" });
  assert.deepEqual(stepLine("and the email is sent"), { type: "and", keyword: null, text: "The email is sent" });
  assert.deepEqual(stepLine("user opens the page"), { type: "other", keyword: null, text: "User opens the page" });
  assert.equal(typeLabel("other"), "Action");
  assert.equal(typeLabel("and"), "And/But");
  assert.equal(typeLabel("given"), "GIVEN");
});

test("filters", () => {
  const steps = [
    { action: "Given a user", expected: "logged out", used_in_cases: 2 },
    { action: "When it runs", expected: "", used_in_cases: 0 },
    { action: "But not twice", expected: "", used_in_cases: 1 },
    { action: "click save", expected: "saved", used_in_cases: 0 },
  ];
  assert.equal(filterSteps(steps, { q: "LOGGED" }).length, 1);
  assert.equal(filterSteps(steps, { type: "Given" }).length, 1);
  assert.equal(filterSteps(steps, { type: "And" }).length, 1);
  assert.equal(filterSteps(steps, { type: "Other" }).length, 1);
  assert.equal(filterSteps(steps, { usage: "used" }).length, 2);
  assert.equal(filterSteps(steps, { usage: "unused" }).length, 2);
  assert.equal(filterSteps(steps, { q: "zzz" }).length, 0);
});

test("usage pill", () => {
  assert.deepEqual(usagePill(1), { unused: false, label: "1 case", title: "Used in 1 test case" });
  assert.deepEqual(usagePill(4), { unused: false, label: "4 cases", title: "Used in 4 test cases" });
  assert.deepEqual(usagePill(0), { unused: true, label: "Unused", title: "Not referenced by any test case yet" });
});

test("edit dialog fields and composed action", () => {
  assert.deepEqual(editFields({ action: "Then the response status is 200 OK", expected: "The API returns 200 OK.", used_in_cases: 4 }), {
    prefix: "Then",
    action: "the response status is 200 OK",
    expected: "The API returns 200 OK.",
    warn: "Warning: This step is referenced by 4 active testcase(s). Updating it will immediately affect all of them.",
  });
  assert.deepEqual(editFields({ action: "click save", used_in_cases: 0 }), {
    prefix: "",
    action: "click save",
    expected: "",
    warn: "",
  });
  assert.equal(editFields({ action: "But not twice", used_in_cases: 0 }).prefix, "But");
  assert.equal(composeAction("Given", "  a user "), "Given a user");
  assert.equal(composeAction("", "click save"), "click save");
});
