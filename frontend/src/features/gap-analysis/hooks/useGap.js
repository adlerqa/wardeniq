import { useEffect, useRef, useState } from "react";
import { api } from "../../../lib/api.js";
import {
  currentFeatureId,
  currentFeatureName,
  currentProjectId,
  toast,
  uiConfirm,
  uiPrompt,
} from "../../../lib/compatBridge.js";
import { nav } from "../../../app/navState.js";
import { exportFileName, isActiveRun, manualRunBody } from "../lib/gap.js";

const callWindow = (name, ...args) => (typeof window[name] === "function" ? window[name](...args) : undefined);

/** Download a gap report; "Open a feature first" (and resolves) without a feature. */
async function downloadGapExport(kind, fmt) {
  const fid = currentFeatureId();
  if (!fid) {
    toast("Open a feature first", true);
    return;
  }
  const mime = fmt === "pdf" ? "application/pdf" : "text/csv";
  const res = await fetch(`/api/features/${fid}/gap/${kind}/export/${fmt}`, { method: "GET" });
  if (!res.ok) {
    let detail = "Export failed";
    try {
      detail = (await res.json()).detail || detail;
    } catch {
      /* keep the generic message */
    }
    throw new Error(detail);
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(new Blob([blob], { type: mime }));
  const a = document.createElement("a");
  a.href = url;
  a.download = exportFileName(nav.get().featureData?.name, kind, fmt);
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

/**
 * Gap Analysis screen (was compat/runtime/controllers/13-gap-analysis.js).
 * Registers window.initGap() (navigateTo("gap")) and window.openGapPrRun(runId).
 *
 * PR tab: the feature's PR coverage runs, re-polled every 2 s while a run is
 * active and every 4 s otherwise (only while that tab shows); a run's detail;
 * exclude / include a PR; reassign a run; a manual run on a PR, followed to the end.
 * Automation tab: the project's Test repos (rescan / reset, re-polled while
 * scanning) and which generated cases have an automated test.
 */
export function useGap() {
  const [view, setView] = useState({ hasFeature: null, title: "Gap Analysis" });
  const [tab, setTab] = useState("pr");
  const [live, setLive] = useState(false);
  const [list, setList] = useState({ kind: "initial" });
  const [detail, setDetail] = useState({ open: false, title: "Run detail", body: null });
  const [manual, setManual] = useState({ busy: false, label: "+ Run on a PR" });
  // Automation tab. Like before, the summary, KPIs and items keep their last
  // content while a reload or an error replaces the repo list.
  const [auto, setAuto] = useState({ repos: { kind: "idle" }, summary: "", showStats: false, scan: null, seq: 0 });

  const tabRef = useRef("pr");
  const hasFeatureRef = useRef(false);
  const prPoll = useRef(null);
  const autoPoll = useRef(null);
  const fns = useRef({});

  const stopPrPoll = () => {
    if (prPoll.current) {
      clearTimeout(prPoll.current);
      prPoll.current = null;
    }
  };
  const schedulePrPoll = (anyActive) => {
    stopPrPoll();
    if (tabRef.current !== "pr" || !hasFeatureRef.current || !currentFeatureId()) return;
    prPoll.current = setTimeout(() => fns.current.loadRuns({ silent: true }), anyActive ? 2000 : 4000);
  };

  const loadRuns = async (opts) => {
    const silent = !!(opts && opts.silent === true);
    const fid = currentFeatureId();
    if (!fid) return;
    if (!silent) setList({ kind: "loading" });
    try {
      const r = await api(`/api/features/${fid}/code-coverage/runs?limit=50`);
      const runs = r.runs || [];
      const anyActive = runs.some(isActiveRun);
      setLive(anyActive);
      if (!runs.length) {
        setList({ kind: "empty" });
        schedulePrPoll(false);
        return;
      }
      setList({ kind: "runs", runs });
      schedulePrPoll(anyActive);
    } catch (e) {
      if (!silent) setList({ kind: "error", text: e.message });
      schedulePrPoll(false); // keep retrying slowly on transient errors
    }
  };

  const loadAuto = async () => {
    const fid = currentFeatureId();
    if (!fid) return;
    setAuto((a) => ({ ...a, repos: { kind: "loading" }, showStats: false }));
    try {
      const r = await api(`/api/features/${fid}/automation-coverage`);
      const repos = r.test_repos || [];
      if (!repos.length) {
        setAuto((a) => ({ ...a, repos: { kind: "none" }, summary: "" }));
        return;
      }
      const haveScan = (r.total_generated || 0) > 0 && (r.items || []).length;
      setAuto((a) =>
        haveScan
          ? {
              repos: { kind: "list", list: repos },
              summary: `${r.covered_count}/${r.total_generated} covered · scanned ${r.scanned_repo_full_name || ""}`,
              showStats: true,
              scan: r,
              seq: a.seq + 1,
            }
          : { ...a, repos: { kind: "list", list: repos }, summary: "Rescan a test repo to populate coverage." },
      );
      if (!haveScan) return;
      if ((r.test_repos || []).some((rp) => rp.scan_status === "running")) {
        if (autoPoll.current) clearTimeout(autoPoll.current);
        autoPoll.current = setTimeout(() => fns.current.loadAuto(), 3000);
      }
    } catch (e) {
      setAuto((a) => ({ ...a, repos: { kind: "error", text: e.message } }));
    }
  };

  const switchTab = (t) => {
    tabRef.current = t;
    setTab(t);
    stopPrPoll();
    if (autoPoll.current) {
      clearTimeout(autoPoll.current);
      autoPoll.current = null;
    }
    if (t === "pr") fns.current.loadRuns();
    else fns.current.loadAuto();
  };

  const openRun = async (rid) => {
    setDetail((d) => ({ ...d, open: true, body: { kind: "loading" } }));
    try {
      const r = await api(`/api/code-coverage/runs/${rid}`);
      // Never show a run that belongs to another feature than the one on screen.
      const fid = currentFeatureId();
      if (r.feature_id && fid && r.feature_id !== fid) {
        setDetail((d) => ({ ...d, open: false, body: null }));
        return;
      }
      setDetail({ open: true, title: `Run · PR #${r.pr_number} · ${r.repo_full_name || ""}`, body: { kind: "run", run: r, seq: Date.now() } });
    } catch (e) {
      setDetail((d) => ({ ...d, body: { kind: "error", text: e.message } }));
    }
  };

  const initGap = () => {
    if (!currentFeatureId()) {
      hasFeatureRef.current = false;
      setView((v) => ({ ...v, hasFeature: false }));
      return;
    }
    // A run detail from a previously viewed feature must not leak into this one.
    setDetail((d) => ({ ...d, open: false, body: null }));
    hasFeatureRef.current = true;
    setView({ hasFeature: true, title: `${currentFeatureName() || "Feature"} — Gap Analysis` });
    switchTab(tabRef.current);
  };

  fns.current = { loadRuns, loadAuto };

  useEffect(() => {
    const open = (rid) => openRun(rid);
    const init = () => initGap();
    Object.assign(window, { initGap: init, openGapPrRun: open });
    return () => {
      stopPrPoll();
      if (autoPoll.current) clearTimeout(autoPoll.current);
      if (window.initGap === init) delete window.initGap;
      if (window.openGapPrRun === open) delete window.openGapPrRun;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const setExcluded = async (prId, excluded) => {
    if (!prId) {
      toast("PR id unavailable for this run", true);
      return;
    }
    try {
      await api(`/api/prs/${prId}/exclude`, { method: "POST", json: { excluded } });
      toast(excluded ? "PR excluded from coverage" : "PR included in coverage");
      loadRuns();
      // The feature's coverage card reflects the change too.
      const fid = currentFeatureId();
      if (fid) callWindow("loadCoverage", fid);
    } catch (e) {
      toast(e.message || "Could not update PR", true);
    }
  };

  const reassign = async (runId) => {
    const pid = currentProjectId();
    if (!pid) return;
    try {
      const r = await api(`/api/features?project_id=${pid}`);
      const features = r.features || [];
      if (!features.length) {
        toast("No features in this project", true);
        return;
      }
      const labels = features.map((f, i) => `${i + 1}. ${f.name}${f.version ? " (v" + f.version + ")" : ""}`).join("\n");
      const choice = await uiPrompt("Reassign feature", `Pick a feature for this run by number:\n${labels}`, "1");
      const idx = parseInt(choice || "0", 10) - 1;
      if (isNaN(idx) || idx < 0 || idx >= features.length) {
        toast("Invalid pick", true);
        return;
      }
      await api(`/api/code-coverage/runs/${runId}/reassign`, { method: "POST", json: { feature_id: features[idx].id } });
      toast(`Reassigning + re-running against ${features[idx].name}…`);
      setTimeout(() => fns.current.loadRuns(), 1500);
      setDetail((d) => ({ ...d, open: false }));
    } catch (e) {
      toast(e.message, true);
    }
  };

  const runManual = async () => {
    const fid = currentFeatureId();
    const pid = currentProjectId();
    if (!fid || !pid) {
      toast("Open a feature first", true);
      return;
    }
    const choice = await uiPrompt(
      "Run PR coverage",
      "Paste a full PR/MR URL (github.com/.../pull/N or gitlab.com/.../merge_requests/N) — or just a PR number if you only have one App repo connected.",
      "",
    );
    if (!choice) return;
    let repos = [];
    if (!/https?:\/\//i.test(String(choice).trim())) repos = (await api(`/api/projects/${pid}/repos`)).repos || [];
    const made = manualRunBody(fid, choice, repos);
    if (made.error) {
      toast(made.error, true);
      return;
    }
    setManual({ busy: true, label: "Starting…" });
    setList({ kind: "muted", text: "⏳ Starting coverage analysis…" });
    let jobId;
    const done = () => setManual({ busy: false, label: "+ Run on a PR" });
    try {
      const r = await api("/api/code-coverage/runs/manual", { method: "POST", json: made.body });
      jobId = r.job_id;
      toast(`Coverage run started · ${r.repo_full_name || ""} #${r.pr_number || ""}`);
    } catch (e) {
      toast(e.message, true);
      done();
      setList({ kind: "error", text: e.message });
      return;
    }
    // Follow the job (and refresh the runs) until it ends; give up after 10 minutes.
    const start = Date.now();
    const poll = async () => {
      try {
        const j = await api(`/api/jobs/${jobId}`);
        setList({ kind: "muted", text: `⏳ ${j.stage || "Working…"} · ${j.progress || 0}%` });
        if (j.status === "succeeded" || j.status === "failed") {
          done();
          if (j.status === "failed") toast(`Run failed: ${j.error || ""}`, true);
          fns.current.loadRuns();
          return;
        }
      } catch {
        /* keep polling on transient errors */
      }
      if (Date.now() - start > 10 * 60 * 1000) {
        done();
        fns.current.loadRuns();
        return;
      }
      setTimeout(poll, 1500);
    };
    poll();
  };

  const rescan = async (rid) => {
    const pid = currentProjectId();
    if (!pid) return;
    try {
      const fid = currentFeatureId();
      await api(`/api/projects/${pid}/repos/${rid}/rescan${fid ? `?feature_id=${fid}` : ""}`, { method: "POST" });
      toast("Rescan started — matching only the current feature for speed");
      setTimeout(() => fns.current.loadAuto(), 1500);
    } catch (e) {
      toast(e.message, true);
    }
  };

  const resetScan = async (rid) => {
    const pid = currentProjectId();
    if (!pid) return;
    if (
      !(await uiConfirm(
        "Force-mark this scan as failed? Use this when a scan has been stuck for several minutes.",
        "Reset Scan Status",
        "Reset",
        true,
      ))
    )
      return;
    try {
      await api(`/api/projects/${pid}/repos/${rid}/scan/reset`, { method: "POST" });
      toast("Scan reset — you can now try Rescan again");
      setTimeout(() => fns.current.loadAuto(), 500);
    } catch (e) {
      toast(e.message, true);
    }
  };

  const exportReport = (kind, fmt) =>
    downloadGapExport(kind, fmt)
      .then(() => toast("Export ready"))
      .catch((err) => toast(err.message || "Export failed", true));

  return {
    view,
    tab,
    live,
    list,
    detail,
    manual,
    auto,
    actions: {
      switchTab,
      refreshRuns: () => loadRuns(),
      openRun,
      closeRun: () => setDetail((d) => ({ ...d, open: false })),
      setExcluded,
      reassign,
      runManual,
      refreshAuto: () => loadAuto(),
      rescan,
      resetScan,
      exportReport,
    },
  };
}
