/**
 * Where the user is (was the `let` state in compat/runtime/controllers/00-core.js):
 * the open project and feature, the feature's data, the view on screen, the
 * signed-in user, and the page title set by navigation.
 *
 * React reaches it through lib/compatBridge.js (getCurrentProject, …), which
 * useNavigation registers on window. The Gap Analysis compat controller reads
 * it as bare globals (currentProject, currentFeature, currentFeatureData), so
 * installNavGlobals also defines those as window accessors.
 */
const state = {
  project: null,
  feature: null,
  featureData: null,
  featureCases: [],
  view: "dashboard",
  user: null,
  title: null, // null until the first navigation: the header keeps its default
};
const listeners = new Set();
const emit = () => listeners.forEach((fn) => fn());

export const nav = {
  get: () => state,
  setProject: (id) => {
    state.project = id;
  },
  setFeature: (id) => {
    state.feature = id;
  },
  setFeatureData: (f) => {
    state.featureData = f;
    state.featureCases = (f && f.test_cases) || [];
  },
  setUser: (u) => {
    state.user = u;
  },
  setView: (v) => {
    state.view = v;
  },
  setTitle: (t) => {
    state.title = t;
    emit();
  },
  /** Re-render subscribers (the header title). Returns an unsubscribe function. */
  subscribe: (fn) => {
    listeners.add(fn);
    return () => listeners.delete(fn);
  },
};

/** The accessor functions the bridge and the compat runtime call. */
export const navFunctions = {
  getCurrentProject: () => state.project,
  setCurrentProject: (id) => nav.setProject(id),
  getCurrentFeatureId: () => state.feature,
  setCurrentFeature: (id) => nav.setFeature(id),
  setCurrentFeatureData: (f) => nav.setFeatureData(f),
  getCurrentUser: () => state.user,
  setCurrentUser: (u) => nav.setUser(u),
  getCurrentViewName: () => state.view,
};

const GLOBALS = {
  currentProject: "project",
  currentFeature: "feature",
  currentFeatureData: "featureData",
  currentFeatureCases: "featureCases",
  currentViewName: "view",
  ME: "user",
};

/** Bare-global access for the compat controller. Returns an uninstall function. */
export function installNavGlobals(win) {
  for (const [name, key] of Object.entries(GLOBALS))
    Object.defineProperty(win, name, {
      configurable: true,
      get: () => state[key],
      set: (v) => {
        if (key === "featureData") nav.setFeatureData(v);
        else state[key] = v;
      },
    });
  return () => {
    for (const name of Object.keys(GLOBALS)) delete win[name];
  };
}
