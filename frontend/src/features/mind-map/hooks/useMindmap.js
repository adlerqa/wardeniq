import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "../../../lib/api.js";
import {
  currentProjectId,
  loadProjects,
  setCurrentProject,
  toast,
  watchJob,
} from "../../../lib/compatBridge.js";
import { branchMap, repoAnalysisDefaultChecked, withoutConnected } from "../lib/mindmap.js";

/**
 * Mind Map controls and coverage list (was the first half of
 * 09-mind-map-and-jobs.js). navigateTo("mindmap") in 00-core.js calls
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
  const [repos, setRepos] = useState([]); // [{ id, full_name, kind, default_branch, checked, branch, branchOptions }]
  const [status, setStatus] = useState(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [diag, setDiagState] = useState({ rows: [], key: 0 });
  const [map, setMap] = useState({ status: "idle", data: null, error: "" });
  const [picker, setPicker] = useState(null); // { pid, repos }
  const [graphData, setGraphData] = useState(null);
  const pidRef = useRef("");
  const mapSeq = useRef(0);
  // Each redraw starts collapsed again, as the old innerHTML redraw did.
  const setDiag = useCallback((rows) => setDiagState((d) => ({ rows, key: d.key + 1 })), []);

  const projectId = () => pidRef.current || currentProjectId() || "";

  const loadRepos = useCallback(async () => {
    const p = pidRef.current || currentProjectId() || "";
    if (!p) return;
    let list;
    try {
      const r = await api(`/api/projects/${p}/repos?repo_type=app`); // app repos only
      list = r.repos || [];
    } catch {
      return;
    }
    setRepos(
      list.map((rp) => ({
        ...rp,
        checked: repoAnalysisDefaultChecked(rp.kind),
        branch: "",
        defaultLabel: rp.default_branch || "default",
        branchOptions: [],
      })),
    );
    // Branch lists come from each repo's provider, one repo at a time.
    for (const rp of list) {
      try {
        const r = await api(`/api/repos/${rp.id}/branches`);
        if (!(r.branches || []).length) continue;
        const def = r.default || rp.default_branch || "";
        setRepos((rows) =>
          rows.map((row) =>
            row.id === rp.id
              ? { ...row, defaultLabel: def || "default", branchOptions: r.branches.filter((b) => b !== def) }
              : row,
          ),
        );
      } catch {
        /* keep the default-only option */
      }
    }
  }, []);

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

  const updateRepo = (id, patch) => setRepos((rows) => rows.map((r) => (r.id === id ? { ...r, ...patch } : r)));

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

  /** "+ Add a repo from GitHub": list what the project's PAT can see, minus connected repos. */
  const openPicker = async () => {
    const p = projectId();
    if (!p) {
      toast("Pick a project first", true);
      return;
    }
    let found = [];
    try {
      for (let page = 1; page <= 4; page++) {
        const r = await api(`/api/projects/${p}/github/accessible-repos?page=${page}`);
        const batch = r.repos || [];
        found = found.concat(batch);
        if (batch.length < 30) break;
      }
    } catch (e) {
      toast(
        `Couldn't list repos for this project (${e.message}). Check the project's GitHub PAT under Projects & Repos.`,
        true,
      );
      return;
    }
    try {
      const pr = await api(`/api/projects/${p}/repos`);
      found = withoutConnected(found, pr.repos);
    } catch {
      /* show everything */
    }
    if (!found.length) {
      toast("No new repos to add — all your accessible repos are already in this project", true);
      return;
    }
    setPicker({ pid: p, repos: found });
  };

  const addPicked = async (picks) => {
    if (!picks.length) {
      toast("Select at least one repo", true);
      return;
    }
    const p = picker.pid;
    let ok = 0,
      fail = 0;
    for (const pick of picks) {
      try {
        await api(`/api/projects/${p}/repos`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ repo_full_name: pick.full_name, default_branch: pick.def || "main", repo_type: "app" }),
        });
        ok++;
      } catch {
        fail++;
      }
    }
    setPicker(null);
    toast(`${ok} repo(s) added${fail ? ` · ${fail} skipped (already added or inaccessible)` : ""}`);
    loadRepos();
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
    closePicker: () => setPicker(null),
    addPicked,
  };
}
