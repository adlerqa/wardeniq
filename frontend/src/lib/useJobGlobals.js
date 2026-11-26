import { useEffect } from "react";
import { renderJobLog, usageLogLines, watchJob } from "./jobs.js";

/**
 * Registers the job helpers on window (watchJob, renderJobLog,
 * usageLogLines), where lib/compatBridge.js and tests look them up. Mounted
 * once by App.
 */
export function useJobGlobals() {
  useEffect(() => {
    const fns = { watchJob, renderJobLog, usageLogLines };
    Object.assign(window, fns);
    return () => {
      for (const [k, fn] of Object.entries(fns)) if (window[k] === fn) delete window[k];
    };
  }, []);
}
