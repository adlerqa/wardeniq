import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import {
  computeDropdownPlacement,
  isEnhanceableSelect,
  nextEnabledRow,
  readSelectItems,
  typeaheadRow,
} from "./selectDropdownModel.js";

const LISTBOX_ID = "wq-select-dropdown";
const OPEN_KEYS = new Set(["ArrowDown", "ArrowUp", "Enter", " ", "F4"]);

/**
 * App-wide dropdown for native <select> elements.
 *
 * Browsers draw the native option list over the field (macOS) at whatever width
 * the options need. This layer keeps every <select> in the DOM as-is (so legacy
 * controllers, React onChange, labels and existing field styling keep working)
 * but replaces the popup: it opens directly BELOW the field and is exactly as
 * wide as the field. Choosing an option sets select.selectedIndex and fires
 * bubbling `input` + `change` events, which both `el.onchange` handlers and
 * React's onChange receive.
 *
 * Opt out per element with `data-native-select`. Multi-selects, listboxes
 * (size > 1), disabled selects and touch-first devices keep the native picker.
 */
export default function SelectDropdownLayer() {
  const [open, setOpen] = useState(null); // { select, rows, active, pos }
  const openRef = useRef(null);
  const listRef = useRef(null);
  const typeahead = useRef({ text: "", timer: 0 });

  const update = useCallback((next) => {
    openRef.current = next;
    setOpen(next);
  }, []);

  const close = useCallback(
    (refocus) => {
      const cur = openRef.current;
      if (!cur) return;
      cur.select.setAttribute("aria-expanded", "false");
      cur.select.removeAttribute("aria-activedescendant");
      cur.select.removeAttribute("aria-controls");
      update(null);
      if (refocus && cur.select.isConnected) cur.select.focus();
    },
    [update],
  );

  const place = (select) =>
    computeDropdownPlacement(select.getBoundingClientRect(), window.innerHeight);

  const openFor = useCallback(
    (select) => {
      const rows = readSelectItems(select);
      let active = rows.findIndex((r) => r.kind === "option" && r.selected);
      if (active < 0) active = nextEnabledRow(rows, -1, 1);
      select.setAttribute("aria-expanded", "true");
      select.setAttribute("aria-controls", LISTBOX_ID);
      update({ select, rows, active, pos: place(select) });
    },
    [update],
  );

  const choose = useCallback(
    (row) => {
      const cur = openRef.current;
      if (!cur || !row || row.kind !== "option" || row.disabled) return;
      const { select } = cur;
      close(true);
      if (select.selectedIndex !== row.index) {
        select.selectedIndex = row.index;
        select.dispatchEvent(new Event("input", { bubbles: true }));
        select.dispatchEvent(new Event("change", { bubbles: true }));
      }
    },
    [close],
  );

  const setActive = useCallback(
    (active) => {
      const cur = openRef.current;
      if (cur && active !== cur.active) update({ ...cur, active });
    },
    [update],
  );

  useEffect(() => {
    const coarse =
      typeof window.matchMedia === "function" &&
      window.matchMedia("(pointer: coarse)").matches &&
      !window.matchMedia("(any-pointer: fine)").matches;
    if (coarse) return undefined;
    const ta = typeahead.current;

    const onMouseDown = (e) => {
      if (listRef.current && listRef.current.contains(e.target)) return;
      const select = e.target && e.target.closest ? e.target.closest("select") : null;
      const cur = openRef.current;
      if (e.button === 0 && isEnhanceableSelect(select)) {
        e.preventDefault(); // suppress the native popup
        select.focus();
        if (cur && cur.select === select) close(false);
        else openFor(select);
        return;
      }
      if (cur) close(false);
    };

    const onKeyDown = (e) => {
      const cur = openRef.current;
      if (!cur) {
        const select = e.target;
        if (
          isEnhanceableSelect(select) &&
          !e.ctrlKey &&
          !e.metaKey &&
          OPEN_KEYS.has(e.key)
        ) {
          e.preventDefault();
          openFor(select);
        }
        return;
      }
      const { rows, active } = cur;
      const handled = () => {
        e.preventDefault();
        e.stopPropagation();
      };
      switch (e.key) {
        case "ArrowDown":
          handled();
          setActive(nextEnabledRow(rows, active, 1));
          return;
        case "ArrowUp":
          handled();
          if (e.altKey) close(true);
          else setActive(nextEnabledRow(rows, active, -1));
          return;
        case "Home":
          handled();
          setActive(nextEnabledRow(rows, -1, 1));
          return;
        case "End":
          handled();
          setActive(nextEnabledRow(rows, rows.length, -1));
          return;
        case "PageDown":
        case "PageUp": {
          handled();
          let i = active;
          for (let n = 0; n < 8; n += 1) i = nextEnabledRow(rows, i, e.key === "PageDown" ? 1 : -1);
          setActive(i);
          return;
        }
        case "Enter":
          handled();
          choose(rows[active]);
          return;
        case " ":
          if (!typeahead.current.text) {
            handled();
            choose(rows[active]);
            return;
          }
          break;
        case "Escape":
          handled();
          close(true);
          return;
        case "Tab":
          close(false);
          return;
        default:
          break;
      }
      if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) {
        handled();
        const t = typeahead.current;
        clearTimeout(t.timer);
        t.text += e.key;
        t.timer = setTimeout(() => {
          t.text = "";
        }, 600);
        const from = t.text.length > 1 ? active - 1 : active;
        const hit = typeaheadRow(rows, from, t.text);
        if (hit >= 0) setActive(hit);
      }
    };

    const reposition = () => {
      const cur = openRef.current;
      if (!cur) return;
      const r = cur.select.getBoundingClientRect();
      if (!cur.select.isConnected || (r.width === 0 && r.height === 0)) {
        close(false);
        return;
      }
      update({ ...cur, pos: place(cur.select) });
    };

    const onFocusIn = (e) => {
      const cur = openRef.current;
      if (cur && e.target !== cur.select && !(listRef.current && listRef.current.contains(e.target)))
        close(false);
    };

    document.addEventListener("mousedown", onMouseDown, true);
    document.addEventListener("keydown", onKeyDown, true);
    document.addEventListener("focusin", onFocusIn, true);
    window.addEventListener("scroll", reposition, true);
    window.addEventListener("resize", reposition);
    return () => {
      document.removeEventListener("mousedown", onMouseDown, true);
      document.removeEventListener("keydown", onKeyDown, true);
      document.removeEventListener("focusin", onFocusIn, true);
      window.removeEventListener("scroll", reposition, true);
      window.removeEventListener("resize", reposition);
      clearTimeout(ta.timer);
    };
  }, [choose, close, openFor, setActive, update]);

  // Keep the highlighted option visible and announced.
  useLayoutEffect(() => {
    if (!open || !listRef.current) return;
    const el = listRef.current.querySelector(`[data-row="${open.active}"]`);
    if (el) {
      el.scrollIntoView({ block: "nearest" });
      open.select.setAttribute("aria-activedescendant", el.id);
    }
  }, [open]);

  if (!open) return null;
  const { rows, active, pos } = open;
  const label =
    open.select.getAttribute("aria-label") ||
    (open.select.labels && open.select.labels[0] && open.select.labels[0].textContent.trim()) ||
    undefined;

  return createPortal(
    <div
      ref={listRef}
      id={LISTBOX_ID}
      role="listbox"
      aria-label={label}
      data-placement={pos.placement}
      onMouseDown={(e) => e.preventDefault()}
      className="fixed z-[10050] box-border overflow-y-auto overscroll-contain rounded-lg border border-solid border-line bg-panel py-1 text-[13px] text-text shadow-[0_14px_36px_rgba(0,0,0,0.45)]"
      style={{
        left: pos.left,
        width: pos.width,
        top: pos.top ?? undefined,
        bottom: pos.bottom ?? undefined,
        maxHeight: pos.maxHeight,
      }}
    >
      {rows.map((row, i) =>
        row.kind === "group" ? (
          <div
            key={`g${i}`}
            role="presentation"
            className="px-3 pb-1 pt-2 text-[11px] font-semibold uppercase tracking-wide text-muted"
          >
            {row.label}
          </div>
        ) : (
          <div
            key={`o${row.index}`}
            id={`${LISTBOX_ID}-opt-${i}`}
            data-row={i}
            role="option"
            aria-selected={row.selected}
            aria-disabled={row.disabled || undefined}
            title={row.label}
            onMouseEnter={() => !row.disabled && setActive(i)}
            onClick={() => choose(row)}
            className={[
              "mx-1 flex min-h-[32px] cursor-pointer items-center gap-2 rounded-md px-2.5 py-1.5 leading-snug",
              row.disabled ? "cursor-not-allowed opacity-45" : "",
              i === active && !row.disabled ? "bg-panel2" : "",
              row.selected ? "font-medium text-accent2" : "",
            ].join(" ")}
          >
            <span className="min-w-0 flex-1 break-words">{row.label || " "}</span>
            {row.selected && (
              <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" className="shrink-0">
                <path d="m5 12 5 5 9-10" />
              </svg>
            )}
          </div>
        ),
      )}
    </div>,
    document.body,
  );
}
