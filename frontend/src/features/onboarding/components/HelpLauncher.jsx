import { useEffect, useRef, useState, useSyncExternalStore } from "react";

import { SHOW_CHECKLIST_EVENT, goTo, isSignedIn } from "../appBridge.js";
import { SETUP_DISMISS_KEY } from "../setupSteps.js";
import { writeFlag } from "../storage.js";
import { getTourState, requestTour, subscribeTour } from "../tourStore.js";

/**
 * Floating "?" button (bottom left, clear of the toasts at the bottom right)
 * to restart the guided tour or bring back the setup checklist (issue #254).
 * Shown only after sign-in and hidden while a tour is running.
 */
export default function HelpLauncher() {
  const tour = useSyncExternalStore(subscribeTour, getTourState);
  const [signedIn, setSignedIn] = useState(isSignedIn);
  const [open, setOpen] = useState(false);
  const wrapRef = useRef(null);
  const buttonRef = useRef(null);

  // #usermenu is un-hidden by applyRole() after sign-in (compat 10-auth.js).
  useEffect(() => {
    const update = () => setSignedIn(isSignedIn());
    update();
    const menu = document.getElementById("usermenu");
    const observer = new MutationObserver(update);
    if (menu) observer.observe(menu, { attributes: true, attributeFilter: ["hidden"] });
    return () => observer.disconnect();
  }, []);

  // Close the menu on outside click or Escape.
  useEffect(() => {
    if (!open) return undefined;
    const onDown = (e) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false);
    };
    const onKey = (e) => {
      if (e.key === "Escape") {
        setOpen(false);
        buttonRef.current && buttonRef.current.focus();
      }
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  // While a tour runs, the explore chapter points at this button, so keep it
  // in the DOM but out of the way of clicks.
  if (!signedIn) return null;

  const startTour = () => {
    setOpen(false);
    requestTour(null);
  };
  const showChecklist = () => {
    setOpen(false);
    writeFlag(SETUP_DISMISS_KEY, false);
    goTo("dashboard");
    window.dispatchEvent(new Event(SHOW_CHECKLIST_EVENT));
  };

  return (
    <div ref={wrapRef} className="fixed bottom-5 left-5 z-[40]">
      {open && (
        <div
          id="wq-help-menu"
          role="menu"
          aria-label="Help"
          className="absolute bottom-12 left-0 w-56 rounded-xl border border-solid border-line bg-panel p-2 shadow-2xl"
        >
          <button type="button" role="menuitem" className="ghost w-full text-left" onClick={startTour}>
            Start the guided tour
          </button>
          <button type="button" role="menuitem" className="ghost mt-1 w-full text-left" onClick={showChecklist}>
            Show setup checklist
          </button>
        </div>
      )}
      <button
        ref={buttonRef}
        id="wq-help-launcher"
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls="wq-help-menu"
        aria-label="Help and guided tour"
        title="Help and guided tour"
        disabled={tour.status !== "idle"}
        onClick={() => setOpen((v) => !v)}
        className="flex h-10 w-10 items-center justify-center rounded-full border border-solid border-line bg-panel text-base font-semibold text-text shadow-lg"
      >
        ?
      </button>
    </div>
  );
}
