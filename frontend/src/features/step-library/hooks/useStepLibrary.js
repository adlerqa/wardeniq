import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "../../../lib/api.js";
import { openCaseInFeature, toast } from "../../../lib/compatBridge.js";
import {
  MSG_ACTION_REQUIRED,
  blockedDeleteMessage,
  composeAction,
  editFields,
  updatedMessage,
} from "../lib/steps.js";

const CLOSED_MODAL = {
  open: false,
  mode: "create",
  id: null,
  heading: "Create Step",
  prefix: "Given",
  action: "",
  expected: "",
  warn: "",
  saving: false,
};

/**
 * State and actions for the Step Library: list, filters, detail pane and the
 * create / edit dialog. navigateTo("steps") in 00-core.js and the test-case
 * editor (04-test-cases.js) call window.loadSteps(); this hook registers it
 * while mounted.
 */
export default function useStepLibrary() {
  const [steps, setSteps] = useState([]);
  const stepsRef = useRef([]);
  const [status, setStatus] = useState("idle");
  const [error, setError] = useState("");
  const [filters, setFilters] = useState({ q: "", type: "", usage: "" });
  const [selectedId, setSelectedId] = useState(null);
  const selectedRef = useRef(null);
  const [detail, setDetail] = useState({ status: "idle", cases: [], error: "", title: "Used in cases (0)" });
  const [modal, setModal] = useState(CLOSED_MODAL);
  const modalRef = useRef(CLOSED_MODAL);
  const mounted = useRef(false);
  const seq = useRef({ list: 0, detail: 0 });

  const updateModal = useCallback((change) => {
    modalRef.current = { ...modalRef.current, ...change };
    if (mounted.current) setModal(modalRef.current);
  }, []);

  const select = useCallback((id) => {
    selectedRef.current = id;
    setSelectedId(id);
  }, []);

  const loadSteps = useCallback(async () => {
    const my = ++seq.current.list;
    const current = () => mounted.current && my === seq.current.list;
    setStatus("loading");
    try {
      const r = await api("/api/steps?limit=1000");
      if (!current()) return;
      stepsRef.current = r.steps || [];
      setSteps(stepsRef.current);
      setStatus("ready");
    } catch (e) {
      if (!current()) return;
      setError(e.message);
      setStatus("error");
    }
  }, []);

  const showDetails = useCallback(async (id) => {
    if (!stepsRef.current.some((s) => s.id === id)) return;
    const my = ++seq.current.detail;
    setDetail((d) => ({ ...d, status: "loading" }));
    try {
      const res = await api(`/api/test-cases?step_id=${id}&limit=200`);
      if (!mounted.current || my !== seq.current.detail) return;
      const cases = res.items || [];
      setDetail({ status: "ready", cases, error: "", title: `Used in Cases (${cases.length})` });
    } catch (e) {
      if (!mounted.current || my !== seq.current.detail) return;
      setDetail((d) => ({ ...d, status: "error", error: e.message }));
    }
  }, []);

  useEffect(() => {
    mounted.current = true;
    const hook = () => loadSteps();
    window.loadSteps = hook;
    return () => {
      mounted.current = false;
      if (window.loadSteps === hook) delete window.loadSteps;
    };
  }, [loadSteps]);

  const selectRow = (id) => {
    select(id);
    showDetails(id);
  };
  const closeDetails = () => select(null);

  const openCreate = () =>
    updateModal({ ...CLOSED_MODAL, open: true });
  const openEdit = (step) =>
    updateModal({ ...CLOSED_MODAL, ...editFields(step), open: true, mode: "edit", id: step.id, heading: "Edit Step" });
  const closeModal = () => updateModal({ open: false });

  const save = async () => {
    const m = modalRef.current;
    const raw = m.action.trim();
    if (!raw) {
      toast(MSG_ACTION_REQUIRED, true);
      return;
    }
    const body = { action: composeAction(m.prefix, raw), expected: m.expected.trim() };
    updateModal({ saving: true });
    try {
      if (m.mode === "create") {
        await api("/api/steps", { method: "POST", json: body });
        toast("Step created ✓");
      } else {
        const r = await api(`/api/steps/${m.id}`, { method: "PATCH", json: body });
        toast(updatedMessage(r.affected_cases));
        if (selectedRef.current === m.id) setTimeout(() => showDetails(m.id), 200);
      }
      updateModal({ open: false });
      loadSteps();
    } catch (e) {
      toast(e.message, true);
    } finally {
      updateModal({ saving: false });
    }
  };

  const remove = async (step) => {
    if (step.used_in_cases > 0) {
      toast(blockedDeleteMessage(step.used_in_cases), true);
      return;
    }
    try {
      const r = await api(`/api/steps/${step.id}`, { method: "DELETE" });
      if (r.deleted) {
        if (selectedRef.current === step.id) select(null);
        loadSteps();
        toast("Step deleted");
      } else {
        toast(r.reason, true);
      }
    } catch (e) {
      toast(e.message, true);
    }
  };

  return {
    steps,
    status,
    error,
    filters,
    setFilters: (change) => setFilters((f) => ({ ...f, ...change })),
    selectedId,
    selectRow,
    closeDetails,
    detail,
    openCase: openCaseInFeature,
    modal,
    setModalField: (field, value) => updateModal({ [field]: value }),
    openCreate,
    openEdit,
    closeModal,
    save,
    remove,
  };
}
