import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "../../../lib/api.js";
import {
  currentFeatureId,
  openCaseConfirmation,
  openFeature,
  refreshStatus,
  toast,
} from "../../../lib/compatBridge.js";
import { escapeHtml } from "../../../lib/html.js";
import { deletePlan, editorBody, moveStep, reviewLine } from "../lib/caseEditor.js";
import { prioLabel } from "../lib/testCases.js";

const callWindow = (name, ...args) => (typeof window[name] === "function" ? window[name](...args) : undefined);

const BLANK = { title: "", type: "functional", prio: "Medium", pre: "", tags: "" };

/**
 * The test case editor dialog and case delete (was editCase / renderSteps /
 * saveCase in 04-test-cases.js and the case CRUD in 07-library-and-crud.js).
 * Registered while mounted:
 *   window.editCase(cid)                       — workspace / Test Cases / Test Cycles
 *   window.openNewCase(featureId)              — "+ New test case" on Test Cases
 *   window.openNewCaseInCycle(featureId, cycleId) — Test Cycles
 *   window.requestDeleteCase(cid, known?)      — row Delete buttons and the editor
 *
 * session: { id, feature_id, cycle_id, shared_with_features } for the open case
 * msg: null | { kind: "ok" | "err" | "text", text }
 */
export default function useCaseEditor() {
  const [show, setShow] = useState(false);
  const [heading, setHeading] = useState("Edit test case");
  const [form, setForm] = useState(BLANK);
  const [steps, setSteps] = useState([]);
  const [warn, setWarn] = useState("");
  const [msg, setMsg] = useState(null);
  const [canDelete, setCanDelete] = useState(false);
  const [saving, setSaving] = useState(false);
  const [drag, setDrag] = useState({ from: null, over: null });
  const session = useRef({ id: null, steps: [] });
  const known = useRef(null);
  const timer = useRef(null);
  useEffect(() => () => clearTimeout(timer.current), []);

  const openWith = (s, head, f, st, warning, deletable) => {
    session.current = s;
    setHeading(head);
    setForm(f);
    setSteps(st);
    setWarn(warning);
    setCanDelete(deletable);
    setMsg(null);
    setShow(true);
  };

  const openNew = useCallback((featureId) => {
    openWith(
      { id: null, feature_id: featureId, shared_with_features: 0 },
      "Create test case",
      BLANK,
      [{ action: "", expected: "" }],
      "The testcase will be linked to the selected feature.",
      false,
    );
  }, []);

  const openNewInCycle = useCallback((featureId, cycleId) => {
    openWith(
      { id: null, feature_id: featureId, cycle_id: cycleId, shared_with_features: 0 },
      "Create test case (adds to this cycle)",
      { ...BLANK, tags: "from-test-cycle" },
      [{ action: "", expected: "" }],
      "Gets a new project ID, is linked to the selected feature, tagged “from-test-cycle”, and added to this cycle.",
      false,
    );
  }, []);

  const requestDelete = useCallback(async (cid, knownCase) => {
    let c = knownCase;
    try {
      if (!c) c = await api("/api/test-cases/" + cid);
    } catch (e) {
      toast(e.message, true);
      return;
    }
    // In scope: the Test Cases feature filter, else the open feature.
    const casesView = document.getElementById("view-cases");
    const scopedFeature =
      casesView && !casesView.hidden ? (document.getElementById("tc-feat") || {}).value || "" : currentFeatureId() || "";
    const plan = deletePlan(c, scopedFeature);
    const refreshAfterDelete = () => {
      setShow(false);
      callWindow("loadCases");
      const fid = currentFeatureId();
      if (fid) openFeature(fid);
    };
    if (plan.scoped) {
      openCaseConfirmation({
        title: plan.title,
        copy: plan.copy,
        summary: `<b>${escapeHtml(c.display_id || "")} ${escapeHtml(c.title)}</b><div class="muted" style="margin-top:6px">${plan.origin} · linked to ${plan.links} feature${plan.links === 1 ? "" : "s"}</div>`,
        confirmLabel: plan.confirmLabel,
        onConfirm: async () => {
          await api(`/api/features/${scopedFeature}/test-cases/${cid}`, { method: "DELETE" });
          refreshAfterDelete();
          toast(plan.links > 1 ? "Removed from this feature; other links were preserved" : "Testcase removed");
        },
        secondaryLabel: plan.secondaryLabel,
        onSecondary: plan.secondaryLabel
          ? async () => {
              await api(`/api/test-cases/${cid}?force=true`, { method: "DELETE" });
              refreshAfterDelete();
              toast("Testcase deleted from every feature");
            }
          : null,
      });
      return;
    }
    const n = (c.steps || []).length;
    openCaseConfirmation({
      title: plan.title,
      copy: plan.copy,
      summary: `<b>${escapeHtml(c.title)}</b><div class="muted" style="margin-top:6px">${plan.links} feature link${plan.links === 1 ? "" : "s"} · ${n} step${n === 1 ? "" : "s"}</div>`,
      confirmLabel: plan.confirmLabel,
      danger: true,
      onConfirm: async () => {
        await api(`/api/test-cases/${cid}${plan.links > 1 ? "?force=true" : ""}`, { method: "DELETE" });
        refreshAfterDelete();
        toast("Testcase deleted");
      },
    });
  }, []);

  const editCase = useCallback(async (cid) => {
    try {
      const c = await api("/api/test-cases/" + cid);
      known.current = c;
      openWith(
        { id: cid, shared_with_features: c.shared_with_features || 0 },
        "Edit test case",
        {
          title: c.title,
          type: c.type,
          prio: prioLabel(c.priority),
          pre: c.preconditions || "",
          tags: (c.tags || []).join(", "),
        },
        c.steps.map((s) => ({ id: s.id, action: s.action, expected: s.expected, usage_count: s.usage_count })),
        c.shared_with_features > 1
          ? `Linked to ${c.shared_with_features} features. Testcase field changes appear in every linked feature; shared-step edits also update other cases that use those exact steps.`
          : "",
        true,
      );
    } catch (e) {
      toast(e.message, true);
    }
  }, []);

  useEffect(() => {
    const hooks = {
      editCase: (cid) => editCase(cid),
      openNewCase: (fid) => openNew(fid),
      openNewCaseInCycle: (fid, cyc) => openNewInCycle(fid, cyc),
      requestDeleteCase: (cid, c) => requestDelete(cid, c),
    };
    Object.assign(window, hooks);
    return () => {
      for (const [k, fn] of Object.entries(hooks)) if (window[k] === fn) delete window[k];
    };
  }, [editCase, openNew, openNewInCycle, requestDelete]);

  const save = async (body) => {
    const s = session.current;
    setSaving(true);
    setMsg({ kind: "text", text: "saving…" });
    try {
      if (s.id) {
        const r = await api("/api/test-cases/" + s.id, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
        setMsg({
          kind: "ok",
          text: `Saved ${r.steps} steps${
            r.other_cases_affected_by_step_edits
              ? ` · ${r.other_cases_affected_by_step_edits} other case(s) updated via shared steps`
              : ""
          }`,
        });
      } else {
        const r = await api("/api/test-cases", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ ...body, feature_id: s.feature_id }),
        });
        const created = `Created${r && r.display_id ? ` — ${r.display_id}` : ""}`;
        setMsg({ kind: "ok", text: created });
        if (s.cycle_id && r && r.id) {
          try {
            await api(`/api/test-cycles/${s.cycle_id}/items`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ case_ids: [r.id] }),
            });
          } catch (e) {
            // The case exists; only adding it to the cycle failed (e.g. a duplicate title).
            setMsg({ kind: "err", text: `${created}, but not added to this cycle: ${e.message}` });
          }
        }
      }
      callWindow("loadCases");
      callWindow("loadSteps");
      const fid = currentFeatureId();
      if (fid) openFeature(fid);
      refreshStatus();
      const cycleCard = document.getElementById("cyc-detail-card");
      if (window._cycle && cycleCard && cycleCard.style.display !== "none") callWindow("openCycle", window._cycle);
      // An open case detail row reloads next time it opens.
      if (s.id)
        document.querySelectorAll(`[data-case-detail="${s.id}"]`).forEach((x) => {
          x.dataset.loaded = "";
        });
      timer.current = setTimeout(() => setShow(false), 500);
    } catch (e) {
      setMsg({ kind: "err", text: e.message });
      throw e;
    } finally {
      setSaving(false);
    }
  };

  const review = () => {
    const body = editorBody(form, steps);
    if (!body.title) {
      setMsg({ kind: "err", text: "Title is required." });
      return;
    }
    const s = session.current;
    openCaseConfirmation({
      title: s.id ? "Confirm testcase update" : "Confirm new testcase",
      copy: s.id ? `Review the fields before updating “${body.title}”.` : `Create “${body.title}” in the selected feature.`,
      summary: `<div><b>${escapeHtml(body.title)}</b></div><div class="muted" style="margin-top:6px">${escapeHtml(reviewLine(body, s.shared_with_features))}</div>`,
      confirmLabel: s.id ? "Update testcase" : "Create testcase",
      onConfirm: () => save(body),
    });
  };

  // ---- steps: edit, add, remove, drag to reorder ----
  const setStep = (i, field, value) => setSteps((st) => st.map((x, j) => (j === i ? { ...x, [field]: value } : x)));
  const addStep = () => setSteps((st) => [...st, { action: "", expected: "" }]);
  const removeStep = (i) => setSteps((st) => st.filter((_, j) => j !== i));
  const dragStart = (i, e) => {
    setDrag({ from: i, over: null });
    e.dataTransfer.effectAllowed = "move";
  };
  const dragOver = (i, e) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
    setDrag((d) => ({ ...d, over: i }));
  };
  const dragLeave = (i) => setDrag((d) => (d.over === i ? { ...d, over: null } : d));
  const dragEnd = () => setDrag({ from: null, over: null });
  const drop = (i, e) => {
    e.preventDefault();
    const from = drag.from;
    setDrag({ from: null, over: null });
    if (from !== null && from !== i) setSteps((st) => moveStep(st, from, i));
  };

  return {
    show,
    heading,
    form,
    setField: (k, v) => setForm((f) => ({ ...f, [k]: v })),
    steps,
    warn,
    msg,
    canDelete,
    saving,
    drag,
    close: () => setShow(false),
    review,
    deleteCase: () => requestDelete(session.current.id, known.current),
    setStep,
    addStep,
    removeStep,
    dragStart,
    dragOver,
    dragLeave,
    dragEnd,
    drop,
  };
}
