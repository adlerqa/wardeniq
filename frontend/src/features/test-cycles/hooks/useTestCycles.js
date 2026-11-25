import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "../../../lib/api.js";
import { escapeHtml } from "../../../lib/html.js";
import {
  currentProjectId,
  loadProjects,
  openCaseConfirmation,
  openInfoDialog,
  openNewCaseInCycle,
  setCurrentProject,
  toast,
  uiConfirm,
  uiPrompt,
} from "../../../lib/compatBridge.js";
import { availableCases, itemPatch, scheduleChange } from "../lib/cycles.js";

const jsonReq = (method, body) => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

/**
 * Test Cycles screen (was the Test Cycles half of 08-code-analysis-and-cycles.js).
 *
 * Registered while mounted (nothing loads on mount):
 *   window.initTestCycles() — navigateTo("testcycles")
 *   window.loadCycles()     — after "create cycle from selection" (Code Analysis), 02
 *   window.openCycle(id)    — after a case is added to a cycle from the editor (04)
 * window._cycle is the open cycle's id; 04 reopens it after saving a case
 * while the detail card is shown.
 */
export default function useTestCycles() {
  const [projects, setProjects] = useState([]);
  const [pid, setPid] = useState("");
  const [name, setName] = useState("");
  const [list, setList] = useState({ status: "idle", cycles: [], error: "" });
  const [templates, setTemplates] = useState(null);
  const [detail, setDetail] = useState(null); // cycle shown in the detail card
  const [shown, setShown] = useState(false);
  const [edit, setEdit] = useState({ itemId: null, draft: null });
  const [renderSeq, setRenderSeq] = useState(0); // the card scrolls into view on every redraw
  const [overlay, setOverlay] = useState(null); // { kind: "chooser" | "existing" | "feature", cid, ... }
  const pidRef = useRef("");
  const detailRef = useRef(null);
  const listSeq = useRef(0);

  const projectId = () => pidRef.current || currentProjectId() || "";

  const show = useCallback((c, resetEdit = true) => {
    detailRef.current = c;
    setDetail(c);
    setShown(true);
    if (resetEdit) setEdit({ itemId: null, draft: null });
    setRenderSeq((n) => n + 1);
  }, []);

  const loadCycles = useCallback(async () => {
    const p = projectId();
    if (!p) return;
    const my = ++listSeq.current;
    setList((l) => ({ ...l, status: "loading" }));
    try {
      const r = await api(`/api/projects/${p}/test-cycles`);
      if (my === listSeq.current) setList({ status: "ready", cycles: r.cycles, error: "" });
    } catch (e) {
      if (my === listSeq.current) setList({ status: "error", cycles: [], error: e.message });
    }
  }, []);

  const loadTemplates = useCallback(async () => {
    const p = projectId();
    if (!p) return;
    try {
      const r = await api(`/api/projects/${p}/cycle-templates`);
      setTemplates(r.templates || []);
    } catch {
      /* keep what is shown */
    }
  }, []);

  const openCycle = useCallback(
    async (id) => {
      try {
        const c = await api("/api/test-cycles/" + id);
        window._cycle = id;
        show(c);
      } catch (e) {
        toast(e.message, true);
      }
    },
    [show],
  );

  const initTestCycles = useCallback(async () => {
    const list = await loadProjects();
    setProjects(list);
    const p = currentProjectId() || "";
    pidRef.current = p;
    setPid(p);
    loadCycles();
    loadTemplates();
  }, [loadCycles, loadTemplates]);

  useEffect(() => {
    const hooks = {
      initTestCycles: () => initTestCycles(),
      loadCycles: () => loadCycles(),
      openCycle: (id) => openCycle(id),
    };
    Object.assign(window, hooks);
    return () => {
      for (const [k, fn] of Object.entries(hooks)) if (window[k] === fn) delete window[k];
    };
  }, [initTestCycles, loadCycles, openCycle]);

  const changeProject = (p) => {
    pidRef.current = p;
    setPid(p);
    setCurrentProject(p);
    loadCycles();
    loadTemplates();
  };

  const refresh = () => {
    loadCycles();
    loadTemplates();
  };

  const createCycle = async () => {
    const p = projectId();
    if (!p) {
      toast("Select a project first", true);
      return;
    }
    // A name is required (a blank one used to become "Cycle <date>" and collide).
    const n = name.trim();
    if (!n) {
      toast("Enter a cycle name", true);
      return;
    }
    try {
      const r = await api("/api/test-cycles", jsonReq("POST", { project_id: p, name: n, case_ids: [] }));
      setName("");
      toast("Cycle created — add the test cases you want to retest");
      loadCycles();
      if (r && r.id) openCycle(r.id);
    } catch (e) {
      toast(e.message || "Could not create cycle", true);
    }
  };

  // ---- templates ----
  const saveAsTemplate = async (cid) => {
    const n0 = await uiPrompt("Save cycle as template", "Template name", (detailRef.current || {}).name || "");
    if (n0 == null) return;
    const n = n0.trim();
    if (!n) {
      toast("Name required", true);
      return;
    }
    try {
      await api(`/api/test-cycles/${cid}/save-template`, jsonReq("POST", { name: n }));
      toast("Template saved");
      loadTemplates();
    } catch (e) {
      toast(e.message, true);
    }
  };

  const newFromTemplate = async (tid) => {
    const n0 = await uiPrompt("New cycle from template", "Cycle name", `Cycle ${new Date().toLocaleDateString()}`);
    if (n0 == null) return;
    const n = n0.trim();
    if (!n) {
      toast("Name required", true);
      return;
    }
    try {
      const r = await api(`/api/cycle-templates/${tid}/create-cycle`, jsonReq("POST", { name: n }));
      toast("Cycle created from template");
      loadCycles();
      if (r && r.id) openCycle(r.id);
    } catch (e) {
      toast(e.message, true);
    }
  };

  const deleteTemplate = async (tid) => {
    if (!(await uiConfirm("Delete this template? Existing cycles are not affected.", "Delete template", "Delete", true)))
      return;
    try {
      await api(`/api/cycle-templates/${tid}`, { method: "DELETE" });
      toast("Template deleted");
      loadTemplates();
    } catch (e) {
      toast(e.message, true);
    }
  };

  // ---- cycle detail ----
  const patchCycle = async (cid, body, message, after) => {
    try {
      const c = await api("/api/test-cycles/" + cid, jsonReq("PATCH", body));
      show(c, false);
      after?.();
      toast(message);
    } catch (e) {
      toast(e.message, true);
    }
  };

  const schedule = (cid, field, value) => {
    const c0 = detailRef.current || {};
    if (scheduleChange(c0, field, value).error) {
      toast("End date can't be before the start date", true);
      show(c0, false);
      return;
    }
    patchCycle(cid, { [field]: value || "" }, value ? "Schedule updated" : "Schedule cleared");
  };

  const editDescription = async (cid) => {
    const d = await uiPrompt("Edit cycle description", "Description", (detailRef.current || {}).description || "");
    if (d == null) return;
    patchCycle(cid, { description: d }, "Description updated");
  };

  const rename = async () => {
    if (!window._cycle) return;
    const cur = (detailRef.current || {}).name || "";
    const n0 = await uiPrompt("Rename test cycle", "Cycle name", cur);
    if (n0 == null) return;
    const n = n0.trim();
    if (!n || n === cur) return;
    // (as before, the list is reloaded before the toast)
    try {
      const c = await api("/api/test-cycles/" + window._cycle, jsonReq("PATCH", { name: n }));
      show(c, false);
      loadCycles();
      toast("Cycle renamed");
    } catch (e) {
      toast(e.message, true);
    }
  };

  const remove = () => {
    const cycle = detailRef.current;
    if (!window._cycle || !cycle) return;
    const counts = cycle.counts || {};
    openCaseConfirmation({
      title: "Delete test cycle",
      copy: `Delete “${cycle.name}”? This removes its saved execution state and cannot be undone.`,
      summary: `<b>${escapeHtml(cycle.name)}</b><div class="muted" style="margin-top:6px">${cycle.total || 0} cases · ${
        counts.passed || 0
      } passed · ${counts.failed || 0} failed · ${counts.blocked || 0} blocked</div>`,
      confirmLabel: "Delete cycle",
      danger: true,
      onConfirm: async () => {
        await api("/api/test-cycles/" + window._cycle, { method: "DELETE" });
        setShown(false);
        detailRef.current = null;
        setDetail(null);
        setEdit({ itemId: null, draft: null });
        loadCycles();
        toast("Cycle deleted");
      },
    });
  };

  const close = () => setShown(false);

  const showReport = async (id) => {
    let r;
    try {
      r = await api(`/api/test-cycles/${id}/report`);
    } catch (e) {
      toast(e.message, true);
      return;
    }
    const s = r.summary || {};
    const kpi = (v, label) => `\n      <div class="cycle-detail-kpi"><b>${v}</b><span>${label}</span></div>`;
    openInfoDialog({
      title: "Cycle summary",
      copy: "A quick progress snapshot for this saved test cycle.",
      summary: `<div class="cycle-detail-summary" style="margin-top:12px">${kpi(`${s.completion_rate || 0}%`, "Completion")}${kpi(
        `${s.pass_rate || 0}%`,
        "Pass rate",
      )}${kpi(s.passed || 0, "Passed")}${kpi(s.failed || 0, "Failed")}${kpi(s.blocked || 0, "Blocked")}\n    </div>`,
    });
  };

  // ---- item status ----
  const saveItem = async (cid, body) => {
    try {
      await api(`/api/test-cycles/${cid}/items`, jsonReq("PATCH", body));
      const updated = await api(`/api/test-cycles/${cid}`);
      show(updated);
      loadCycles();
      toast("status updated");
    } catch (e) {
      // (the old screen left this failure unreported)
      toast(e.message, true);
    }
  };

  const changeItemStatus = (cid, itemId, status) => {
    const item = ((detailRef.current || {}).items || []).find((x) => x.id === itemId);
    if (!item) {
      toast("Cycle item not found", true);
      return;
    }
    // Failed / blocked open the inline editor for the result, notes and defect link.
    if (status === "failed" || status === "blocked") {
      setEdit({
        itemId,
        draft: { status, actual_result: item.actual_result || "", notes: item.notes || "", defect_link: item.defect_link || "" },
      });
      setRenderSeq((n) => n + 1);
      return;
    }
    saveItem(cid, itemPatch(itemId, status, item));
  };

  const updateDraft = (field, value) => setEdit((e) => ({ ...e, draft: { ...(e.draft || {}), [field]: value } }));
  /** Typing into an editor that is open because of saved details starts editing that item. */
  const beginEdit = (item, field, value) =>
    setEdit({
      itemId: item.id,
      draft: {
        status: item.execution_status,
        actual_result: item.actual_result || "",
        notes: item.notes || "",
        defect_link: item.defect_link || "",
        [field]: value,
      },
    });
  const cancelEdit = () => {
    setEdit({ itemId: null, draft: null });
    setRenderSeq((n) => n + 1);
  };
  const saveEdit = (cid, itemId) => {
    // An editor open because of saved details saves those details unchanged
    // (it used to send empty fields and clear them).
    const item = ((detailRef.current || {}).items || []).find((x) => x.id === itemId) || {};
    const draft = edit.itemId === itemId ? edit.draft || {} : { ...item, status: item.execution_status };
    saveItem(cid, itemPatch(itemId, draft.status || "failed", draft));
  };

  // ---- add cases ----
  const openAddExisting = async (cid) => {
    setOverlay(null);
    const p = (detailRef.current || {}).project_id || currentProjectId();
    if (!p) {
      toast("No project", true);
      return;
    }
    let items;
    try {
      const r = await api(`/api/test-cases?project_id=${encodeURIComponent(p)}&limit=500`);
      items = r.items || [];
    } catch (e) {
      toast(e.message, true);
      return;
    }
    const avail = availableCases(items, detailRef.current);
    if (!avail.length) {
      toast("All project test cases are already in this cycle");
      return;
    }
    setOverlay({ kind: "existing", cid, cases: avail });
  };

  const addExisting = async (cid, ids) => {
    if (!ids.length) {
      toast("Select at least one case", true);
      return;
    }
    try {
      await api(`/api/test-cycles/${cid}/items`, jsonReq("POST", { case_ids: ids }));
      setOverlay(null);
      openCycle(cid);
      loadCycles();
      toast(`${ids.length} case(s) added`);
    } catch (e) {
      toast(e.message, true);
    }
  };

  const openNewCase = async (cid) => {
    setOverlay(null);
    const p = (detailRef.current || {}).project_id || currentProjectId();
    let feats;
    try {
      const r = await api(`/api/features?project_id=${encodeURIComponent(p)}`);
      feats = r.features || [];
    } catch (e) {
      toast(e.message, true);
      return;
    }
    if (!feats.length) {
      toast("Create a feature first — every test case must belong to a feature", true);
      return;
    }
    if (feats.length === 1) {
      openNewCaseInCycle(feats[0].id, cid);
      return;
    }
    setOverlay({ kind: "feature", cid, features: feats });
  };

  const pickFeature = (cid, fid) => {
    setOverlay(null);
    openNewCaseInCycle(fid, cid);
  };

  return {
    projects,
    pid,
    name,
    setName,
    list,
    templates,
    detail,
    shown,
    edit,
    renderSeq,
    overlay,
    changeProject,
    refresh,
    createCycle,
    openCycle,
    saveAsTemplate,
    newFromTemplate,
    deleteTemplate,
    schedule,
    editDescription,
    rename,
    remove,
    close,
    showReport,
    changeItemStatus,
    updateDraft,
    beginEdit,
    cancelEdit,
    saveEdit,
    openChooser: (cid) => setOverlay({ kind: "chooser", cid }),
    closeOverlay: () => setOverlay(null),
    openAddExisting,
    addExisting,
    openNewCase,
    pickFeature,
  };
}
