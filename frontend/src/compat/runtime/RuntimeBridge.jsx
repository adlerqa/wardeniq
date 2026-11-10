import { useEffect } from "react";

// Vite exposes the controller sources as lazy raw-text imports for the runtime.
const controllerModules = import.meta.glob(
  './controllers/*.js',
  {query: '?raw', import: 'default'}
);

let runtimeLoadPromise;

// Load controllers in filename order and share the pending load across effects.
function loadRuntime() {
  if (window.__WARDENIQ_RUNTIME_READY__) return Promise.resolve();
  if (!runtimeLoadPromise) {
    const modules = Object.entries(controllerModules).sort(([a], [b]) =>
      a.localeCompare(b),
    );
    if (modules.length === 0) {
      return Promise.reject(new Error("No compatibility runtime controllers found."));
    }

    runtimeLoadPromise = Promise.all(modules.map(([, load]) => load()))
      .then((runtimeChunks) => {
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
  useEffect(() => {
    if (window.__WARDENIQ_RUNTIME_READY__) return;
    loadRuntime().catch((error) => {
      console.error("Failed to load the WardenIQ compatibility runtime.", error);
    });

    // No teardown: the preserved runtime has a single-page lifecycle and owns
    // long-lived listeners/timers. React StrictMode may replay this effect in
    // development, so the module-level window guard prevents double wiring.
  }, []);

  return null;
}
