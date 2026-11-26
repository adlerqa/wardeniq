import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "../../../lib/api.js";
import {
  currentFeatureId,
  currentProjectId,
  openFeature,
  refreshStatus,
  toast,
  usageLogLines,
  watchJob,
} from "../../../lib/compatBridge.js";
import { fmtUsd } from "../../usage/lib/usage.js";
import { jobLogLines } from "../../validator/lib/validator.js";
import {
  DEFAULT_FOCUS,
  FOCUS_TYPES,
  casesLine,
  estimateLength,
  estimateParts,
  filterSummaryLine,
  largestFocusOther,
  rebalanceFocus,
  splitLinks,
} from "../lib/features.js";

const TICKET_HINT =
  "Associate an Epic so PRs auto-link to this feature (ticket → epic → feature). Each Epic maps to one feature only.";

/**
 * The "New feature" page (was showFeatureCreate / #f-go and friends in
 * 03-features-and-usage.js). `fs` is useFeatures(): it owns the page switch
 * and the project the page creates the feature in.
 *
 * Registered while mounted: window.showFeatureCreate().
 *
 * status: null | { kind: "err" | "muted", text } | { kind: "accepted", docs, chunks }
 *       | { kind: "running", stage, line } | { kind: "failed" | "startFailed", text }
 *       | { kind: "done", line, filterLine, warnings, errors }
 * log: null (hidden) | string[]
 */
