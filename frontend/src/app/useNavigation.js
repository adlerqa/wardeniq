import { useEffect, useState, useSyncExternalStore } from "react";
import { nav, navFunctions } from "./navState.js";
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
 * lib/compatBridge.js and the screens. Returns the back bar model.
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
    };
    Object.assign(window, fns);
    const off = onBackbar(setBackbar);
    return () => {
      off();
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
