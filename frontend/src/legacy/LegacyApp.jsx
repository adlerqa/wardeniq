import { useEffect, useRef } from "react";
import { LEGACY_SHELL_HTML } from "./legacyShellHtml.js";
// Import the legacy JS as a raw string (Vite `?raw`) instead of executing it as
// a module. We inject it as a classic <script> element below so it runs in the
// page's GLOBAL scope — exactly like app/static/index.html did. That is what
// makes every top-level `function foo(){}` reachable from the inline on*
// handlers in the shell markup (e.g. onclick="navigateTo(...)"). Importing it
// as a module instead would trap those declarations in module scope and break
// every inline handler with "ReferenceError: <fn> is not defined".
import LEGACY_APP_JS from "./legacyApp.js?raw";

// Module-level guard so React 18 StrictMode's intentional double-invoke of
// effects in dev does not re-inject the legacy DOM (which would strand the
// event handlers the legacy JS attached to the first copy of each element).
let __mounted = false;

// LegacyApp — mounts the untouched legacy shell markup (login gate, sidebar,
// header, all view sections, and modals) into a container ref, then runs the
// legacy JS once as a global-scope <script>. Every id/class the legacy code
// queries resolves against the injected DOM, and every global function the
// inline handlers call resolves against the window — so behavior is identical
// to the pre-migration index.html.
//
// This is deliberately a "vessel" component. As views are refactored into
// idiomatic React under src/features/<name>/, remove their fragments from
// legacyShellHtml.js and their init logic from legacyApp.js in the same PR.
export default function LegacyApp() {
  const rootRef = useRef(null);

  useEffect(() => {
    if (!rootRef.current) return;
    // Guard against React 18 StrictMode's double-effect: on the second run we
    // must NOT re-inject the markup or re-run the script, because the legacy JS
    // has already wired its onclick / addEventListener handlers to the first
    // copy of each element. Re-injecting would swap in fresh DOM nodes with no
    // handlers — exactly the "sign-in button does nothing" symptom.
    if (__mounted) return;
    __mounted = true;

    // 1) Inject the shell markup (login, sidebar, header, views, modals).
    rootRef.current.innerHTML = LEGACY_SHELL_HTML;

    // 2) Run the legacy JS in GLOBAL scope by appending a classic <script>.
    //    A script element created via createElement + textContent DOES execute
    //    when appended to the document (unlike scripts set via innerHTML). The
    //    shell DOM already exists above, so getElementById lookups resolve, and
    //    top-level `function` declarations land on window for inline handlers.
    const el = document.createElement("script");
    el.textContent = LEGACY_APP_JS;
    document.body.appendChild(el);

    // No teardown: the legacy code assumes a single-page lifespan. If the
    // container ever unmounts (e.g. via HMR), Vite falls back to a full page
    // reload for this ES-module boundary anyway.
  }, []);

  return <div ref={rootRef} className="legacy-root" />;
}
