import { useEffect } from "react";
import { renderJobLog, usageLogLines, watchJob } from "./jobs.js";
import { loadingRow, skIn, skeleton } from "./skeleton.js";
import { brandLoader, startBrandTicker } from "./brandLoader.js";
import { prioBadge, stepsHtml } from "./htmlRenderers.js";

/**
 * Registers shared helpers on window, where lib/compatBridge.js, the compat
 * runtime (13-gap-analysis.js) and tests look them up: the job helpers, the
 * skeleton placeholders, the branded loader and the priority / steps HTML.
 * Also runs the branded-loader message ticker. Mounted once by App.
 */
export function useSharedGlobals() {
  useEffect(() => {
    const fns = { watchJob, renderJobLog, usageLogLines, skeleton, skIn, loadingRow, brandLoader, prioBadge, stepsHtml };
    Object.assign(window, fns);
    const stopTicker = startBrandTicker();
    return () => {
      stopTicker();
      for (const [k, fn] of Object.entries(fns)) if (window[k] === fn) delete window[k];
    };
  }, []);
}
