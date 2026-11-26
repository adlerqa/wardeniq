import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "../../../lib/api.js";
import {
  currentProjectId,
  loadProjects,
  setCurrentProject,
  toast,
  watchJob,
} from "../../../lib/compatBridge.js";
import useAnalysisRepos from "../../mind-map/hooks/useAnalysisRepos.js";
import { branchMap } from "../../mind-map/lib/mindmap.js";
import {
  analyzeTitle,
  daysInRange,
  DAYS_RANGE_TEXT,
  lookbackDays,
  NO_SAVED_TEXT,
  restoredCounts,
  restoredText,
  startText,
} from "../lib/codeAnalysis.js";

/** The Test Cycles screen's list reload (registered by useTestCycles), if mounted. */
const reloadCycles = () => (typeof window.loadCycles === "function" ? window.loadCycles() : undefined);

/**
 * Code Analysis (change impact) screen (was the code analysis half of
 * 08-code-analysis-and-cycles.js). Registered while mounted; nothing loads on
 * mount:
 *   window.initCycles()                — navigateTo("cycles") in app/navigation.js
 *   window.openCodeAnalysisFor(pid, rid) — "Analyze" on a Projects repo card (02 gotoAnalyze)
 *
 * status:   null | { kind: "text" | "muted" | "error" | "running" | "failed" | "done", ... }
 * impacted: null (nothing shown) | { list, grounded, ai, commits, key }
 */
export default function useCodeAnalysis() {
  const [projects, setProjects] = useState([]);
  const [pid, setPid] = useState("");
  const [days, setDays] = useState("14");
  const [running, setRunning] = useState(false);
  const [status, setStatus] = useState(null);
  const [impacted, setImpacted] = useState(null);
  const [selected, setSelected] = useState(() => new Set());
  // The old controller replaced #cyc-make's icon with plain text the first
  // time a review was drawn; `shownOnce` keeps that look.
  const [shownOnce, setShownOnce] = useState(false);
  const [name, setName] = useState("");
  const pidRef = useRef("");
  const keyRef = useRef(0);
  const rp = useAnalysisRepos(pidRef);
  const { loadRepos } = rp;

  const inRange = daysInRange(days);
  const projectId = () => pidRef.current || currentProjectId() || "";

  /** Draws a review (was renderImpacted): selection cleared, rows collapsed. */
  const showImpacted = useCallback((a) => {
    const list = a.impacted || [];
    setSelected(new Set());
    setImpacted({ list, grounded: a.grounded || 0, ai: a.ai || 0, commits: a.commits || [], key: ++keyRef.current });
    if (list.length) setShownOnce(true);
  }, []);

  const clearImpacted = useCallback((msg) => {
    setImpacted(null);
    setSelected(new Set());
    setStatus(msg ? { kind: "muted", text: msg } : null);
  }, []);

  const loadLatest = useCallback(async () => {
    const p = pidRef.current || currentProjectId() || "";
    if (!p) return;
    clearImpacted(""); // a project with no saved review must not show the previous one
    try {
      const run = await api(`/api/projects/${p}/commit-analysis/latest`);
      const results = run.results || [];
      if (!results.length) {
        clearImpacted(NO_SAVED_TEXT);
        return;
      }
      setStatus({ kind: "muted", text: restoredText(results.length) });
      showImpacted({ impacted: results, ...restoredCounts(results), commits: run.commits || [] });
    } catch {
      clearImpacted("");
    }
  }, [clearImpacted, showImpacted]);

  const syncProjects = useCallback(async (p) => {
    const list = await loadProjects();
    setProjects(list);
    pidRef.current = p ?? (currentProjectId() || "");
    setPid(pidRef.current);
  }, []);

  const initCycles = useCallback(async () => {
    await syncProjects();
    await loadRepos();
    loadLatest();
  }, [loadLatest, loadRepos, syncProjects]);

  const openFor = useCallback(
    async (p, rid) => {
      await syncProjects(p);
      await loadRepos({ only: rid });
    },
    [loadRepos, syncProjects],
  );

  useEffect(() => {
    const init = () => initCycles();
    const open = (p, rid) => openFor(p, rid);
    window.initCycles = init;
    window.openCodeAnalysisFor = open;
    return () => {
      if (window.initCycles === init) delete window.initCycles;
      if (window.openCodeAnalysisFor === open) delete window.openCodeAnalysisFor;
    };
  }, [initCycles, openFor]);

  const changeProject = (p) => {
    pidRef.current = p;
    setPid(p);
    setCurrentProject(p);
    loadRepos();
    loadLatest();
  };

  const refresh = () => {
    loadRepos();
    loadLatest();
  };

  const analyze = async () => {
    // The button is disabled out of range; this guards a programmatic click.
    if (!daysInRange(days)) {
      toast(DAYS_RANGE_TEXT, true);
      return;
    }
    const ids = rp.repos.filter((r) => r.checked).map((r) => r.id);
    if (!ids.length) {
      toast("Select at least one repo", true);
      return;
    }
    setImpacted(null);
    setSelected(new Set());
    setStatus({ kind: "text", text: startText(ids.length) });
    setRunning(true);
    let r;
    try {
      r = await api("/api/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          project_id: projectId(),
          repo_ids: ids,
          branches: branchMap(rp.repos),
          days: lookbackDays(days),
        }),
      });
    } catch (e) {
      setStatus({ kind: "error", text: e.message });
      setRunning(false);
      return;
    }
    if (!r.job_id) return;
    watchJob(r.job_id, (j) => {
      const a = j.result || {};
      if (j.status === "running") {
        setStatus({ kind: "running", stage: j.stage, result: a });
        return;
      }
      setStatus(j.status === "failed" ? { kind: "failed", text: j.error || "" } : { kind: "done", result: a });
      setRunning(false);
      showImpacted(a);
    });
  };

  const toggleCase = (i, on) =>
    setSelected((s) => {
      const next = new Set(s);
      if (on) next.add(i);
      else next.delete(i);
      return next;
    });
  const toggleAll = (on) => setSelected(on ? new Set((impacted?.list || []).map((_, i) => i)) : new Set());

  const createCycle = async () => {
    const list = impacted?.list || [];
    const ids = [...selected].sort((a, b) => a - b).map((i) => list[i].case_id);
    if (!ids.length) {
      toast("Select at least one case", true);
      return;
    }
    const cycleName = name.trim();
    if (!cycleName) {
      toast("Enter a cycle name", true);
      return;
    }
    try {
      await api("/api/test-cycles", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          project_id: projectId(),
          name: cycleName,
          case_ids: ids,
          source: { repo_ids: rp.repos.filter((r) => r.checked).map((r) => r.id), days: lookbackDays(days) },
        }),
      });
      setName("");
      toast(`Cycle created with ${ids.length} case(s) — see it under Test Cycles`);
      reloadCycles();
    } catch (e) {
      toast(e.message, true);
    }
  };

  return {
    projects,
    pid,
    days,
    setDays,
    inRange,
    running,
    analyzeDisabled: running || !inRange,
    analyzeTitle: analyzeTitle(inRange, running),
    status,
    impacted,
    selected,
    shownOnce,
    name,
    setName,
    repos: rp.repos,
    updateRepo: rp.updateRepo,
    picker: rp.picker,
    openPicker: rp.openPicker,
    closePicker: rp.closePicker,
    addPicked: rp.addPicked,
    changeProject,
    refresh,
    analyze,
    toggleCase,
    toggleAll,
    createCycle,
  };
}
