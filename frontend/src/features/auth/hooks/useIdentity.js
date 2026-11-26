import { useEffect, useState } from "react";
import { api } from "../../../lib/api.js";
import {
  currentUser,
  currentViewName,
  navigateTo,
  setCurrentUser,
  showLogin,
  toast,
} from "../../../lib/compatBridge.js";
import { applyRoleDom, applyRoleTooltips, enforceViewerReadOnly } from "../lib/identity.js";

const ADMIN_ONLY_VIEWS = ["users", "config"];

/**
 * The signed-in user's role in the page (was the identity half of
 * compat/runtime/controllers/10-auth.js). Mounted once, by the Header.
 *
 * Registers on window, for the compat runtime and other screens:
 *   applyRole()               — header user menu + role-dependent page state
 *   checkAuth()               — load the signed-in user at boot (true) or show sign-in (false)
 *   refreshMe()               — re-read the user so an admin's role change / disable applies live
 *   enforceViewerReadOnly()   — mark write buttons in the visible view for viewers
 *   applyRoleTooltips(role)
 * refreshMe also runs when the window regains focus.
 *
 * Returns the user the header shows: set by applyRole only, as before.
 */
export function useIdentity() {
  const [shown, setShown] = useState(null);

  useEffect(() => {
    const applyRole = () => {
      const user = currentUser();
      setShown(user ? { ...user } : null);
      applyRoleDom(user);
    };

    const checkAuth = async () => {
      try {
        const r = await api("/api/auth/me");
        if (!r.user) throw new Error("not signed in"); // the legacy applyRole threw here too
        setCurrentUser(r.user);
        const login = document.getElementById("login");
        if (login) login.hidden = true;
        applyRole();
        return true;
      } catch {
        showLogin();
        return false;
      }
    };

    let refreshing = false;
    const refreshMe = async () => {
      if (refreshing || !currentUser()) return;
      refreshing = true;
      try {
        const r = await fetch("/api/auth/me", {
          method: "GET",
          credentials: "include", // make sure the session cookie is sent
          headers: { Accept: "application/json" },
        });
        if (r.status === 401) {
          console.warn("[Auth] /api/auth/me returned 401. Session cookie may be missing or invalid.");
          setCurrentUser(null);
          showLogin();
          toast("Your session ended — please sign in again.", true);
          return;
        }
        if (!r.ok) {
          // A temporary server error must not sign the user out.
          console.warn(`[Auth] Identity refresh failed with status ${r.status}`);
          return;
        }
        const j = await r.json();
        if (!j?.user) {
          console.warn("[Auth] /api/auth/me did not return a user.");
          return;
        }
        const prevRole = currentUser()?.role;
        setCurrentUser(j.user);
        if (j.user.role !== prevRole) {
          applyRole();
          toast(`Your role is now "${j.user.role}".`);
          const view = currentViewName();
          try {
            navigateTo(j.user.role !== "admin" && ADMIN_ONLY_VIEWS.includes(view) ? "dashboard" : view);
          } catch {
            /* navigation is best-effort */
          }
        }
      } catch (e) {
        // A network failure must not end the session.
        console.warn("[Auth] Unable to refresh session:", e);
      } finally {
        refreshing = false;
      }
    };

    const fns = {
      applyRole,
      checkAuth,
      refreshMe,
      enforceViewerReadOnly: () => enforceViewerReadOnly(currentUser()),
      applyRoleTooltips: (role) => applyRoleTooltips(role),
    };
    Object.assign(window, fns);
    const onFocus = () => {
      try {
        refreshMe();
      } catch {
        /* best-effort */
      }
    };
    window.addEventListener("focus", onFocus);
    return () => {
      window.removeEventListener("focus", onFocus);
      for (const [k, fn] of Object.entries(fns)) if (window[k] === fn) delete window[k];
    };
  }, []);

  return shown;
}
