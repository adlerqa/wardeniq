import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "../../../lib/api.js";
import { currentFeatureId, currentFeatureName, openFeature, toast, uiConfirm } from "../../../lib/compatBridge.js";
import { downloadFeatureExport } from "../lib/caseExport.js";
import { RESULT_OPTIONS } from "../lib/testCases.js";

const RESULT_LABELS = Object.fromEntries(RESULT_OPTIONS);
const plural = (n, w) => `${n} ${w}${n === 1 ? "" : "s"}`;

/**
 * Row behaviour of a test case list (was viewCase / setCaseResult in 04 and
 * the selection / bulk actions in 03): one open detail at a time (loaded once
 * per list load), the result select per row, ticked rows and the bulk actions.
 * Everything resets when the list reloads (`seq` changes).
 *
 * opts.feature()  — the feature the list is scoped to ("" for none): exports
 *                   need one; deletes remove the case from it rather than everywhere
 * opts.reload()   — reload the list after a bulk delete
 */
export default function useCaseList(items, seq, opts) {
  const [selected, setSelected] = useState(() => new Set());
  const [open, setOpen] = useState(null);
  const [details, setDetails] = useState({});
  const [results, setResults] = useState({}); // id → { value, saved, cls, busy }
  const optsRef = useRef(opts);
  optsRef.current = opts;

  useEffect(() => {
    setSelected(new Set());
    setOpen(null);
    setDetails({});
    setResults({});
  }, [seq]);

  const resultOf = (c) => {
    const status = c.execution_status || "untested";
    return results[c.id] || { value: status, saved: status, cls: `result-select needs-editor ${status}`, busy: false };
  };
  const patchResult = (id, patch, base) =>
    setResults((r) => ({ ...r, [id]: { ...(r[id] || base), ...patch } }));

  const toggleDetail = useCallback(
    async (id) => {
      if (open === id) {
        setOpen(null);
        return;
      }
      setOpen(id);
      if (details[id] && details[id].status === "ready") return;
      setDetails((d) => ({ ...d, [id]: { status: "loading" } }));
      try {
        const c = await api("/api/test-cases/" + id);
        setDetails((d) => ({ ...d, [id]: { status: "ready", data: c } }));
      } catch (e) {
        setDetails((d) => ({ ...d, [id]: { status: "error", error: e.message } }));
      }
    },
    [open, details],
  );

  const setResult = async (c, status) => {
    const base = resultOf(c);
    patchResult(c.id, { value: status, busy: true }, base);
    try {
      await api(`/api/test-cases/${c.id}/execution`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status }),
      });
      patchResult(c.id, { saved: status, cls: `result-select ${status}`, busy: false }, base);
      toast(`Marked ${RESULT_LABELS[status].toLowerCase()}`);
    } catch (e) {
      patchResult(c.id, { value: base.saved, busy: false }, base);
      toast(e.message, true);
    }
  };

  const toggle = (id, on) =>
    setSelected((s) => {
      const next = new Set(s);
      if (on) next.add(id);
      else next.delete(id);
      return next;
    });
  const toggleAll = (on) => setSelected(on ? new Set(items.map((c) => c.id)) : new Set());
  const selectedIds = () => items.filter((c) => selected.has(c.id)).map((c) => c.id);

  const bulkSetResult = async (status) => {
    const ids = selectedIds();
    if (!ids.length) {
      toast("Select test cases first", true);
      return;
    }
    try {
      await Promise.all(
        ids.map((id) =>
          api(`/api/test-cases/${id}/execution`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ status }),
          }),
        ),
      );
      setResults((r) => {
        const next = { ...r };
        for (const id of ids)
          next[id] = { value: status, saved: status, cls: `result-select needs-editor ${status}`, busy: false };
        return next;
      });
      toast(`${plural(ids.length, "test case")} marked ${RESULT_LABELS[status].toLowerCase()}`);
    } catch (e) {
      toast(e.message, true);
    }
  };

  const bulkExport = async (format = "pdf") => {
    const ids = selectedIds();
    const featureId = optsRef.current.feature();
    if (!featureId) {
      toast("Choose one feature before exporting selected test cases", true);
      return;
    }
    try {
      await downloadFeatureExport(featureId, format, ids, currentFeatureName());
      toast(ids.length ? "Selected test cases exported" : "All feature test cases exported");
    } catch (e) {
      toast(e.message, true);
    }
  };

  const bulkDelete = async () => {
    const ids = selectedIds();
    if (!ids.length) {
      toast("Select test cases first", true);
      return;
    }
    if (
      !(await uiConfirm(
        `Delete ${plural(ids.length, "selected test case")}? Shared test cases are only removed from the current feature when a feature is in context.`,
        "Delete Test Cases",
        "Delete",
        true,
      ))
    )
      return;
    const scoped = optsRef.current.feature();
    try {
      for (const id of ids) {
        if (scoped) await api(`/api/features/${scoped}/test-cases/${id}`, { method: "DELETE" });
        else await api(`/api/test-cases/${id}`, { method: "DELETE" });
      }
      toast(`${plural(ids.length, "selected test case")} removed`);
      optsRef.current.reload();
      const fid = currentFeatureId();
      if (fid) openFeature(fid);
    } catch (e) {
      toast(e.message, true);
    }
  };

  return {
    selected,
    open,
    details,
    resultOf,
    toggleDetail,
    closeDetail: () => setOpen(null),
    setResult,
    toggle,
    toggleAll,
    count: items.filter((c) => selected.has(c.id)).length,
    bulkSetResult,
    bulkExport,
    bulkDelete,
  };
}
