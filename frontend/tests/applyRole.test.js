
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";

const source = readFileSync(
  new URL(
    "../src/compat/runtime/controllers/10-auth.js",
    import.meta.url
  ),
  "utf8"
);

const start = source.indexOf("function applyRole()");
const end = source.indexOf(
  "// ---- change password",
  start
);

assert.ok(start >= 0 && end > start);

function harness(email) {
  const nodes = new Map();

  const $ = (selector) => {
    if (!nodes.has(selector)) {
      nodes.set(selector, {
        hidden: false,
        textContent: "",
        title: "",
        className: "",
      });
    }
    return nodes.get(selector);
  };

  const context = vm.createContext({
    $,
    ME: { email, role: "viewer" },
    document: {
      body: {
        classList: {
          toggle() {},
        },
      },
      querySelectorAll() {
        return [];
      },
    },
    applyRoleTooltips() {},
  });

  vm.runInContext(source.slice(start, end), context);

  return { $, applyRole: context.applyRole };
}

test("applyRole sets the full email as tooltip title", () => {
  const email = "verylongemailaddress@example.com";
  const h = harness(email);

  h.applyRole();

  assert.equal(h.$("#user-email").title, email);
});

test("applyRole displays the user's full email text", () => {
  const email = "user@example.com";
  const h = harness(email);

  h.applyRole();

  assert.equal(h.$("#user-email").textContent, email);
});
