import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "../../../lib/api.js";
import { loadProjects } from "../../../lib/compatBridge.js";
import {
  DEFAULT_FILTERS,
  buildCaseQuery,
  filterSummary,
  pageCount,
  projectOptionLabel,
} from "../lib/testCases.js";

/**
 * Test Cases screen state (was initCases / fillFeatFilter / loadCases in
 * 04-test-cases.js).
 *
 * The compat runtime still drives this screen from outside, so while mounted
 * the hook registers:
 *   window.initCases()            — navigateTo("cases") in app/navigation.js
 *   window.loadCases()            — after a case is saved / deleted (04, 07, 03)
 *   window.fillFeatFilter()       — kept for callers of the old name
 *   window.openTestCasesFor(f, p) — "Test cases" link in the feature workspace (03)
 * Nothing is fetched on mount: every view is mounted (hidden) at start-up.
 *
 * Behaviour kept from the old screen:
 *   - opening the screen resets Project, Feature and Tag (their option lists are
 *     reloaded) but keeps the other filters and the page;
 *   - while a page loads, and when it fails, the summary and pager keep their
 *     previous values.
 */
export default function useTestCases() {
  const [filters, setFiltersState] = useState(DEFAULT_FILTERS);
  const [projects, setProjects] = useState([]);
  const [features, setFeatures] = useState([]);
  const [tags, setTags] = useState([]);
  const [list, setList] = useState({ status: "idle", items: [], error: "", seq: 0 });
  const [summary, setSummary] = useState("");
  const [pager, setPager] = useState(null);

  const mounted = useRef(false);
  const filtersRef = useRef(DEFAULT_FILTERS);
  const pageRef = useRef(0);
  const loadSeq = useRef(0);
  const featSeq = useRef(0);
  const initSeq = useRef(0);
  const labels = useRef({ projects: [], features: [] });

  const setFilters = useCallback((patch) => {
    filtersRef.current = { ...filtersRef.current, ...patch };
    if (mounted.current) setFiltersState(filtersRef.current);
  }, []);

  const loadCases = useCallback(async () => {
    const my = ++loadSeq.current;
    const f = filtersRef.current;
    const page = pageRef.current;
    if (mounted.current) setList((s) => ({ ...s, status: "loading" }));
    try {
      const r = await api("/api/test-cases?" + buildCaseQuery(f, page));
      if (!mounted.current || my !== loadSeq.current) return;
      const project = labels.current.projects.find((p) => p.id === f.project);
      const feature = labels.current.features.find((x) => x.id === f.feature);
      setList({ status: "ready", items: r.items, error: "", seq: my });
      setSummary(
        filterSummary(r.total, f, {
          projectText: project ? projectOptionLabel(project) : "",
          featureText: feature ? feature.name : "",
        }),
      );
      setPager({ total: r.total, page, pages: pageCount(r.total) });
    } catch (e) {
      if (mounted.current && my === loadSeq.current)
        setList((s) => ({ ...s, status: "error", error: e.message }));
    }
  }, []);

  const fillFeatFilter = useCallback(async () => {
    const my = ++featSeq.current;
    try {
      const pf = filtersRef.current.project;
      const r = await api("/api/features" + (pf ? `?project_id=${pf}` : ""));
      if (!mounted.current || my !== featSeq.current) return;
      labels.current.features = r.features;
      setFeatures(r.features);
      setFilters({ feature: "" });
    } catch {
      /* the old screen kept the previous options */
    }
  }, [setFilters]);

  const initCases = useCallback(async () => {
    const my = ++initSeq.current;
    const projectList = await loadProjects();
    if (!mounted.current || my !== initSeq.current) return;
    labels.current.projects = projectList;
    setProjects(projectList);
    setFilters({ project: "" });
    try {
      const t = await api("/api/tags");
      if (mounted.current && my === initSeq.current) {
        setTags(t.tags);
        setFilters({ tag: "" });
      }
    } catch {
      /* keep the previous tags */
    }
    if (!mounted.current || my !== initSeq.current) return;
    await fillFeatFilter();
    if (!mounted.current || my !== initSeq.current) return;
    loadCases();
    return my;
  }, [fillFeatFilter, loadCases, setFilters]);

  const openFor = useCallback(
    async (featureId, projectId) => {
      const my = await initCases();
      if (!my || my !== initSeq.current) return;
      setFilters({ project: projectId || "" });
      await fillFeatFilter();
      if (!mounted.current || my !== initSeq.current) return;
      setFilters({ ...DEFAULT_FILTERS, project: projectId || "", feature: featureId || "" });
      pageRef.current = 0;
      loadCases();
    },
    [fillFeatFilter, initCases, loadCases, setFilters],
  );

  useEffect(() => {
    mounted.current = true;
    const hooks = {
      initCases: () => initCases(),
      loadCases: () => loadCases(),
      fillFeatFilter: () => fillFeatFilter(),
      openTestCasesFor: (fid, pid) => openFor(fid, pid),
    };
    Object.assign(window, hooks);
    return () => {
      mounted.current = false;
      for (const [k, fn] of Object.entries(hooks)) if (window[k] === fn) delete window[k];
    };
  }, [fillFeatFilter, initCases, loadCases, openFor]);

  /** A select changed: page 0, reload (project also reloads the features). */
  const changeFilter = useCallback(
    async (key, value) => {
      if (key === "project") {
        setFilters({ project: value, feature: "" });
        await fillFeatFilter();
      } else setFilters({ [key]: value });
      pageRef.current = 0;
      loadCases();
    },
    [fillFeatFilter, loadCases, setFilters],
  );

  const setQuery = useCallback((q) => setFilters({ q }), [setFilters]);

  const apply = useCallback(() => {
    pageRef.current = 0;
    loadCases();
  }, [loadCases]);

  const reset = useCallback(async () => {
    setFilters({ ...DEFAULT_FILTERS, feature: filtersRef.current.feature });
    pageRef.current = 0;
    await fillFeatFilter();
    setFilters({ feature: "" });
    loadCases();
  }, [fillFeatFilter, loadCases, setFilters]);

  const prevPage = useCallback(() => {
    if (pageRef.current > 0) {
      pageRef.current -= 1;
      loadCases();
    }
  }, [loadCases]);

  const nextPage = useCallback(() => {
    if (pager && pageRef.current < pager.pages - 1) {
      pageRef.current += 1;
      loadCases();
    }
  }, [loadCases, pager]);

  return {
    filters,
    projects,
    features,
    tags,
    list,
    summary,
    pager,
    changeFilter,
    setQuery,
    apply,
    reset,
    prevPage,
    nextPage,
    reload: loadCases,
  };
}
