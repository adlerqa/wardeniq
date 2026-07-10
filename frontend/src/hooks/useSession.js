import { useCallback, useEffect, useState } from "react";
import { api, setUnauthorizedHandler } from "../lib/api";

// useSession — encapsulates the passwordless OTP auth flow.
//
// Session state has three phases:
//   loading  — first /api/auth/me check is pending
//   guest    — user is not signed in (LoginPage should render)
//   invite   — signed in but has a pending invite (InviteGate should render)
//   ready    — user is fully authenticated with role/permissions
//
// The backend uses signed HTTP-only cookies, so we never store tokens in JS.

export function useSession() {
  const [state, setState] = useState({ phase: "loading", me: null });

  const refresh = useCallback(async () => {
    try {
      const me = await api("/api/auth/me");
      if (me && me.authenticated && me.pending_invite) {
        setState({ phase: "invite", me });
      } else if (me && me.authenticated) {
        setState({ phase: "ready", me });
      } else {
        setState({ phase: "guest", me: null });
      }
    } catch (e) {
      if (e.status === 401) {
        setState({ phase: "guest", me: null });
      } else {
        // Network / backend error — surface as guest but log for debugging.
         
        console.warn("session refresh failed", e);
        setState({ phase: "guest", me: null });
      }
    }
  }, []);

  const signOut = useCallback(async () => {
    try {
      await api("/api/auth/logout", { method: "POST" });
    } finally {
      setState({ phase: "guest", me: null });
    }
  }, []);

  useEffect(() => {
    refresh();
    setUnauthorizedHandler(() => {
      // Any non-auth 401 kicks a refresh, which will move us to `guest`.
      refresh();
    });

    // Match the legacy 30-second identity poll so admin role/disable changes
    // propagate reliably even without focus events.
    const t = setInterval(() => {
      if (state.phase === "ready" || state.phase === "invite") refresh();
    }, 30_000);

    // Refresh on tab focus for near-instant propagation in the common case.
    const onFocus = () => refresh();
    window.addEventListener("focus", onFocus);

    return () => {
      clearInterval(t);
      window.removeEventListener("focus", onFocus);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return { ...state, refresh, signOut };
}
