import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "../../../lib/api.js";
import {
  currentProjectId,
  importSheetForFeature,
  openCaseConfirmation,
  openFeature,
  refreshStatus,
  setCurrentFeature,
  toast,
  uiPrompt,
  updateBackbar,
} from "../../../lib/compatBridge.js";
import { escapeHtml } from "../../../lib/html.js";

/**
 * Features screen: the page switch (list / create / workspace), the feature
 * cards and their menu, and the title from the project list. Registered while
 * mounted (nothing loads on mount):
 *   window.loadFeatures()                  — 00-core.js, 07, imports, test cycles
 *   window.showFeatureList()               — back to the cards (00-core.js, 07)
 *   window.syncFeatureProjects(list, cur)  — after each project-list load (Projects screen)
 * window.showFeatureCreate is registered by useFeatureCreate.
 *
 * page: "list" | "create" | "workspace"
 * list: { status: "idle" | "loading" | "ready" | "error", features, error }
 */
export default function useFeatures() {
  const [page, setPageState] = useState("list");
  const [list, setList] = useState({ status: "idle", features: [], error: "" });
  const [showNewBtn, setShowNewBtn] = useState(true);
  const [openMenu, setOpenMenu] = useState(null);
  const [projects, setProjects] = useState({ list: [], cur: "", synced: false });
  const [pageTick, setPageTick] = useState(0);
  const seq = useRef(0);

  // The backbar (00-core.js) reads #feature-create-page.hidden, so it is
  // redrawn once a page switch is on screen.
  useEffect(() => {
    if (pageTick) updateBackbar();
  }, [pageTick]);
  const showPage = useCallback((p) => {
    setPageState(p);
    setPageTick((t) => t + 1);
  }, []);

  const loadFeatures = useCallback(async () => {
    const my = ++seq.current;
    setList((l) => ({ ...l, status: "loading" }));
    const pid = currentProjectId();
    try {
      const r = await api("/api/features" + (pid ? `?project_id=${pid}` : ""));
      if (my !== seq.current) return;
      setShowNewBtn(r.features.length > 0);
      setList({ status: "ready", features: r.features, error: "" });
      setOpenMenu(null);
    } catch (e) {
      if (my === seq.current) setList({ status: "error", features: [], error: e.message });
    }
  }, []);

  const showFeatureList = useCallback(() => {
    setCurrentFeature(null);
    showPage("list");
  }, [showPage]);

  useEffect(() => {
    const hooks = {
      loadFeatures: () => loadFeatures(),
      showFeatureList: () => showFeatureList(),
      syncFeatureProjects: (all, cur) => setProjects({ list: all, cur: cur || "", synced: true }),
    };
    Object.assign(window, hooks);
    return () => {
      for (const [k, fn] of Object.entries(hooks)) if (window[k] === fn) delete window[k];
    };
  }, [loadFeatures, showFeatureList, showPage]);

  // A click outside every feature card, or Escape, closes the card menu.
  useEffect(() => {
    if (!openMenu) return;
    const onClick = (e) => {
      if (!e.target.closest("[data-feature-card]")) setOpenMenu(null);
    };
    const onKey = (e) => {
      if (e.key === "Escape") setOpenMenu(null);
    };
    document.addEventListener("click", onClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("click", onClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [openMenu]);

  const cardName = (fid) => (list.features.find((f) => f.id === fid)?.name || "").trim();

  const renameFromCard = async (fid) => {
    const name = await uiPrompt("Rename feature", "Feature name", cardName(fid));
    if (!name) return;
    await api("/api/features/" + fid, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    });
    loadFeatures();
    toast("Feature renamed");
  };

  const deleteFromCard = async (fid) => {
    setCurrentFeature(fid);
    const f = await api("/api/features/" + fid);
    const n = (f.test_cases || []).length;
    openCaseConfirmation({
      title: "Delete feature",
      copy: "This removes the feature, its document chunks, and its test-case links. Test cases still linked to another feature will not be deleted.",
      summary: `<b>${escapeHtml(f.name)}</b><div class="muted" style="margin-top:6px">Version ${f.version || 1} · ${n} test case${n === 1 ? "" : "s"}</div>`,
      confirmLabel: "Delete feature",
      danger: true,
      onConfirm: async () => {
        const r = await api("/api/features/" + fid, { method: "DELETE" });
        setCurrentFeature(null);
        showFeatureList();
        loadFeatures();
        refreshStatus();
        toast(
          `Feature deleted · ${r.removed_orphan_cases} orphan test case(s) removed · ${r.preserved_shared_cases} shared test case(s) preserved`,
        );
      },
    });
  };

  const active = projects.list.find((p) => p.id === projects.cur) || null;

  return {
    page,
    showPage,
    list,
    showNewBtn,
    openMenu,
    projects,
    active,
    loadFeatures,
    showFeatureList,
    toggleMenu: (fid) => setOpenMenu((m) => (m === fid ? null : fid)),
    open: (fid) => openFeature(fid),
    renameFromCard,
    importSheet: (f) => importSheetForFeature(f.id, f.project_id || ""),
    deleteFromCard,
  };
}
