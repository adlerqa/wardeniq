import { useEffect } from "react";
import { renderJobLog, usageLogLines, watchJob } from "./jobs.js";
import { loadingRow, skIn, skeleton } from "./skeleton.js";

/**
 * Registers shared helpers on window, where lib/compatBridge.js, the compat
 * runtime (13-gap-analysis.js) and tests look them up: the job helpers and the
 * skeleton placeholders. Mounted once by App.
 */
export function useSharedGlobals() {
  useEffect(() => {
    const fns = { watchJob, renderJobLog, usageLogLines, skeleton, skIn, loadingRow };
    Object.assign(window, fns);
    return () => {
      for (const [k, fn] of Object.entries(fns)) if (window[k] === fn) delete window[k];
    };
  }, []);
}
