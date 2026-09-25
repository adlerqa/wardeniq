import { useEffect } from "react";
import chunk00 from "./controllers/00-core.js?raw";
import chunk01 from "./controllers/01-dashboard.js?raw";
import chunk02 from "./controllers/02-projects.js?raw";
import chunk03 from "./controllers/03-features-and-usage.js?raw";
import chunk04 from "./controllers/04-test-cases.js?raw";
import chunk05 from "./controllers/05-step-workflows.js?raw";
import chunk06 from "./controllers/06-configuration.js?raw";
import chunk07 from "./controllers/07-library-and-crud.js?raw";
import chunk08 from "./controllers/08-code-analysis-and-cycles.js?raw";
import chunk09 from "./controllers/09-mind-map-and-jobs.js?raw";
import chunk10 from "./controllers/10-auth.js?raw";
import chunk11 from "./controllers/11-users.js?raw";
import chunk12 from "./controllers/12-validator.js?raw";
import chunk13 from "./controllers/13-gap-analysis.js?raw";
import chunk14 from "./controllers/14-test-plan.js?raw";
import chunk15 from "./controllers/15-imports.js?raw";
import chunk16 from "./controllers/16-boot.js?raw";
import chunk17 from "./controllers/17-api-tokens.js?raw";

const runtimeChunks = [chunk00, chunk01, chunk02, chunk03, chunk04, chunk05, chunk06, chunk07, chunk08, chunk09, chunk10, chunk11, chunk12, chunk13, chunk14, chunk15, chunk16, chunk17];

/**
 * Compatibility bridge for behavior that has not yet been migrated to React
 * state/hooks. Source is maintained in small domain controllers, then combined
 * in original order at runtime so the existing shared global contract remains
 * byte-for-byte compatible with the uploaded Piyush build.
 */
export default function RuntimeBridge() {
  useEffect(() => {
    if (window.__WARDENIQ_RUNTIME_READY__) return;
    window.__WARDENIQ_RUNTIME_READY__ = true;

    const script = document.createElement("script");
    script.dataset.wardeniqRuntime = "compat";
    script.textContent = `${runtimeChunks.join("\n")}\n//# sourceURL=wardeniq-compat-runtime.js`;
    document.body.appendChild(script);

    // No teardown: the preserved runtime has a single-page lifecycle and owns
    // long-lived listeners/timers. React StrictMode may replay this effect in
    // development, so the module-level window guard prevents double wiring.
  }, []);

  return null;
}
