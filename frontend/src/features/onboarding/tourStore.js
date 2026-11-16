/**
 * Tiny external store for the guided tour, shared by the tour engine, the
 * checklist's "Show me" buttons, the welcome dialog and the help button.
 * Plain JS (no React) so it can be unit tested; components subscribe with
 * React's useSyncExternalStore.
 *
 * status: "idle" → "loading" (a start was requested; the engine is reading the
 * setup flags) → "active" (steps[index] is shown) → "idle".
 */

import { readFlag, writeFlag } from "./storage.js";
import { TOUR_SEEN_KEY } from "./tourSteps.js";

const IDLE = Object.freeze({ status: "idle", chapter: null, steps: [], index: 0 });
let state = IDLE;
const listeners = new Set();

function setState(next) {
  state = next;
  listeners.forEach((fn) => fn());
}

export function getTourState() {
  return state;
}

export function subscribeTour(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

/** Ask the engine to start a tour, from the beginning or at a chapter. */
export function requestTour(chapter = null) {
  markTourSeen();
  setState({ status: "loading", chapter, steps: [], index: 0 });
}

/** The engine built the steps: show the first one (or stop if there are none). */
export function beginTour(steps) {
  if (state.status !== "loading") return;
  if (!steps || !steps.length) {
    setState(IDLE);
    return;
  }
  setState({ ...state, status: "active", steps, index: 0 });
}

export function nextStep() {
  if (state.status !== "active") return;
  if (state.index >= state.steps.length - 1) setState(IDLE);
  else setState({ ...state, index: state.index + 1 });
}

export function previousStep() {
  if (state.status !== "active" || state.index === 0) return;
  setState({ ...state, index: state.index - 1 });
}

export function endTour() {
  setState(IDLE);
}

/** Has the signed-in user answered the welcome prompt (or taken the tour)? */
export function hasSeenTour() {
  return readFlag(TOUR_SEEN_KEY, true); // storage unavailable: never nag
}

export function markTourSeen() {
  writeFlag(TOUR_SEEN_KEY, true);
}

/** Test helper: reset to idle. */
export function _resetTourForTests() {
  setState(IDLE);
}
