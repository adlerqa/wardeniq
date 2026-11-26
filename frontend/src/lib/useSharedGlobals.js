import { useEffect } from "react";
import { renderJobLog, usageLogLines, watchJob } from "./jobs.js";
import { brandLoader, startBrandTicker } from "./brandLoader.js";

/**
 * Registers shared helpers on window, where lib/compatBridge.js and tests look
 * them up: the job helpers and the branded loader. Also runs the
 * branded-loader message ticker. Mounted once by App.
 */
export function useSharedGlobals() {
  useEffect(() => {
    const fns = { watchJob, renderJobLog, usageLogLines, brandLoader };
    Object.assign(window, fns);
    const stopTicker = startBrandTicker();
    return () => {
      stopTicker();
      for (const [k, fn] of Object.entries(fns)) if (window[k] === fn) delete window[k];
    };
  }, []);
}
