import { useCallback, useEffect, useLayoutEffect, useRef, useState, useSyncExternalStore } from "react";
import { createPortal } from "react-dom";

import {
  currentView,
  findAllTargets,
  findTarget,
  goTo,
  loadEffectiveSetup,
  readRole,
  visible,
} from "../appBridge.js";
import {
  buildTour,
  isActionStep,
  keyAction,
  popoverPosition,
  resolveText,
  tourProgress,
} from "../tourSteps.js";
import {
  beginTour,
  endTour,
  getTourState,
  nextStep,
  previousStep,
  subscribeTour,
} from "../tourStore.js";

const PAD = 6; // space between the highlighted element and its ring
const TARGET_TIMEOUT_MS = 4000; // then fall back to a centred popup
const SETUP_POLL_MS = 5000;

function isTyping(el) {
  if (!el) return false;
  const tag = el.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || el.isContentEditable;
}

function sameRect(a, b) {
  return a && b && a.top === b.top && a.left === b.left && a.width === b.width && a.height === b.height;
}

/**
 * The guided tour (issue #254): dims the page except the control to use, and
 * shows a popup with what it is and what to do. Moves between screens with the
 * app's navigateTo() and waits for real actions (a project created, generation
 * finished) before moving on. Rendered once from AppOverlays.
 */
