import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "../../../lib/api.js";
import {
  currentProjectId,
  loadProjects,
  setCurrentProject,
  toast,
  watchJob,
} from "../../../lib/compatBridge.js";
import { branchMap } from "../lib/mindmap.js";
import useAnalysisRepos from "./useAnalysisRepos.js";

/**
 * Mind Map controls and coverage list (was the first half of
 * 09-mind-map-and-jobs.js). navigateTo("mindmap") in app/navigation.js calls
 * window.initMindmap(), registered while mounted; nothing loads on mount.
 * `graphData` is the last /mindmap response that loaded, drawn by the
 * coverage graph (kept when a later load fails, as before).
 *
 * status: { kind: "text" | "running" | "failed" | "done" | "error", ... }
 * map:    { status: "idle" | "loading" | "analyzing" | "noproject" | "ready" | "error", data, error }
 */
export default function useMindmap() {
  const [projects, setProjects] = useState([]);
  const [pid, setPid] = useState("");
  const [status, setStatus] = useState(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [diag, setDiagState] = useState({ rows: [], key: 0 });
  const [map, setMap] = useState({ status: "idle", data: null, error: "" });
  const [graphData, setGraphData] = useState(null);
  const pidRef = useRef("");
  const { repos, picker, loadRepos, updateRepo, openPicker, closePicker, addPicked } = useAnalysisRepos(pidRef);
  const mapSeq = useRef(0);
  // Each redraw starts collapsed again, as the old innerHTML redraw did.
  const setDiag = useCallback((rows) => setDiagState((d) => ({ rows, key: d.key + 1 })), []);

  const projectId = () => pidRef.current || currentProjectId() || "";

  const loadMindmap = useCallback(async () => {
    const p = pidRef.current || currentProjectId() || "";
    const my = ++mapSeq.current;
    if (!p) {
      setMap({ status: "noproject", data: null, error: "" });
      return;
    }
    setMap((m) => ({ ...m, status: "loading" }));
    try {
      const r = await api(`/api/projects/${p}/mindmap`);
      if (my !== mapSeq.current) return;
      setDiag(r.last_analysis?.per_repo || []);
      setGraphData(r);
      setMap({ status: "ready", data: r, error: "", seq: my });
    } catch (e) {
      if (my === mapSeq.current) setMap({ status: "error", data: null, error: e.message });
    }
  }, [setDiag]);

  const initMindmap = useCallback(async () => {
    const list = await loadProjects();
    setProjects(list);
    const p = currentProjectId() || "";
    pidRef.current = p;
    setPid(p);
    await loadRepos();
    loadMindmap();
  }, [loadMindmap, loadRepos]);

  useEffect(() => {
    const hook = () => initMindmap();
    window.initMindmap = hook;
    return () => {
      if (window.initMindmap === hook) delete window.initMindmap;
    };
  }, [initMindmap]);

  const changeProject = (p) => {
    pidRef.current = p;
    setPid(p);
    setCurrentProject(p);
    loadRepos();
    loadMindmap();
  };

  const analyze = async () => {
    const ids = repos.filter((r) => r.checked).map((r) => r.id);
    if (!ids.length) {
      toast("Select at least one repo", true);
      return;
    }
    setStatus({ kind: "text", text: `Starting implementation coverage review for ${ids.length} repo${ids.length === 1 ? "" : "s"}…` });
    setAnalyzing(true);
    setDiag([]);
    mapSeq.current++;
    setMap((m) => ({ ...m, status: "analyzing" }));
    let r;
    try {
      r = await api("/api/code-analysis", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ project_id: projectId(), repo_ids: ids, branches: branchMap(repos) }),
      });
    } catch (e) {
      setStatus({ kind: "error", text: e.message });
      setAnalyzing(false);
      return;
    }
    if (!r.job_id) return;
    watchJob(r.job_id, (j) => {
      const a = j.result || {};
      if (j.status === "running") setStatus({ kind: "running", stage: j.stage, result: a });
      else if (j.status === "failed") setStatus({ kind: "failed", text: j.error || "" });
      else setStatus({ kind: "done", result: a });
      if (j.status !== "running") {
        setAnalyzing(false);
        setDiag(a.per_repo || []);
        loadMindmap();
      }
    });
  };

  return {
    projects,
    pid,
    repos,
    status,
    analyzing,
    diag,
    map,
    graphData,
    picker,
    changeProject,
    updateRepo,
    analyze,
    refresh: loadMindmap,
    openPicker,
    closePicker,
    addPicked,
  };
}
