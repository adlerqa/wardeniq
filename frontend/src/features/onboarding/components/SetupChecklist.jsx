import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";

import { SHOW_CHECKLIST_EVENT, goTo, loadEffectiveSetup, readRole } from "../appBridge.js";
import {
  SAMPLE_PRD_URL,
  SETUP_DISMISS_KEY,
  buildSetupSteps,
  canAct,
  checklistState,
  setupProgress,
} from "../setupSteps.js";
import { CHECKLIST_TO_CHAPTER } from "../tourSteps.js";
import {
  getTourState,
  hasSeenTour,
  markTourSeen,
  requestTour,
  subscribeTour,
} from "../tourStore.js";
import WelcomeDialog from "./WelcomeDialog.jsx";

function readDismissed() {
  try {
    return localStorage.getItem(SETUP_DISMISS_KEY) === "1";
  } catch {
    return false;
  }
}

function writeDismissed(value) {
  try {
    if (value) localStorage.setItem(SETUP_DISMISS_KEY, "1");
    else localStorage.removeItem(SETUP_DISMISS_KEY);
  } catch {
    /* storage unavailable: the choice just isn't remembered */
  }
}

function StepMarker({ step, index }) {
  if (step.done) {
    return (
      <span
        aria-hidden="true"
        className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-green text-bg"
      >
        <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="3"
          strokeLinecap="round" strokeLinejoin="round">
          <path d="m5 12 5 5 9-10" />
        </svg>
      </span>
    );
  }
  return (
    <span
      aria-hidden="true"
      className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-solid text-xs font-semibold ${
        step.next ? "border-accent text-accent" : "border-line text-muted"
      }`}
    >
      {index + 1}
    </span>
  );
}

function statusText(step) {
  if (step.done) return "Done";
  if (step.next) return "Next step";
  return step.optional ? "Optional" : "Not done";
}

/**
 * Dashboard "Get started" checklist for new users (issue #254).
 *
 * Reads the effective setup flags (GET /api/dashboard `setup`, plus
 * GET /api/status while the LLM settings were never saved, same rule as the
 * boot gate, #279) and re-reads them each time the Dashboard view is shown.
 * Each unfinished step has a "Show me" button that starts the guided tour at
 * that step. Hidden once every required step is done; can be dismissed and
 * restored. Also hosts the one-time welcome prompt.
 */
export default function SetupChecklist() {
  const rootRef = useRef(null);
  const tour = useSyncExternalStore(subscribeTour, getTourState);
  const [setup, setSetup] = useState(null);
  const [dismissed, setDismissed] = useState(readDismissed);
  const [role, setRole] = useState(readRole);
  const [welcome, setWelcome] = useState(false);

  const load = useCallback(async () => {
    const s = await loadEffectiveSetup();
    if (s) setSetup(s);
    setRole(readRole());
    setDismissed(readDismissed());
  }, []);

  // Reload whenever the Dashboard view becomes visible (navigateTo() toggles
  // the `hidden` attribute on each `.view`), track role changes on <body>, and
  // react to "Show setup checklist" from the help button.
  useEffect(() => {
    const view = rootRef.current && rootRef.current.closest(".view");
    if (view && !view.hidden) load();
    const viewObserver = new MutationObserver(() => {
      if (view && !view.hidden) load();
    });
    if (view) viewObserver.observe(view, { attributes: true, attributeFilter: ["hidden"] });
    const roleObserver = new MutationObserver(() => setRole(readRole()));
    roleObserver.observe(document.body, { attributes: true, attributeFilter: ["class"] });
    window.addEventListener(SHOW_CHECKLIST_EVENT, load);
    return () => {
      viewObserver.disconnect();
      roleObserver.disconnect();
      window.removeEventListener(SHOW_CHECKLIST_EVENT, load);
    };
  }, [load]);

  // Refresh when a tour ends, so steps finished during it tick off.
  useEffect(() => {
    if (tour.status === "idle") {
      const view = rootRef.current && rootRef.current.closest(".view");
      if (view && !view.hidden) load();
    }
  }, [tour.status, load]);

  const state = checklistState(setup, dismissed);

  // Offer the tour once, while setup is incomplete.
  useEffect(() => {
    if (state !== "hidden" && tour.status === "idle" && !hasSeenTour()) setWelcome(true);
  }, [state, tour.status]);

  const dismiss = () => {
    writeDismissed(true);
    setDismissed(true);
  };
  const restore = () => {
    writeDismissed(false);
    setDismissed(false);
  };
  const startTour = useCallback(() => {
    setWelcome(false);
    requestTour(null);
  }, []);
  const skipWelcome = useCallback(() => {
    setWelcome(false);
    markTourSeen();
  }, []);

  const welcomeDialog = welcome ? (
    <WelcomeDialog role={role} setup={setup} onStart={startTour} onDismiss={skipWelcome} />
  ) : null;

  if (state === "hidden") return <div ref={rootRef} hidden />;

  if (state === "collapsed") {
    return (
      <div ref={rootRef} id="setup-checklist" className="mb-4 flex justify-end">
        <button type="button" className="ghost" onClick={restore}>
          Show setup checklist
        </button>
        {welcomeDialog}
      </div>
    );
  }

  const steps = buildSetupSteps(setup);
  const progress = setupProgress(steps);
  const readOnly = role === "viewer";

  return (
    <section
      ref={rootRef}
      id="setup-checklist"
      aria-labelledby="setup-checklist-title"
      className="mb-6 rounded-xl border border-solid border-line bg-panel p-5"
    >
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 id="setup-checklist-title" className="m-0 text-base font-semibold text-text">
            Get started with wardenIQ
          </h2>
          <p className="m-0 mt-1 text-sm text-muted" aria-live="polite">
            {progress.done} of {progress.total} required steps done
            {readOnly ? ". You have read-only access, so an admin or editor completes these." : "."}
          </p>
        </div>
        <div className="flex gap-2">
          <button type="button" className="ghost" onClick={() => requestTour(null)}>
            Take the tour
          </button>
          <button type="button" className="ghost" onClick={dismiss} aria-label="Dismiss setup checklist">
            Dismiss
          </button>
        </div>
      </div>

      <ol className="m-0 flex list-none flex-col gap-2 p-0">
        {steps.map((step, i) => {
          const actionable = !step.done && canAct(step, role);
          const blocked = !step.done && !readOnly && !canAct(step, role) && step.blockedNote;
          return (
            <li
              key={step.id}
              aria-current={step.next ? "step" : undefined}
              className={`flex flex-wrap items-center gap-3 rounded-lg border border-solid px-4 py-3 ${
                step.next ? "border-accent bg-panel2" : "border-line"
              }`}
            >
              <StepMarker step={step} index={i} />
              <div className="min-w-0 flex-1">
                <div className={`text-sm font-medium ${step.done ? "text-muted line-through" : "text-text"}`}>
                  {step.title}
                  <span className="sr-only">: {statusText(step)}</span>
                  {step.optional && !step.done && (
                    <span className="ml-2 text-xs font-normal text-muted">Optional</span>
                  )}
                  {step.next && (
                    <span aria-hidden="true" className="ml-2 text-xs font-semibold text-accent">
                      Next
                    </span>
                  )}
                </div>
                {!step.done && (
                  <div className="mt-1 text-xs text-muted">
                    {step.description}
                    {step.sampleLink && (
                      <>
                        {" "}No document handy?{" "}
                        <a
                          href={SAMPLE_PRD_URL}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-accent underline"
                        >
                          Try the sample PRD
                          <span className="sr-only"> (opens in a new tab)</span>
                        </a>
                        .
                      </>
                    )}
                    {blocked && <span className="block mt-1">{step.blockedNote}</span>}
                  </div>
                )}
                {step.note && <div className="mt-1 text-xs text-muted">{step.note}</div>}
              </div>
              {actionable && (
                <div className="flex gap-2">
                  <button
                    type="button"
                    className="ghost"
                    onClick={() => goTo(step.view)}
                    aria-label={`${step.action} (opens the screen)`}
                  >
                    {step.action}
                  </button>
                  <button
                    type="button"
                    className={step.next ? "go" : "ghost"}
                    onClick={() => requestTour(CHECKLIST_TO_CHAPTER[step.id])}
                    aria-label={`Show me how: ${step.title}`}
                  >
                    Show me
                  </button>
                </div>
              )}
            </li>
          );
        })}
      </ol>
      {welcomeDialog}
    </section>
  );
}
