import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "../../../lib/api.js";
import {
  currentProjectId,
  openCaseConfirmation,
  openProjectFeatures,
  refreshStatus,
  setCurrentProject,
  syncFeatureProjects,
  toast,
  uiPrompt,
  updateBackbar,
} from "../../../lib/compatBridge.js";
import { escapeHtml } from "../../../lib/html.js";
import { deletedText, pickCurrent, statsText } from "../lib/projects.js";

/**
 * Projects screen: project cards, the detail header, rename / delete and the
 * page switch (list / create / detail). Registered while mounted (called by
 * navigation and other screens; nothing loads on mount):
 *   window.loadProjects()            — reload; keeps window.allProjects and the runtime project in step
 *   window.showProjectList()         — back to the cards
 *   window.showProjectCreate()       — the create wizard (empty-state button)
 *   window.openProjectSettings(pid)  — project settings (also window.selectProject)
 *
 * page: "list" | "create" | "detail"
 */
export default function useProjects(settings) {
  const [projects, setProjects] = useState([]);
  const [loaded, setLoaded] = useState(false);
  const [loading, setLoading] = useState(false);
  const [activeId, setActiveId] = useState("");
  const [caseCount, setCaseCount] = useState("—");
  const [page, setPageState] = useState("list");
  const [openMenu, setOpenMenu] = useState(null);
  const pageRef = useRef("list");
  const loadedRef = useRef(false);
  const caseSeq = useRef(0);
  // Project settings (useProjectSettings): repo list reload and the provider / PAT panel.
  const settingsRef = useRef(settings);
  settingsRef.current = settings;

  const setPage = useCallback((p) => {
    pageRef.current = p;
    setPageState(p);
  }, []);

  // The backbar / breadcrumbs (app/navigation.js) read #project-detail-page.hidden, so
  // they are redrawn once the page switch is on screen.
  const [pageTick, setPageTick] = useState(0);
  useEffect(() => {
    if (pageTick) updateBackbar();
  }, [pageTick]);
  const showPage = useCallback(
    (p) => {
      setPage(p);
      setPageTick((t) => t + 1);
    },
    [setPage],
  );

  const loadProjects = useCallback(async () => {
    if (!loadedRef.current) setLoading(true);
    let list;
    try {
      const r = await api("/api/projects");
      list = r.projects;
    } catch {
      return;
    }
    window.allProjects = list;
    loadedRef.current = true;
    const cur = pickCurrent(list, currentProjectId());
    setCurrentProject(cur);
    syncFeatureProjects(list, cur);
    setProjects(list);
    setLoaded(true);
    setLoading(false);
    setActiveId(cur);
    setOpenMenu(null);
    const my = ++caseSeq.current;
    if (cur) {
      api(`/api/test-cases?project_id=${cur}&status=all&limit=1`)
        .then((x) => my === caseSeq.current && setCaseCount(x.total))
        .catch(() => my === caseSeq.current && setCaseCount("—"));
    } else setCaseCount("—");
    if (pageRef.current === "detail" && settingsRef.current) settingsRef.current.loadRepos();
    setPageTick((t) => t + 1);
  }, []);

  const showProjectList = useCallback(() => showPage("list"), [showPage]);
  const showProjectCreate = useCallback(() => showPage("create"), [showPage]);

  const openProjectSettings = useCallback(
    async (pid) => {
      setCurrentProject(pid);
      showPage("detail");
      await loadProjects();
      if (settingsRef.current) await settingsRef.current.open(pid);
    },
    [loadProjects, showPage],
  );

  useEffect(() => {
    const hooks = {
      loadProjects: () => loadProjects(),
      showProjectList: () => showProjectList(),
      showProjectCreate: () => showProjectCreate(),
      openProjectSettings: (pid) => openProjectSettings(pid),
    };
    hooks.selectProject = hooks.openProjectSettings;
    Object.assign(window, hooks);
    return () => {
      for (const [k, fn] of Object.entries(hooks)) if (window[k] === fn) delete window[k];
    };
  }, [loadProjects, openProjectSettings, showProjectCreate, showProjectList]);

  // A click outside every project card, or Escape, closes the card menu.
  useEffect(() => {
    if (!openMenu) return;
    const onClick = (e) => {
      if (!e.target.closest("[data-project-card]")) setOpenMenu(null);
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

  const active = projects.find((p) => p.id === activeId) || null;
  // Before the first load the header shows the placeholder "Project".
  const activeTitle = active ? active.name : loaded ? "" : "Project";
  const activeStats = active ? statsText(active) : "";

  const rename = async (pid, current, successText) => {
    const name = await uiPrompt("Rename project", "New name for the project", current);
    if (!name) return;
    try {
      await api(`/api/projects/${pid}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
      });
      loadProjects();
      toast(successText);
    } catch (e) {
      toast(e.message, { type: "err", title: "Couldn't rename project" });
    }
  };

  const confirmDelete = (pid, copy, summary) =>
    openCaseConfirmation({
      title: "Delete project",
      copy,
      summary,
      confirmLabel: "Delete project",
      danger: true,
      onConfirm: async () => {
        const r = await api(`/api/projects/${pid}`, { method: "DELETE" });
        setCurrentProject(null);
        showProjectList();
        loadProjects();
        refreshStatus();
        toast(deletedText(r));
      },
    });

  const cardName = (pid) => (projects.find((p) => p.id === pid)?.name || "").trim() || "Project";

  return {
    projects,
    loaded,
    loading,
    page,
    openMenu,
    active,
    activeTitle,
    activeStats,
    caseCount,
    loadProjects,
    showProjectList,
    showProjectCreate,
    toggleMenu: (pid) => setOpenMenu((m) => (m === pid ? null : pid)),
    openFeatures: (pid) => openProjectFeatures(pid),
    openSettings: openProjectSettings,
    renameFromCard: (pid) => rename(pid, cardName(pid), "Project renamed"),
    deleteFromCard: (pid) => {
      setCurrentProject(pid);
      confirmDelete(
        pid,
        "This removes this project, its features, repositories, and project-only test-case links. Test cases linked to another project remain available.",
        `<b>${escapeHtml(cardName(pid))}</b>`,
      );
    },
    renameActive: () => {
      const pid = currentProjectId();
      if (!pid) return;
      rename(pid, activeTitle, "Project renamed successfully!");
    },
    deleteActive: () => {
      const pid = currentProjectId();
      if (!pid) return;
      confirmDelete(
        pid,
        "This removes this project, its features, repositories, and project-only test-case links. Test cases linked to features in another project will remain.",
        `<b>${escapeHtml(activeTitle)}</b><div class="muted" style="margin-top:6px">${escapeHtml(activeStats)}</div>`,
      );
    },
  };
}
