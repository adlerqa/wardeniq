/**
 * Small helpers for talking to the rest of the app from the onboarding UI
 * (checklist, welcome dialog, guided tour, help button). They read what the
 * compat runtime already exposes (role classes on <body>, the global
 * navigateTo(), the visible `.view`) without adding anything to compat/.
 */

import { effectiveSetup, needsLlmStatus, needsRunningJobs } from "./setupSteps.js";

/** The app's role, as applyRole() (compat 10-auth.js) records it on <body>. */
export function readRole() {
  const c = document.body.classList;
  if (c.contains("role-viewer")) return "viewer";
  if (c.contains("role-editor")) return "editor";
  // applyRole() only adds the viewer/editor classes; admins have neither but do
  // have the admin-only nav entries un-hidden.
  return document.querySelector("nav button[data-admin]:not([hidden])") ? "admin" : "viewer";
}

/** Is a user signed in? applyRole() un-hides #usermenu after sign-in. */
export function isSignedIn() {
  const menu = document.getElementById("usermenu");
  return Boolean(menu && !menu.hidden);
}

/** Open a screen with the app's own navigation (compat 00-core.js navigateTo). */
export function goTo(view) {
  if (typeof window.navigateTo === "function") window.navigateTo(view);
  else window.location.hash = view;
}

/** Id of the visible screen, e.g. "dashboard" for #view-dashboard. */
export function currentView() {
  const v = document.querySelector("main .view:not([hidden])");
  return v ? v.id.replace(/^view-/, "") : null;
}

/** Is the element on screen (rendered, not hidden, with a size)? */
export function isShown(el) {
  if (!el || !el.isConnected) return false;
  if (el.closest("[hidden]")) return false;
  const r = el.getBoundingClientRect();
  if (r.width === 0 && r.height === 0) return false;
  const style = window.getComputedStyle(el);
  return style.visibility !== "hidden" && style.display !== "none";
}

/** First visible element matching any of the selectors, in order. */
export function findTarget(selectors) {
  for (const sel of selectors || []) {
    let nodes;
    try {
      nodes = document.querySelectorAll(sel);
    } catch {
      continue;
    }
    for (const el of nodes) if (isShown(el)) return el;
  }
  return null;
}

/** Every visible element matching any of the selectors (for grouped highlights). */
export function findAllTargets(selectors) {
  const out = [];
  for (const sel of selectors || []) {
    let nodes;
    try {
      nodes = document.querySelectorAll(sel);
    } catch {
      continue;
    }
    for (const el of nodes) if (isShown(el) && !out.includes(el)) out.push(el);
  }
  return out;
}

/** Is any element matching the selector visible? */
export function visible(selector) {
  return Boolean(findTarget([selector]));
}

async function getJson(url) {
  const r = await fetch(url, { credentials: "same-origin" });
  if (!r.ok) throw new Error(String(r.status));
  return r.json();
}

/**
 * The effective setup flags: GET /api/dashboard `setup`, plus GET /api/status
 * while the LLM settings were never saved (same rule as the boot gate, #279),
 * plus the running jobs while a feature has no test cases yet.
 * Returns null when not signed in or on error.
 */
export async function loadEffectiveSetup() {
  try {
    const d = await getJson("/api/dashboard");
    const raw = d && d.setup ? d.setup : null;
    let status = null;
    if (needsLlmStatus(raw)) {
      try {
        status = await getJson("/api/status");
      } catch {
        /* treat as not configured */
      }
    }
    let jobs = null;
    if (needsRunningJobs(raw)) {
      try {
        jobs = await getJson("/api/jobs?status=running&limit=50");
      } catch {
        /* treat as not running */
      }
    }
    return effectiveSetup(raw, status, jobs);
  } catch {
    return null;
  }
}

/** Event the help button sends to bring back a dismissed checklist. */
export const SHOW_CHECKLIST_EVENT = "wq:show-setup-checklist";
