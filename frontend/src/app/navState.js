/**
 * Where the user is (was the `let` state in compat/runtime/controllers/00-core.js):
 * the open project and feature, the feature's data, the view on screen, the
 * signed-in user, and the page title set by navigation.
 *
 * Screens reach it through lib/compatBridge.js (getCurrentProject, …), which
 * useNavigation registers on window, or import `nav` directly.
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

/** The accessor functions registered on window for lib/compatBridge.js. */
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
