/**
 * Pure helpers for SelectDropdownLayer (no React, no DOM globals) so they can be
 * unit-tested with `node --test`.
 */

/** A <select> the custom dropdown takes over: single-value, enabled, not opted out. */
export function isEnhanceableSelect(el) {
  return Boolean(
    el &&
      el.tagName === "SELECT" &&
      !el.multiple &&
      !(el.size > 1) &&
      !el.disabled &&
      !(el.dataset && "nativeSelect" in el.dataset),
  );
}

/**
 * Flatten a <select>'s options (and optgroups) into render rows.
 * Option rows carry `index` = the option's index in select.options.
 */
export function readSelectItems(select) {
  const rows = [];
  const pushOption = (opt, groupDisabled) => {
    rows.push({
      kind: "option",
      index: opt.index,
      value: opt.value,
      label: (opt.label || opt.textContent || "").trim(),
      disabled: Boolean(opt.disabled || groupDisabled),
      selected: opt.index === select.selectedIndex,
    });
  };
  for (const child of Array.from(select.children)) {
    if (child.tagName === "OPTGROUP") {
      rows.push({ kind: "group", label: child.label || "" });
      for (const opt of Array.from(child.children)) {
        if (opt.tagName === "OPTION") pushOption(opt, child.disabled);
      }
    } else if (child.tagName === "OPTION") {
      pushOption(child, false);
    }
  }
  return rows;
}

/**
 * Where the panel goes: directly below the field, exactly as wide as it.
 * Only when there is clearly not enough room below (and more room above) does
 * it flip above, so it never renders off-screen.
 */
export function computeDropdownPlacement(
  rect,
  viewportHeight,
  { gap = 4, margin = 8, maxHeight = 320, minHeight = 160 } = {},
) {
  const spaceBelow = viewportHeight - rect.bottom - gap - margin;
  const spaceAbove = rect.top - gap - margin;
  const below = spaceBelow >= minHeight || spaceBelow >= spaceAbove;
  const available = below ? spaceBelow : spaceAbove;
  return {
    placement: below ? "bottom" : "top",
    left: rect.left,
    width: rect.width,
    top: below ? rect.bottom + gap : null,
    bottom: below ? null : viewportHeight - rect.top + gap,
    maxHeight: Math.max(80, Math.min(maxHeight, available)),
  };
}

/** Next enabled option row index from `from` moving by `step` (wraps = false). */
export function nextEnabledRow(rows, from, step) {
  let i = from;
  for (let n = 0; n < rows.length; n += 1) {
    i += step;
    if (i < 0 || i >= rows.length) return from;
    if (rows[i].kind === "option" && !rows[i].disabled) return i;
  }
  return from;
}

/** First enabled option row whose label starts with `query` (case-insensitive), searching after `from`. */
export function typeaheadRow(rows, from, query) {
  const q = query.toLowerCase();
  const n = rows.length;
  for (let k = 1; k <= n; k += 1) {
    const i = (from + k + n) % n;
    const r = rows[i];
    if (r.kind === "option" && !r.disabled && r.label.toLowerCase().startsWith(q)) return i;
  }
  return -1;
}
