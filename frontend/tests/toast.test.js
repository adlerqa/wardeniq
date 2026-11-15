
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import vm from "node:vm";
import { JSDOM } from "jsdom";

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

function createToastHarness() {
  const dom = new JSDOM('<div id="toast"></div>');
  const timeouts = [];

  const context = vm.createContext({
    document: dom.window.document,
    setTimeout(callback, delay) {
      timeouts.push({ callback, delay });
      return timeouts.length;
    },
    clearTimeout() {},
  });

  vm.runInContext(
    `${toastSrc}\nglobalThis.testToast = toast;`,
    context,
  );

  return {
    toast: context.testToast,
    document: dom.window.document,
    timeouts,
    close: () => dom.window.close(),
  };
}

test("warning toast renders the correct class, title, icon and message", () => {
  const h = createToastHarness();

  try {
    const element = h.toast("Invitation email failed", {
      type: "warn",
    });

    assert.equal(element.className, "toastmsg warn");
    assert.equal(element.querySelector(".t-ico").textContent, "⚠");
    assert.equal(element.querySelector(".t-title").textContent, "Warning");
    assert.equal(
      element.querySelector(".t-msg").textContent,
      "Invitation email failed",
    );

    assert.equal(h.document.querySelectorAll("#toast .toastmsg").length, 1);
  } finally {
    h.close();
  }
});

test("warning toast uses the warning-specific duration", () => {
  const h = createToastHarness();

  try {
    const message = "Invitation email failed";
    const expectedDuration = Math.min(
      9000,
      5200 + message.length * 35,
    );

    const element = h.toast(message, { type: "warn" });

    assert.equal(h.timeouts[0].delay, expectedDuration);
    assert.match(
      element.querySelector(".t-timer").getAttribute("style"),
      new RegExp(`${expectedDuration}ms`),
    );
  } finally {
    h.close();
  }
});

test("legacy error and success calls retain their behavior", () => {
  const h = createToastHarness();

  try {
    const errorToast = h.toast("Something failed", true);

    assert.equal(errorToast.className, "toastmsg err");
    assert.equal(errorToast.querySelector(".t-ico").textContent, "!");
    assert.equal(
      errorToast.querySelector(".t-title").textContent,
      "Something went wrong",
    );

    const successToast = h.toast("User created");

    assert.equal(successToast.className, "toastmsg ok");
    assert.equal(successToast.querySelector(".t-ico").textContent, "✓");
    assert.equal(
      successToast.querySelector(".t-title").textContent,
      "Success",
    );
  } finally {
    h.close();
  }
});

test("toast supports custom types, titles and durations", () => {
  const h = createToastHarness();

  try {
    const element = h.toast("Custom notification", {
      type: "info",
      title: "Custom title",
      duration: 6000,
    });

    assert.equal(element.className, "toastmsg info");
    assert.equal(element.querySelector(".t-ico").textContent, "i");
    assert.equal(
      element.querySelector(".t-title").textContent,
      "Custom title",
    );
    assert.equal(h.timeouts[0].delay, 6000);
  } finally {
    h.close();
  }
});

test("warning toast supports a custom title", () => {
  const h = createToastHarness();

  try {
    const element = h.toast("Invitation email failed", {
      type: "warn",
      title: "Invitation email not sent",
    });

    assert.equal(
      element.querySelector(".t-title").textContent,
      "Invitation email not sent",
    );
  } finally {
    h.close();
  }
});