export default function GuidedTour() {
  const tour = useSyncExternalStore(subscribeTour, getTourState);
  const [role, setRole] = useState("viewer");
  const setupRef = useRef(null);
  const [rect, setRect] = useState(null);
  const [missing, setMissing] = useState(false);
  const [popSize, setPopSize] = useState({ width: 340, height: 180 });
  const popRef = useRef(null);
  const titleRef = useRef(null);
  const returnFocusRef = useRef(null);

  const step = tour.status === "active" ? tour.steps[tour.index] : null;

  const env = useCallback(
    () => ({ view: currentView(), visible, setup: setupRef.current || {}, role }),
    [role],
  );

  // A start was requested: read role and setup, then build the steps.
  useEffect(() => {
    if (tour.status !== "loading") return;
    let cancelled = false;
    returnFocusRef.current = document.activeElement;
    (async () => {
      const r = readRole();
      const setup = (await loadEffectiveSetup()) || {};
      if (cancelled) return;
      setupRef.current = setup;
      setRole(r);
      beginTour(buildTour({ role: r, setup, startChapter: tour.chapter }));
    })();
    return () => {
      cancelled = true;
    };
  }, [tour.status, tour.chapter]);

  // Tour ended: give focus back to where the user was.
  useEffect(() => {
    if (tour.status !== "idle") return;
    const el = returnFocusRef.current;
    returnFocusRef.current = null;
    if (el && el.isConnected && typeof el.focus === "function") el.focus();
  }, [tour.status]);

  // Each step: skip, open its screen, find and track the target, wait for actions.
  useEffect(() => {
    if (!step) return undefined;
    if (step.skip && step.skip(env())) {
      nextStep();
      return undefined;
    }
    if (step.view && currentView() !== step.view) goTo(step.view);
    // "featureList": show the project's feature list rather than the create form
    // or the last opened feature, which navigateTo("features") can re-open a
    // moment later. Retried for a few seconds; showFeatureList / loadFeatures
    // are compat globals (03-features-and-usage.js).
    let ensureUntil = step.ensure === "featureList" ? Date.now() + 3000 : 0;
    let lastEnsure = 0;
    const ensure = () => {
      if (!ensureUntil || Date.now() > ensureUntil || Date.now() - lastEnsure < 600) return;
      if (visible("[data-feature-card]")) {
        ensureUntil = 0;
        return;
      }
      if (visible("#detail-card") || visible("#feature-create-page") || currentView() === "features") {
        lastEnsure = Date.now();
        if (typeof window.showFeatureList === "function") window.showFeatureList();
        if (typeof window.loadFeatures === "function") window.loadFeatures();
      }
    };

    setRect(null);
    setMissing(false);
    let target = null; // the first highlighted element (scroll anchor, click target)
    let scrolled = false;
    const startedAt = Date.now();
    const timers = [];

    const track = () => {
      ensure();
      if (!step.targets || !step.targets.length) return;
      const els = step.group ? findAllTargets(step.targets) : [findTarget(step.targets)].filter(Boolean);
      const el = els[0] || null;
      if (el !== target) {
        target = el;
        scrolled = false;
      }
      if (!el) {
        setRect(null);
        if (Date.now() - startedAt > TARGET_TIMEOUT_MS) setMissing(true);
        return;
      }
      setMissing(false);
      if (!scrolled) {
        scrolled = true;
        el.scrollIntoView({ block: "center", inline: "nearest" });
      }
      // Grouped steps highlight the box around every matched element.
      const rs = els.map((x) => x.getBoundingClientRect());
      const top = Math.min(...rs.map((r) => r.top));
      const left = Math.min(...rs.map((r) => r.left));
      const bottom = Math.max(...rs.map((r) => r.bottom));
      const right = Math.max(...rs.map((r) => r.right));
      const next = { top, left, width: right - left, height: bottom - top, bottom, right };
      setRect((prev) => (sameRect(prev, next) ? prev : next));
    };
    track();
    timers.push(setInterval(track, 200));

    if (step.waitFor) {
      timers.push(
        setInterval(() => {
          if (step.waitFor(env())) nextStep();
        }, 500),
      );
    }
    if (step.pollSetup) {
      timers.push(
        setInterval(async () => {
          const s = await loadEffectiveSetup();
          if (s) setupRef.current = s;
        }, SETUP_POLL_MS),
      );
    }

    // Action step "click the highlighted control": let the app handle the click, then move on.
    const onClick = (e) => {
      if (!step.advanceOnClick || !target) return;
      if (target === e.target || target.contains(e.target)) setTimeout(nextStep, 150);
    };
    document.addEventListener("click", onClick, true);

    // Move focus into the popup so keyboard and screen-reader users land on the step.
    const focusTimer = setTimeout(() => titleRef.current && titleRef.current.focus(), 50);

    return () => {
      timers.forEach(clearInterval);
      clearTimeout(focusTimer);
      document.removeEventListener("click", onClick, true);
    };
  }, [step, env]);

  // Keyboard: Esc closes; arrows go back/next unless the user is typing.
  useEffect(() => {
    if (!step) return undefined;
    const onKey = (e) => {
      const action = keyAction(e.key, {
        typing: isTyping(e.target),
        actionStep: isActionStep(step),
      });
      if (!action) return;
      e.preventDefault();
      if (action === "close") endTour();
      else if (action === "next") nextStep();
      else if (action === "back") previousStep();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [step]);

  // Measure the popup (its height depends on the step's text) so it can be
  // placed next to the target.
  useLayoutEffect(() => {
    if (!popRef.current) return;
    const r = popRef.current.getBoundingClientRect();
    if (Math.abs(r.width - popSize.width) > 1 || Math.abs(r.height - popSize.height) > 1) {
      setPopSize({ width: r.width, height: r.height });
    }
  }, [tour.index, tour.status, missing, popSize.width, popSize.height]);

  if (!step) return null;

  const e = env();
  const title = resolveText(step.title, e);
  const body = resolveText(step.body, e);
  const action = isActionStep(step);
  const isFirst = tour.index === 0;
  const isLast = tour.index === tour.steps.length - 1;
  const ring = rect
    ? {
        top: rect.top - PAD,
        left: rect.left - PAD,
        width: rect.width + PAD * 2,
        height: rect.height + PAD * 2,
      }
    : null;
  const vp = { width: window.innerWidth, height: window.innerHeight };
  const pos = popoverPosition(
    ring ? { ...ring, bottom: ring.top + ring.height, right: ring.left + ring.width } : null,
    popSize,
    vp,
    { prefer: step.placement || null },
  );
  const progress = tourProgress(tour.steps, tour.index);

  // The dimmed backdrop is four panels around the target, so the highlighted
  // control stays clickable and everything else is blocked.
  const shade = "fixed bg-bg opacity-70 motion-safe:transition-all motion-safe:duration-200";
  const backdrop = ring ? (
    <>
      <div aria-hidden="true" className={shade} style={{ top: 0, left: 0, right: 0, height: Math.max(0, ring.top) }} />
      <div aria-hidden="true" className={shade} style={{ top: ring.top + ring.height, left: 0, right: 0, bottom: 0 }} />
      <div aria-hidden="true" className={shade} style={{ top: ring.top, left: 0, width: Math.max(0, ring.left), height: ring.height }} />
      <div aria-hidden="true" className={shade} style={{ top: ring.top, left: ring.left + ring.width, right: 0, height: ring.height }} />
      <div
        aria-hidden="true"
        className="pointer-events-none fixed rounded-lg border-2 border-solid border-accent motion-safe:transition-all motion-safe:duration-200"
        style={ring}
      />
    </>
  ) : (
    <div aria-hidden="true" className={`${shade} inset-0`} />
  );

  return createPortal(
    <div className="fixed inset-0 z-[150]" style={{ pointerEvents: "none" }}>
      <div style={{ pointerEvents: "auto" }}>{backdrop}</div>
      <div
        ref={popRef}
        role="dialog"
        aria-modal="false"
        aria-labelledby="wq-tour-title"
        aria-describedby="wq-tour-body"
        className="fixed w-[340px] max-w-[calc(100vw-24px)] rounded-xl border border-solid border-line bg-panel p-4 text-text shadow-2xl motion-safe:transition-all motion-safe:duration-200"
        style={{ top: pos.top, left: pos.left, pointerEvents: "auto" }}
      >
        <div className="mb-1 flex items-center justify-between gap-2">
          <span className="text-xs text-muted">
            {progress.title} · {tour.index + 1}/{tour.steps.length}
          </span>
          <button type="button" className="ghost" onClick={endTour} aria-label="Close the tour">
            Exit
          </button>
        </div>
        <h2 id="wq-tour-title" ref={titleRef} tabIndex={-1} className="m-0 text-base font-semibold text-text outline-none">
          {title}
        </h2>
        <p id="wq-tour-body" className="m-0 mt-2 text-sm leading-relaxed text-muted">
          {body}
        </p>
        {step.link && (
          <a
            href={step.link.href}
            target="_blank"
            rel="noopener noreferrer"
            className="mt-2 inline-block text-sm text-accent underline"
          >
            {step.link.label}
            <span className="sr-only"> (opens in a new tab)</span>
          </a>
        )}
        {missing && (
          <p className="m-0 mt-2 text-xs text-muted">
            This control isn&apos;t on screen right now. You can carry on with Next.
          </p>
        )}
        {action && !missing && (
          <p className="m-0 mt-2 text-xs font-medium text-accent">
            {step.waitFor && !step.advanceOnClick && step.pollSetup
              ? "Waiting for this to finish…"
              : "Use the highlighted control to continue."}
          </p>
        )}
        <div className="mt-4 flex items-center justify-between gap-2">
          <button type="button" className="ghost" onClick={previousStep} disabled={isFirst}>
            Back
          </button>
          <button type="button" className={action && !missing ? "ghost" : "go"} onClick={nextStep}>
            {step.nextLabel || (isLast ? "Finish" : action && !missing ? "Skip this step" : "Next")}
          </button>
        </div>
        <div aria-hidden="true" className="mt-3 h-1 overflow-hidden rounded-full bg-panel2">
          <div
            className="h-full bg-accent motion-safe:transition-all motion-safe:duration-300"
            style={{ width: `${Math.round(((tour.index + 1) / tour.steps.length) * 100)}%` }}
          />
        </div>
        <div className="sr-only" aria-live="polite">
          {`Part ${progress.part} of ${progress.parts}, ${progress.title}, step ${progress.step} of ${progress.steps}: ${title}`}
        </div>
      </div>
    </div>,
    document.body,
  );
}
