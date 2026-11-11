import { useEffect, useRef, useState } from "react";

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

const runtimeChunks = [
  chunk00, chunk01, chunk02, chunk03, chunk04, chunk05,
  chunk06, chunk07, chunk08, chunk09, chunk10, chunk11,
  chunk12, chunk13, chunk14, chunk15, chunk16, chunk17,
];

let runtimeLoadPromise;

// Share the pending injection across effects, including StrictMode replays.
function loadRuntime() {
  if (window.__WARDENIQ_RUNTIME_READY__) return Promise.resolve();
  if (!runtimeLoadPromise) {
    runtimeLoadPromise = Promise.resolve()
      .then(() => {
        if (window.__WARDENIQ_RUNTIME_READY__) return;

        // A classic script keeps the concatenated controllers in their shared global scope.
        const script = document.createElement("script");
        script.dataset.wardeniqRuntime = "compat";
        script.textContent = `${runtimeChunks.join("\n")}\n//# sourceURL=wardeniq-compat-runtime.js`;
        document.body.appendChild(script);
        window.__WARDENIQ_RUNTIME_READY__ = true;
      })
      .catch((error) => {
        runtimeLoadPromise = undefined;
        throw error;
      });
  }
  return runtimeLoadPromise;
}

/**
 * Compatibility bridge for behavior that has not yet been migrated to React
 * state/hooks. Source is maintained in small domain controllers, then combined
 * in original order at runtime so the existing shared global contract remains
 * intact.
 */
export default function RuntimeBridge() {
  const [attempt, setAttempt] = useState(0);
  const [failed, setFailed] = useState(false);
  const [pending, setPending] = useState(true);
  const retryPending = useRef(true);

  useEffect(() => {
    let active = true;
    loadRuntime().then(
      () => {
        if (!active) return;
        retryPending.current = false;
        setFailed(false);
        setPending(false);
      },
      (error) => {
        if (!active) return;
        console.error("Failed to load the WardenIQ compatibility runtime.", error);
        retryPending.current = false;
        setFailed(true);
        setPending(false);
      },
    );

    // Unsubscribe this effect, but keep the runtime's single-page listeners/timers.
    // The shared loader and window guard prevent StrictMode from double wiring.
    return () => {
      active = false;
    };
  }, [attempt]);

  function retry() {
    if (retryPending.current) return;
    retryPending.current = true;
    setPending(true);
    setAttempt((previous) => previous + 1);
  }

  if (!failed) return null;

  return (
    <div
      role="alert"
      aria-busy={pending}
      className="fixed inset-x-4 top-4 z-[10000] mx-auto max-w-lg rounded-xl border border-rose-400/30 bg-slate-900 p-5 text-slate-100 shadow-2xl"
    >
      <h2 className="text-lg font-semibold">WardenIQ could not initialize.</h2>
      <p className="mt-2 text-sm text-slate-300">
        Retry to finish starting the application. If the problem continues, check
        the browser console for details.
      </p>
      <button
        type="button"
        disabled={pending}
        onClick={retry}
        className="mt-4 rounded-lg bg-sky-500 px-4 py-2 text-sm font-semibold text-white transition hover:bg-sky-400 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-400 disabled:cursor-wait disabled:opacity-50"
      >
        {pending ? "Retrying..." : "Retry"}
      </button>
    </div>
  );
}
