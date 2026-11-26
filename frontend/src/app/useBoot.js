import { useEffect, useRef } from "react";
import { api } from "../lib/api.js";
import {
  currentUser,
  navigateTo,
  openChangePasswordModal,
  refreshMe,
  refreshStatus,
  setCurrentFeature,
  setCurrentProject,
  showLogin,
  toast,
} from "../lib/compatBridge.js";
import { runBoot, startApp, watchFields } from "./boot.js";

const callWindow = (name, ...args) => (typeof window[name] === "function" ? window[name](...args) : undefined);

const deps = () => ({
  api: (p, o) => api(p, o),
  fetch: (...a) => fetch(...a),
  currentUser,
  checkAuth: () => callWindow("checkAuth"),
  maybeShowInvite: () => callWindow("maybeShowInvite"),
  showLogin,
  toast,
  openChangePasswordModal,
  refreshStatus,
  navigateTo,
  setCurrentProject,
  setCurrentFeature,
  location: window.location,
  history: window.history,
  storage: window.localStorage,
  session: window.sessionStorage,
  document,
});

/**
 * App start-up (was compat/runtime/controllers/16-boot.js). On mount: field
 * hardening, window.startApp (sign-in and invitations call it), the 5 s
 * service-status refresh and the 30 s identity refresh while signed in; then
 * the boot sequence, once. App calls it after every screen and overlay has
 * registered its window functions (child effects run first).
 */
export function useBoot() {
  const started = useRef(false);

  useEffect(() => {
    const stopFields = watchFields(document, MutationObserver);
    const start = () => startApp(deps());
    window.startApp = start;
    const status = setInterval(() => {
      if (currentUser()) refreshStatus();
    }, 5000);
    // Admin-side role / disable changes apply within ~30 s even without a focus event.
    const identity = setInterval(() => {
      if (currentUser()) refreshMe();
    }, 30000);
    return () => {
      stopFields();
      clearInterval(status);
      clearInterval(identity);
      if (window.startApp === start) delete window.startApp;
    };
  }, []);

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    runBoot(deps());
  }, []);
}
