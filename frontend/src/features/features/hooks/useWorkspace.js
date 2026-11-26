import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "../../../lib/api.js";
import {
  currentFeatureId,
  openCaseConfirmation,
  openImportLibraryModal,
  openNewVersionModal,
  refreshStatus,
  setCurrentFeature,
  setCurrentFeatureData,
  toast,
  uiPrompt,
  updateBackbar,
  watchJob,
} from "../../../lib/compatBridge.js";
import { escapeHtml } from "../../../lib/html.js";
import useCaseList from "../../test-cases/hooks/useCaseList.js";
import { groupCases, orderedCases } from "../lib/workspace.js";

const callWindow = (name, ...args) => (typeof window[name] === "function" ? window[name](...args) : undefined);

/**
 * The feature workspace (was openFeature and the workspace half of
 * 03-features-and-usage.js, plus the workspace buttons in 07). `fs` is
 * useFeatures(): it owns the page switch. Registered while mounted:
 *   window.openFeature(fid)              — cards, versions, saves, app/navigation.js navigateTo
 *   window.watchFeatureGen(jobId, fid)   — the generation banner (new-version dialog)
 *   window.viewCase(cid)                 — open a case's detail (Step Library "Open")
 *   window.loadCoverage(fid)             — refresh the coverage card (13 gap analysis)
 *
 * view: { seq, feature, error } — `seq` remounts the case groups (closed) on each load
 * banner: null | { kind: "running", caption } | { kind: "failed", text }
 */