export default function useFeatureCreate(fs) {
  const [name, setName] = useState("");
  const [ticket, setTicket] = useState({ none: "No Jira ticket", options: [], status: { text: "A linked Jira ticket lets PRs auto-link by branch/title." } });
  const [ticketKey, setTicketKey] = useState("");
  const [matchKey, setMatchKey] = useState("");
  const [text, setText] = useState("");
  const [confluence, setConfluence] = useState("");
  const [figma, setFigma] = useState("");
  const [files, setFiles] = useState([]);
  const [focus, setFocus] = useState(DEFAULT_FOCUS);
  const [estimate, setEstimate] = useState({ cost: "", warning: "" });
  const [status, setStatus] = useState(null);
  const [log, setLog] = useState(null);
  const [busy, setBusy] = useState(false);
  const fileRef = useRef(null);
  const sheetRef = useRef(null);
  const nameRef = useRef(null);
  const timer = useRef(null);
  const focusPrev = useRef(DEFAULT_FOCUS);
  const focusPartner = useRef(null);
  const fsRef = useRef(fs);
  fsRef.current = fs;

  /** The project the feature goes into: the Features screen's project, else the current one. */
  const projectId = () => fsRef.current.projects.cur || currentProjectId() || "";

  // ---- pre-run cost estimate (issue #22): file sizes stand in for extracted text ----
  const inputs = useRef({ text: "", files: [] });
  inputs.current = { text, files };
  const updateEstimate = useCallback(async () => {
    const len = estimateLength(inputs.current.text, inputs.current.files);
    // With no document there is no cost to show, but the call is still made: the
    // server may answer with a warning (a local model on CPU) that belongs before Generate.
    setEstimate({ cost: len ? "Estimating cost…" : "", warning: "" });
    try {
      const r = await api("/api/usage/estimate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text_length: len }),
      });
      setEstimate(estimateParts(r, len, fmtUsd));
    } catch {
      setEstimate({ cost: "", warning: "" });
    }
  }, []);
  const scheduleEstimate = useCallback(() => {
    clearTimeout(timer.current);
    timer.current = setTimeout(updateEstimate, 400);
  }, [updateEstimate]);
  useEffect(() => () => clearTimeout(timer.current), []);

  const loadTicketOptions = useCallback(async (pid) => {
    setTicket({ none: "No Jira epic", options: [], status: { text: TICKET_HINT } });
    setTicketKey("");
    if (!pid) return;
    try {
      const r = await api(`/api/projects/${pid}`);
      const jiraKey = (r.jira_project_key || "").trim();
      if (!jiraKey) {
        setTicket((t) => ({ ...t, status: { text: "No Jira project is linked to this project." } }));
        return;
      }
      setTicket((t) => ({ ...t, status: { text: `Loading available Epics from ${jiraKey}…` } }));
      const issues = await api(`/api/projects/${pid}/jira-issues`);
      const items = issues.issues || [];
      setTicket({
        none: "No Jira epic",
        options: items.map((i) => ({ value: i.key, label: `${i.key} — ${i.summary}` })),
        status: {
          text: items.length
            ? `${items.length} unassociated Epic(s) available from ${jiraKey}`
            : `No unassociated Epics found in ${jiraKey}`,
        },
      });
    } catch (e) {
      setTicket((t) => ({ ...t, status: { err: true, text: e.message } }));
    }
  }, []);

  /** Open a blank page (Confluence / Figma links, the sheet and the mix are kept, as before). */
  const showFeatureCreate = useCallback(async () => {
    fsRef.current.showPage("create");
    setName("");
    setText("");
    setMatchKey("");
    setFiles([]);
    if (fileRef.current) fileRef.current.value = "";
    setStatus(null);
    setLog(null);
    setEstimate({ cost: "", warning: "" });
    inputs.current = { text: "", files: [] };
    scheduleEstimate(); // a "runs on CPU" warning can show before any document is added
    await loadTicketOptions(projectId());
  }, [loadTicketOptions, scheduleEstimate]);

  useEffect(() => {
    const hook = () => showFeatureCreate();
    window.showFeatureCreate = hook;
    return () => {
      if (window.showFeatureCreate === hook) delete window.showFeatureCreate;
    };
  }, [showFeatureCreate]);

  // ---- files: removable one by one (issue #108) by rebuilding the input's FileList ----
  const pickFiles = () => {
    const list = [...(fileRef.current ? fileRef.current.files : [])];
    setFiles(list);
    inputs.current = { ...inputs.current, files: list };
    scheduleEstimate();
  };
  const removeFile = (i) => {
    const input = fileRef.current;
    const dt = new DataTransfer();
    [...input.files].forEach((f, idx) => {
      if (idx !== i) dt.items.add(f);
    });
    input.files = dt.files;
    pickFiles();
  };
  const changeText = (v) => {
    setText(v);
    inputs.current = { ...inputs.current, text: v };
    scheduleEstimate();
  };

  // ---- test type mix: one drag keeps taking from / giving to the same partner ----
  const focusStart = (t) => {
    focusPartner.current = largestFocusOther(t, focusPrev.current);
  };
  const focusFocus = (t) => {
    if (!focusPartner.current) focusStart(t);
  };
  const focusInput = (t, raw) => {
    const { values, partner } = rebalanceFocus(focusPrev.current, t, parseInt(raw) || 0, focusPartner.current);
    focusPartner.current = partner;
    focusPrev.current = values;
    setFocus(values);
  };
  const focusEnd = () => {
    focusPartner.current = null;
  };

  const sheetTemplate = (e) => {
    e.preventDefault();
    // The template endpoint ignores the feature id; any will do.
    window.location.href = `/api/features/${currentFeatureId() || "_"}/tests/import/template?format=xlsx`;
  };

  const watchGen = (jobId, fid) => {
    if (!jobId) {
      setBusy(false);
      return;
    }
    watchJob(jobId, (j) => {
      const res = j.result || {};
      const lines = jobLogLines(j, usageLogLines);
      setLog(lines.length ? lines : null);
      if (j.status === "running") setStatus({ kind: "running", stage: j.stage, line: casesLine(res) });
      else if (j.status === "failed") setStatus({ kind: "failed", text: j.error || "unknown error" });
      else
        setStatus({
          kind: "done",
          line: casesLine(res),
          filterLine: filterSummaryLine(res),
          warnings: res.warnings || [],
          errors: res.errors || [],
        });
      if (j.status === "running") return;
      setBusy(false);
      fsRef.current.loadFeatures();
      refreshStatus();
      if (j.status === "failed") toast("Generation failed: " + (j.error || "unknown error"), true);
      else toast(`Generation complete — ${res.cases_new || 0} new, ${res.cases_reused || 0} reused test cases.`);
      if (fid) openFeature(fid);
    });
  };

  const generate = async () => {
    const featureName = name.trim();
    const fail = (msg, focusEl) => {
      setStatus({ kind: "err", text: msg });
      toast(msg, true);
      if (focusEl) focusEl.focus();
    };
    if (!featureName) {
      fail("Enter a feature name to continue.", nameRef.current);
      return;
    }
    const pid = projectId();
    const conflList = splitLinks(confluence);
    const figmaList = splitLinks(figma);
    const chosen = [...(fileRef.current ? fileRef.current.files : [])];
    if (!chosen.length && !text.trim() && !conflList.length && !figmaList.length) {
      fail("Add at least one source — upload a document, paste requirement text, or add a Confluence/Figma link.");
      return;
    }
    const fd = new FormData();
    fd.append("name", featureName);
    fd.append("project_id", pid);
    fd.append("key", ticketKey.trim());
    fd.append("match_key", matchKey.trim());
    for (const f of chosen) fd.append("files", f);
    fd.append("text", text);
    fd.append("focus", JSON.stringify(Object.fromEntries(FOCUS_TYPES.map((t) => [t, focus[t]]))));
    conflList.forEach((u) => fd.append("confluence_url", u));
    figmaList.forEach((u) => fd.append("figma_url", u));
    setBusy(true);
    setStatus({ kind: "muted", text: "Uploading sources and starting generation…" });
    setLog(["Starting generation…"]);
    try {
      const r = await api("/api/features", { method: "POST", body: fd });
      setStatus({ kind: "accepted", docs: r.doc_count, chunks: r.chunks });
      toast("Generation started");
      // Optional sheet import alongside ingest — it runs its own job.
      const sheet = sheetRef.current && sheetRef.current.files && sheetRef.current.files[0];
      if (sheet && r.feature_id && pid) {
        try {
          const sfd = new FormData();
          sfd.append("file", sheet);
          const sr = await fetch(`/api/projects/${pid}/features/${r.feature_id}/tests/import`, { method: "POST", body: sfd });
          const sj = await sr.json();
          if (sr.ok) toast(`Sheet queued for import (${sheet.name})`);
          else toast(`Sheet import failed: ${sj.detail || sr.status}`, true);
        } catch (e) {
          toast("Sheet import failed: " + e.message, true);
        }
      }
      watchGen(r.job_id, r.feature_id);
    } catch (e) {
      setStatus({ kind: "startFailed", text: e.message });
      toast("Generation failed: " + e.message, true);
      setBusy(false);
    }
  };

  return {
    fileRef,
    sheetRef,
    nameRef,
    name,
    setName,
    ticket,
    ticketKey,
    setTicketKey,
    matchKey,
    setMatchKey,
    text,
    changeText,
    confluence,
    setConfluence,
    figma,
    setFigma,
    files,
    pickFiles,
    removeFile,
    focus,
    focusStart,
    focusFocus,
    focusInput,
    focusEnd,
    estimate,
    status,
    log,
    busy,
    showFeatureCreate,
    back: () => fsRef.current.showFeatureList(),
    sheetTemplate,
    generate,
  };
}
