import { useEffect, useRef, useState } from "react";
import { api } from "../lib/api.js";
import { formatBootStatus, statusFailureBanner } from "../lib/bootStatus.js";

const HIDDEN = { visible: false };

/**
 * Header service chips and the boot banner (was 00-core.js refreshStatus).
 * Registers window.refreshStatus() — called at start-up, every 5 s while signed
 * in, and after changes that move the counts — and window.formatBootStatus.
 *
 * status: { phase: "idle" | "loading" | "ready" | "unavailable", data }
 *   "loading" / "unavailable" only show until the first successful load.
 * banner: formatBootStatus() shape ({ visible, kind, summary, raw }).
 */
export function useServiceStatus() {
  const [status, setStatus] = useState({ phase: "idle", data: null });
  const [banner, setBanner] = useState(HIDDEN);
  const loaded = useRef(false);

  useEffect(() => {
    const show = (formatted) => {
      if (formatted && formatted.visible && formatted.raw) {
        try {
          console.warn("[wardenIQ] boot detail:", formatted.raw);
        } catch {
          /* console unavailable */
        }
      }
      setBanner(formatted && formatted.visible ? formatted : HIDDEN);
    };
    const refreshStatus = async () => {
      if (!loaded.current) setStatus({ phase: "loading", data: null });
      try {
        const s = await api("/api/status");
        loaded.current = true;
        setStatus({ phase: "ready", data: s });
        show(formatBootStatus(s.boot));
      } catch (e) {
        show(statusFailureBanner(e && e.message));
        if (!loaded.current) setStatus({ phase: "unavailable", data: null });
      }
    };
    const fns = { refreshStatus, formatBootStatus };
    Object.assign(window, fns);
    return () => {
      for (const [k, fn] of Object.entries(fns)) if (window[k] === fn) delete window[k];
    };
  }, []);

  return { status, banner };
}
