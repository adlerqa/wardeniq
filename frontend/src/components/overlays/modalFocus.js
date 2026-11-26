const FOCUSABLE_SELECTOR = [
  "a[href]",
  "area[href]",
  "button:not([disabled])",
  "input:not([disabled]):not([type=\"hidden\"])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  "iframe",
  "object",
  "embed",
  "[contenteditable]:not([contenteditable=\"false\"])",
  "[tabindex]:not([tabindex=\"-1\"])",
].join(",");

function isVisible(element, doc) {
  if (
    element.isConnected === false ||
    element.hidden ||
    element.disabled ||
    element.closest?.('[hidden], [aria-hidden="true"], [inert]')
  ) {
    return false;
  }

  const style = doc.defaultView?.getComputedStyle?.(element);
  if (
    style &&
    (style.display === "none" ||
      style.visibility === "hidden" ||
      style.visibility === "collapse")
  ) {
    return false;
  }

  return !element.getClientRects || element.getClientRects().length > 0;
}

function isTabbable(element, doc) {
  return (
    element.matches?.(FOCUSABLE_SELECTOR) &&
    (element.tabIndex >= 0 || element.hasAttribute?.("contenteditable")) &&
    isVisible(element, doc)
  );
}

export function getModalTabbableElements(modal, doc = document) {
  return Array.from(modal.querySelectorAll(FOCUSABLE_SELECTOR)).filter(
    (element) => isTabbable(element, doc),
  );
}

function focusElement(element) {
  if (!element || typeof element.focus !== "function") return false;
  element.focus({ preventScroll: true });
  return true;
}

function canRestore(element, doc) {
  return (
    element !== doc.body &&
    typeof element?.focus === "function" &&
    isVisible(element, doc)
  );
}

export function createModalFocusManager(doc = document) {
  const entries = [];
  let observer;
  let started = false;

  const openModals = () =>
    Array.from(doc.querySelectorAll(".modal.show")).filter(
      (modal) => modal.isConnected !== false,
    );

  const activeEntry = () => entries[entries.length - 1];

  const focusInitial = (modal) => {
    const explicit =
      modal.querySelector("[data-modal-initial-focus]") ||
      modal.querySelector("[autofocus]");
    const initial =
      (explicit && isTabbable(explicit, doc) && explicit) ||
      getModalTabbableElements(modal, doc)[0];

    if (focusElement(initial)) return;

    if (modal.tabIndex < 0) modal.tabIndex = -1;
    focusElement(modal);
  };

  const ensureFocus = () => {
    const entry = activeEntry();
    if (!entry) return;
    if (
      entry.modal === doc.activeElement ||
      entry.modal.contains(doc.activeElement)
    ) {
      return;
    }
    focusInitial(entry.modal);
  };

  const resolveOpener = (removed) => {
    let opener = doc.activeElement;
    for (const entry of [...removed].reverse()) {
      if (
        opener === doc.body ||
        (opener && entry.modal.contains(opener))
      ) {
        opener = entry.opener;
      }
    }
    return opener;
  };

  const sync = () => {
    const opened = openModals();
    const openedSet = new Set(opened);
    const previousTop = activeEntry();
    const removed = entries.filter((entry) => !openedSet.has(entry.modal));
    const removedSet = new Set(removed);
    const retained = entries.filter((entry) => !removedSet.has(entry));
    const known = new Set(retained.map((entry) => entry.modal));
    const added = opened.filter((modal) => !known.has(modal));

    entries.splice(0, entries.length, ...retained);
    const opener = resolveOpener(removed);
    added.forEach((modal) => {
      entries.push({
        modal,
        opener,
      });
    });

    if (added.length) {
      focusInitial(activeEntry().modal);
      return;
    }

    if (previousTop && removedSet.has(previousTop)) {
      const opener = [...removed]
        .reverse()
        .map((entry) => entry.opener)
        .find((candidate) => canRestore(candidate, doc));

      if (opener && focusElement(opener)) return;
    }

    ensureFocus();
  };

  const onKeyDown = (event) => {
    if (event.key !== "Tab") return;
    const entry = activeEntry();
    if (!entry) return;

    const tabbable = getModalTabbableElements(entry.modal, doc);
    if (!tabbable.length) {
      event.preventDefault();
      focusInitial(entry.modal);
      return;
    }

    const first = tabbable[0];
    const last = tabbable[tabbable.length - 1];
    const currentIndex = tabbable.indexOf(doc.activeElement);

    if (event.shiftKey && currentIndex <= 0) {
      event.preventDefault();
      focusElement(last);
    } else if (!event.shiftKey && (currentIndex < 0 || currentIndex === tabbable.length - 1)) {
      event.preventDefault();
      focusElement(first);
    }
  };

  const onFocusIn = () => ensureFocus();

  const start = () => {
    if (started) return;
    started = true;
    doc.addEventListener("keydown", onKeyDown, true);
    doc.addEventListener("focusin", onFocusIn, true);

    const MutationObserverClass = doc.defaultView?.MutationObserver;
    if (MutationObserverClass) {
      observer = new MutationObserverClass(sync);
      observer.observe(doc.body, {
        attributes: true,
        attributeFilter: ["class"],
        childList: true,
        subtree: true,
      });
    }

    sync();
  };

  const destroy = () => {
    if (!started) return;
    started = false;
    observer?.disconnect();
    doc.removeEventListener("keydown", onKeyDown, true);
    doc.removeEventListener("focusin", onFocusIn, true);
    entries.splice(0, entries.length);
  };

  return { activeEntry, destroy, start, sync };
}

export function installModalFocusManager(doc = document) {
  const manager = createModalFocusManager(doc);
  manager.start();
  return manager;
}