export default function useWorkspace(fs) {
  const [view, setView] = useState({ seq: 0, feature: null, error: "" });
  const [coverage, setCoverage] = useState({ fid: null, summary: null, seq: 0 });
  const [thresholdStatus, setThresholdStatus] = useState("");
  const [matchKeyStatus, setMatchKeyStatus] = useState("");
  const [banner, setBanner] = useState(null);
  const [tick, setTick] = useState(0);
  const watching = useRef(new Map()); // jobId → feature id
  const fsRef = useRef(fs);
  fsRef.current = fs;

  const f = view.feature;
  const fid = f ? f.id || null : null;
  const fidRef = useRef(null);
  fidRef.current = fid;
  const bt = f ? groupCases(f.test_cases) : {};
  const ordered = f ? orderedCases(bt) : [];
  const cl = useCaseList(ordered, view.seq, { feature: () => currentFeatureId() || "", reload: () => {} });

  // Breadcrumbs follow a load once it is on screen.
  useEffect(() => {
    if (tick) updateBackbar();
  }, [tick]);

  const loadCoverage = useCallback(async (id) => {
    setCoverage((c) => ({ fid: id, summary: null, seq: c.seq + 1 }));
    setThresholdStatus("");
    try {
      const r = await api(`/api/features/${id}/coverage`);
      if (r.summary) setCoverage((c) => ({ fid: id, summary: r.summary, seq: c.seq + 1 }));
    } catch {
      /* the coverage card just stays empty */
    }
  }, []);

  const watchFeatureGen = useCallback((jobId, featureId) => {
    if (!jobId) return;
    if (watching.current.has(jobId)) {
      // Already following it (e.g. the workspace was reopened): show the loader again.
      setBanner((b) => b || { kind: "running", caption: null });
      return;
    }
    watching.current.set(jobId, featureId);
    setBanner({ kind: "running", caption: null });
    watchJob(jobId, (j) => {
      if (j.status === "running") {
        setBanner({ kind: "running", caption: j });
        return;
      }
      watching.current.delete(jobId);
      if (j.status === "failed") {
        setBanner({ kind: "failed", text: j.error || "unknown error" });
        return;
      }
      setBanner(null);
      callWindow("loadFeatures");
      refreshStatus();
      if (featureId) callWindow("openFeature", featureId); // the new cases appear
    });
  }, []);

  const openFeature = useCallback(
    async (id) => {
      try {
        const feat = await api("/api/features/" + id);
        setCurrentFeature(id);
        setCurrentFeatureData(feat);
        setBanner(null);
        fsRef.current.showPage("workspace");
        setMatchKeyStatus("");
        setView((v) => ({ seq: v.seq + 1, feature: { ...feat, id }, error: "" }));
        loadCoverage(id);
        window.scrollTo({ top: 0, behavior: "smooth" });
        setTick((t) => t + 1);
        // A generation / ingest job still running (after a refresh, or coming back) gets its loader.
        try {
          const r = await api("/api/jobs?status=running&limit=50");
          const job = (r.jobs || []).find((j) => j.feature_id === id && ["generate", "ingest"].includes(j.type));
          if (job) watchFeatureGen(job.id, id);
        } catch {
          /* no loader */
        }
      } catch (e) {
        setView((v) => ({ ...v, error: e.message, seq: v.seq + 1 }));
      }
    },
    [loadCoverage, watchFeatureGen],
  );

  const clRef = useRef(cl);
  clRef.current = cl;
  useEffect(() => {
    const hooks = {
      openFeature: (id) => openFeature(id),
      watchFeatureGen: (jobId, id) => watchFeatureGen(jobId, id),
      // Refresh the coverage card (13 gap analysis, after a run).
      loadCoverage: (id) => loadCoverage(id),
      // Open a case's detail in the workspace (Step Library "Open").
      viewCase: (cid) => {
        if (clRef.current.open !== cid) clRef.current.toggleDetail(cid);
      },
    };
    Object.assign(window, hooks);
    return () => {
      for (const [k, fn] of Object.entries(hooks)) if (window[k] === fn) delete window[k];
    };
  }, [loadCoverage, openFeature, watchFeatureGen]);

  const saveMatchKey = async (value) => {
    const id = currentFeatureId();
    if (!id) return;
    try {
      const r = await api(`/api/features/${id}/match-key`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ match_key: value.trim() }),
      });
      if (f) f.match_key = r.match_key;
      setMatchKeyStatus(r.match_key ? `saved · PRs tagged [${r.match_key}] map here` : "cleared");
      toast("PR match tag " + (r.match_key ? "set to [" + r.match_key + "]" : "cleared"));
    } catch (e) {
      setMatchKeyStatus(e.message || "failed");
      toast(e.message || "failed", true);
    }
  };

  const saveThreshold = async (raw) => {
    const id = coverage.fid;
    const v = parseInt(raw || "80", 10);
    try {
      const r = await api(`/api/features/${id}/ready-threshold`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ threshold: isNaN(v) ? 80 : v }),
      });
      toast(`QA-readiness target set to ${r.ready_threshold}% code coverage`);
      loadCoverage(id);
    } catch (e) {
      setThresholdStatus(e.message || "failed");
      toast(e.message || "Could not save target", true);
    }
  };

  const syncJira = async () => {
    try {
      const r = await api(`/api/features/${fid}/jira-sync`, { method: "POST" });
      toast("Posted coverage to Jira " + r.issue);
    } catch (e) {
      toast(e.message, true);
    }
  };

  const reuseImported = () => {
    const id = currentFeatureId();
    if (!id) {
      toast("Open a feature first", true);
      return;
    }
    openImportLibraryModal(id);
  };

  // The header's (hidden) Rename / Delete buttons.
  const rename = async () => {
    const id = currentFeatureId();
    if (!id) return;
    const name = await uiPrompt("Rename feature", "Feature name", f ? f.name : "Feature");
    if (!name) return;
    await api("/api/features/" + id, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    });
    openFeature(id);
    callWindow("loadFeatures");
    toast("Renamed");
  };
  const remove = () => {
    const id = currentFeatureId();
    if (!id) return;
    openCaseConfirmation({
      title: "Delete feature",
      copy: "This removes the feature, its document chunks, and its testcase links. Testcases still linked to another feature will not be deleted.",
      summary: `<b>${escapeHtml(f ? f.name : "Feature")}</b><div class="muted" style="margin-top:6px"></div>`,
      confirmLabel: "Delete feature",
      danger: true,
      onConfirm: async () => {
        const r = await api("/api/features/" + id, { method: "DELETE" });
        setCurrentFeature(null);
        fsRef.current.showFeatureList();
        callWindow("loadFeatures");
        refreshStatus();
        toast(
          `Feature deleted · ${r.removed_orphan_cases} orphan testcase(s) removed · ${r.preserved_shared_cases} shared testcase(s) preserved`,
        );
      },
    });
  };

  const newVersion = () => {
    const id = currentFeatureId();
    if (!id || !f) return;
    const cur = (f.versions || []).find((v) => v.id === id);
    openNewVersionModal(id, `${f.name} — current ${cur ? `v${cur.version} · ${cur.case_count} cases` : ""}`);
  };

  return {
    view,
    feature: f,
    bt,
    cl,
    coverage,
    thresholdStatus,
    matchKeyStatus,
    banner,
    openFeature,
    saveMatchKey,
    saveThreshold,
    syncJira,
    reuseImported,
    rename,
    remove,
    newVersion,
    switchVersion: (id) => openFeature(id),
  };
}
