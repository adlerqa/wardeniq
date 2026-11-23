import assert from "node:assert/strict";
import test from "node:test";

import { createModalFocusManager } from "../src/components/overlays/modalFocus.js";

class FakeClassList {
  constructor(values = []) {
    this.values = new Set(values);
  }

  contains(value) {
    return this.values.has(value);
  }

  add(value) {
    this.values.add(value);
  }

  remove(value) {
    this.values.delete(value);
  }
}

class FakeElement {
  constructor(doc, { classes = [], focusable = false, tagName = "BUTTON" } = {}) {
    this.doc = doc;
    this.classList = new FakeClassList(classes);
    this.disabled = false;
    this.focusable = focusable;
    this.hidden = false;
    this.isConnected = true;
    this.parentElement = null;
    this.tabIndex = focusable ? 0 : -1;
    this.tagName = tagName;
  }

  closest() {
    return null;
  }

  contains(element) {
    for (let current = element; current; current = current.parentElement) {
      if (current === this) return true;
    }
    return false;
  }

  focus(options) {
    this.doc.activeElement = this;
    this.doc.dispatch("focusin", { target: this, options });
  }

  getClientRects() {
    if (this.hidden) return [];
    const modal = this.findModal();
    if (modal && !modal.classList.contains("show")) return [];
    return [{}];
  }

  matches() {
    return this.focusable;
  }

  querySelector() {
    return this.initialFocus || null;
  }

  querySelectorAll() {
    return (this.controls || []).filter((control) => control.focusable);
  }

  findModal() {
    for (let current = this; current; current = current.parentElement) {
      if (current.classList.contains("modal")) return current;
    }
    return null;
  }
}

class FakeDocument {
  constructor() {
    this.activeElement = null;
    this.body = new FakeElement(this, { tagName: "BODY" });
    this.listeners = new Map();
    this.modals = [];
    this.defaultView = {
      getComputedStyle: () => ({
        display: "block",
        visibility: "visible",
      }),
    };
  }

  addEventListener(type, listener) {
    const listeners = this.listeners.get(type) || new Set();
    listeners.add(listener);
    this.listeners.set(type, listeners);
  }

  dispatch(type, event) {
    for (const listener of this.listeners.get(type) || []) {
      listener(event);
    }
  }

  querySelectorAll(selector) {
    if (selector === ".modal.show") {
      return this.modals.filter((modal) => modal.classList.contains("show"));
    }
    return [];
  }

  removeEventListener(type, listener) {
    this.listeners.get(type)?.delete(listener);
  }
}

function createModal(doc, controlCount = 2) {
  const modal = new FakeElement(doc, { classes: ["modal"], tagName: "DIV" });
  modal.controls = Array.from({ length: controlCount }, () => {
    const control = new FakeElement(doc, { focusable: true });
    control.parentElement = modal;
    return control;
  });
  doc.modals.push(modal);
  return modal;
}

function tab(doc, shiftKey = false) {
  const event = {
    key: "Tab",
    shiftKey,
    prevented: false,
    preventDefault() {
      this.prevented = true;
    },
  };
  doc.dispatch("keydown", event);
  return event;
}

test("opening a modal focuses it and closing returns to the opener", () => {
  const doc = new FakeDocument();
  const opener = new FakeElement(doc, { focusable: true });
  const modal = createModal(doc);
  const manager = createModalFocusManager(doc);
  manager.start();

  opener.focus();
  modal.classList.add("show");
  manager.sync();
  assert.equal(doc.activeElement, modal.controls[0]);

  modal.classList.remove("show");
  manager.sync();
  assert.equal(doc.activeElement, opener);
});

test("Tab and Shift+Tab wrap within the active modal", () => {
  const doc = new FakeDocument();
  const modal = createModal(doc, 3);
  modal.classList.add("show");
  const manager = createModalFocusManager(doc);
  manager.start();

  modal.controls[2].focus();
  const forward = tab(doc);
  assert.equal(forward.prevented, true);
  assert.equal(doc.activeElement, modal.controls[0]);

  const backward = tab(doc, true);
  assert.equal(backward.prevented, true);
  assert.equal(doc.activeElement, modal.controls[2]);
});

test("Tab moves from a non-tabbable focused node to the first control", () => {
  const doc = new FakeDocument();
  const modal = createModal(doc);
  modal.classList.add("show");
  const manager = createModalFocusManager(doc);
  manager.start();

  modal.controls[1].tabIndex = -1;
  modal.controls[1].focus();
  const event = tab(doc);
  assert.equal(event.prevented, true);
  assert.equal(doc.activeElement, modal.controls[0]);
});

test("focus that escapes is redirected into the active modal", () => {
  const doc = new FakeDocument();
  const outside = new FakeElement(doc, { focusable: true });
  const modal = createModal(doc);
  modal.classList.add("show");
  const manager = createModalFocusManager(doc);
  manager.start();

  outside.focus();
  assert.equal(doc.activeElement, modal.controls[0]);
});

test("closing a nested modal restores focus inside its parent", () => {
  const doc = new FakeDocument();
  const outerOpener = new FakeElement(doc, { focusable: true });
  const parent = createModal(doc);
  const child = createModal(doc);
  const manager = createModalFocusManager(doc);
  manager.start();

  outerOpener.focus();
  parent.classList.add("show");
  manager.sync();

  parent.controls[1].focus();
  child.classList.add("show");
  manager.sync();
  assert.equal(doc.activeElement, child.controls[0]);

  child.classList.remove("show");
  manager.sync();
  assert.equal(doc.activeElement, parent.controls[1]);

  parent.classList.remove("show");
  manager.sync();
  assert.equal(doc.activeElement, outerOpener);
});

test("replacing a modal preserves the original opener", () => {
  const doc = new FakeDocument();
  const outerOpener = new FakeElement(doc, { focusable: true });
  const first = createModal(doc);
  const second = createModal(doc);
  const manager = createModalFocusManager(doc);
  manager.start();

  outerOpener.focus();
  first.classList.add("show");
  manager.sync();
  first.classList.remove("show");
  second.classList.add("show");
  manager.sync();

  second.classList.remove("show");
  manager.sync();
  assert.equal(doc.activeElement, outerOpener);
});

test("closing both stacked modals skips hidden dialog controls", () => {
  const doc = new FakeDocument();
  const outerOpener = new FakeElement(doc, { focusable: true });
  const parent = createModal(doc);
  const child = createModal(doc);
  const manager = createModalFocusManager(doc);
  manager.start();

  outerOpener.focus();
  parent.classList.add("show");
  manager.sync();
  parent.controls[0].focus();
  child.classList.add("show");
  manager.sync();

  child.classList.remove("show");
  parent.classList.remove("show");
  manager.sync();
  assert.equal(doc.activeElement, outerOpener);
});
