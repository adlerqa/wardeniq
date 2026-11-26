import { useEffect, useState, useSyncExternalStore } from "react";
import { api, cleanErr } from "../lib/api.js";
import { escapeHtml } from "../lib/html.js";
import { installNavGlobals, nav, navFunctions } from "./navState.js";
import {
  clickBreadcrumb,
  getProjectName,
  goToFeatureWorkspace,
  goToProjectFeatures,
  goToProjects,
  gotoAnalyze,
  navigateTo,
  onBackbar,
  updateBackbar,
} from "./navigation.js";

/**
 * Registers navigation and the shared state on window (was 00-core.js), for
 * lib/compatBridge.js, the screens and the Gap Analysis compat controller —
 * which also gets $, esc and api as globals. Returns the back bar model.
 * Mounted once, by ApplicationFrame.
 */
export function useNavigation() {
  const [backbar, setBackbar] = useState({ show: false, onBack: null, crumbs: [] });
  useEffect(() => {
    const fns = {
      ...navFunctions,
      navigateTo,
      updateBackbar,
      renderBreadcrumbs: updateBackbar,
      getProjectName,
      goToProjects,
      gotoAnalyze,
      goToProjectFeatures,
      goToFeatureWorkspace,
      clickBreadcrumb,
      // For 13-gap-analysis.js until it moves to React.
      $: (s) => document.querySelector(s),
      esc: escapeHtml,
      api: (p, o) => api(p, o),
      cleanErr,
    };
    Object.assign(window, fns);
    const uninstall = installNavGlobals(window);
    const off = onBackbar(setBackbar);
    return () => {
      off();
      uninstall();
      for (const [k, fn] of Object.entries(fns)) if (window[k] === fn) delete window[k];
    };
  }, []);
  return backbar;
}

/** The page title navigation set, or `fallback` before the first navigation. */
export function useViewTitle(fallback) {
  const title = useSyncExternalStore(nav.subscribe, () => nav.get().title);
  return title == null ? fallback : title;
}
