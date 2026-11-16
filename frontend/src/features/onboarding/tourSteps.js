/**
 * Guided tour content and rules (issue #254).
 *
 * Pure data and functions, no React or DOM access, so they can be unit tested
 * with `node --test` (see frontend/tests/tour-steps.test.js). The tour engine
 * (components/GuidedTour.jsx) supplies an `env` object to the step callbacks:
 *
 *   env.view          id of the visible screen ("dashboard", "projects", ...)
 *   env.visible(sel)  is an element matching the selector on screen?
 *   env.setup         effective setup flags (see setupSteps.js effectiveSetup)
 *   env.role          "admin" | "editor" | "viewer"
 *
 * Step fields:
 *   id, chapter, title, body       text shown in the popup
 *   targets                        CSS selectors; the first visible one is highlighted.
 *                                  No targets = a centred popup.
 *   group                          highlight every visible match of `targets` together
 *                                  (e.g. a file picker and the text box under it)
 *   placement                      "side" to keep the popup beside a form, not over it
 *   when(setup, role)              include the step only for this setup (decided once,
 *                                  when the tour is built, so the step count is right)
 *   view                           screen to open first (via the app's navigateTo)
 *   skip(env)                      skip this step when it returns true
 *   waitFor(env)                   an action step: moves on by itself once true
 *   advanceOnClick                 an action step: moves on when the target is clicked
 *   pollSetup                      re-read the setup flags while waiting (slow jobs)
 *   link                           optional { href, label } shown under the body
 *   nextLabel                      label for the Next button on this step
 *   ensure                         named preparation the engine runs on entry
 *                                  ("featureList": show the project's feature list)
 *
 * Only stable ids from React-owned markup (features/*, layouts/*) and the
 * compat empty-state buttons are used as targets; nothing is added to compat/.
 */

import { SAMPLE_PRD_URL, isSetupComplete, normaliseRole } from "./setupSteps.js";

/** localStorage key: the welcome prompt was answered (started, skipped or finished). */
export const TOUR_SEEN_KEY = "wq_tour_seen";

const isEditorOrAdmin = (env) => env.role === "admin" || env.role === "editor";

/** Chapters in tour order, with their title, who gets them and when. */
export const CHAPTERS = [
  { id: "welcome", title: "Welcome", applies: () => true },
  { id: "llm", title: "AI model", applies: (env) => env.role === "admin" && !env.setup.llm_configured },
  { id: "project", title: "Create a project", applies: (env) => isEditorOrAdmin(env) && !env.setup.has_project },
  { id: "generate", title: "Generate test cases", applies: (env) => isEditorOrAdmin(env) && !env.setup.has_test_cases },
  { id: "results", title: "Your results", applies: (env) => isEditorOrAdmin(env) },
  { id: "repo", title: "Connect a repository", applies: (env) => isEditorOrAdmin(env) && !env.setup.has_repo },
  { id: "explore", title: "Find your way around", applies: () => true },
];

const CHAPTER_TITLE = Object.fromEntries(CHAPTERS.map((c) => [c.id, c.title]));

/** Map a checklist step id to the tour chapter that shows how to do it. */
export const CHECKLIST_TO_CHAPTER = {
  llm: "llm",
  project: "project",
  repo: "repo",
  generate: "generate",
};

export const STEPS = [
  // ---- welcome ----
  {
    id: "welcome-intro",
    chapter: "welcome",
    title: "Welcome to wardenIQ",
    body: (env) =>
      env.role === "viewer" || isSetupComplete(env.setup)
        ? "wardenIQ turns requirement documents into a reusable test suite and maps code changes to the tests they affect. This short tour shows you where everything is. Press Esc to leave at any time."
        : "wardenIQ turns requirement documents into a reusable test suite and maps code changes to the tests they affect. This short tour walks you through setup on the real screens. Press Esc to leave at any time.",
  },
  {
    id: "welcome-checklist",
    chapter: "welcome",
    view: "dashboard",
    targets: ["#setup-checklist"],
    skip: (env) => isSetupComplete(env.setup),
    title: "Your setup checklist",
    body: "This card tracks your progress from real data, so steps tick off as you complete them. Each step has a Show me button that replays its part of this tour.",
  },

  // ---- llm (admins, only while no working model) ----
  {
    id: "llm-provider",
    chapter: "llm",
    view: "config",
    targets: ["#cfg-llm-provider"],
    title: "Choose an AI provider",
    body: "wardenIQ uses an LLM to write test cases. Ollama (built-in) runs inside this Docker stack: free, private and no API key. Hosted providers such as OpenAI, Anthropic or Gemini need an API key.",
  },
  {
    id: "llm-model",
    chapter: "llm",
    targets: ["#cfg-llm-model-select", "#cfg-llm-model"],
    title: "Pick a model",
    body: "On the built-in Ollama, qwen2.5:3b is the fast default and qwen2.5:7b gives better results but is slower and needs more memory. You can change this later.",
  },
  {
    id: "llm-save",
    chapter: "llm",
    targets: ["#cfg-llm-save"],
    advanceOnClick: true,
    title: "Save the AI settings",
    body: "Click Save. wardenIQ stores the settings and uses them for every generation and analysis.",
  },

  // ---- project ----
  {
    id: "project-new",
    chapter: "project",
    view: "projects",
    targets: ["#project-cards-container .empty-state .go", "#proj-new-btn"],
    waitFor: (env) => env.visible("#proj-create-card"),
    title: "Create your first project",
    body: "A project holds your features, repositories and test cases. Click the highlighted button to start.",
  },
  {
    id: "project-name",
    chapter: "project",
    targets: ["#new-proj-name"],
    placement: "side",
    skip: (env) => !env.visible("#proj-create-card") && env.setup.has_project,
    title: "Name the project",
    body: "Only the name is required. Jira, Confluence and repositories further down are optional and can be added later.",
  },
  {
    id: "project-save",
    chapter: "project",
    targets: ["#proj-create-save"],
    waitFor: (env) => env.view === "features",
    title: "Create the project",
    body: "Click Create project. wardenIQ opens the new project straight away.",
  },

  // ---- generate ----
  {
    id: "generate-open-project",
    chapter: "generate",
    view: "projects",
    skip: (env) => env.view === "features",
    targets: ["[data-project-card]"],
    waitFor: (env) => env.view === "features",
    title: "Open your project",
    body: "Click your project to see its features.",
  },
  {
    id: "generate-new-feature",
    chapter: "generate",
    when: (setup) => !setup.has_feature,
    targets: ["#feat-list .empty-state .go", "#feature-new-btn"],
    waitFor: (env) => env.visible("#feature-create-page"),
    title: "Add a feature",
    body: "A feature is one piece of functionality, described by your requirement documents. Click the highlighted button.",
  },
  {
    id: "generate-open-feature",
    chapter: "generate",
    when: (setup) => setup.has_feature,
    targets: ["[data-feature-card]"],
    waitFor: (env) => env.visible("#detail-card"),
    title: "Open your feature",
    body: (env) =>
      env.setup.generating
        ? "Generation is already running for this feature. Click it to follow its progress."
        : "This feature has no test cases yet. Click it to open its workspace.",
  },
  {
    id: "generate-regenerate",
    chapter: "generate",
    when: (setup) => setup.has_feature && !setup.generating,
    // #d-regen exists in the markup but the app never shows it, so the
    // new-version button (+) is the visible way to run generation again.
    targets: ["#d-regen", "#d-newver"],
    advanceOnClick: true,
    title: "Run generation again",
    body: "Click + to add a new version: upload the requirement documents again (or paste the text) and wardenIQ generates the test suite for it.",
  },
  {
    id: "generate-name",
    chapter: "generate",
    when: (setup) => !setup.has_feature,
    targets: ["#f-name"],
    placement: "side",
    title: "Name the feature",
    body: "Use a short name such as Login or Checkout.",
  },
  {
    id: "generate-docs",
    chapter: "generate",
    when: (setup) => !setup.has_feature,
    targets: ["#f-file", "#f-text"],
    group: true,
    placement: "side",
    title: "Add your requirements",
    body: "Upload one or more documents (PRD, HLD, LLD as PDF, DOCX or Markdown), or paste text in the box below. No document handy? Download the sample PRD and upload it.",
    link: { href: SAMPLE_PRD_URL, label: "Open the sample PRD" },
  },
  {
    id: "generate-mix",
    chapter: "generate",
    when: (setup) => !setup.has_feature,
    placement: "side",
    targets: ["#focus-ctrl"],
    title: "Tune the test type mix (optional)",
    body: "These sliders set how much emphasis each category gets, not a fixed number of cases. The defaults are a good start.",
  },
  {
    id: "generate-go",
    chapter: "generate",
    when: (setup) => !setup.has_feature,
    targets: ["#f-go"],
    advanceOnClick: true,
    title: "Generate test cases",
    body: "Click Generate test cases. wardenIQ reads your documents and writes a normalised, reusable test suite.",
  },
  {
    id: "generate-wait",
    chapter: "generate",
    targets: ["#f-status", "#f-log", "#d-genbanner"],
    group: true,
    pollSetup: true,
    waitFor: (env) => env.setup.has_test_cases,
    nextLabel: "Continue while it runs",
    title: "Generation is running",
    body: "This runs in the background and can take a few minutes, longer on a CPU-only machine with the built-in model. You can carry on; the tour moves on by itself when the first test cases are ready.",
  },

  // ---- results ----
  {
    id: "results-feature",
    chapter: "results",
    view: "features",
    ensure: "featureList",
    targets: ["[data-feature-card]"],
    skip: (env) => !env.setup.has_feature && !env.setup.has_test_cases,
    title: "Review your test cases",
    body: (env) =>
      env.setup.has_test_cases
        ? "Each feature card shows its version and number of test cases. Open it to review, edit and export the cases. Re-uploading documents later creates a new version and keeps, retires or adds cases."
        : "Generation is still running, so the card shows 0 test cases for now. When it finishes, the count updates and the checklist ticks off. Open the card to review, edit and export the cases.",
  },

  // ---- repo (optional) ----
  {
    id: "repo-connect",
    chapter: "repo",
    view: "projects",
    targets: ["[data-project-card] .entity-menu-btn", "[data-project-card]"],
    skip: (env) => !env.setup.has_project,
    title: "Connect a repository (optional)",
    body: "To map code changes to your tests, open the project's ⋯ menu and choose Settings & repositories, then add a GitHub or GitLab repository with a personal access token. This powers Code Analysis and Mind Map. You can skip it for now.",
  },

  // ---- explore ----
  {
    id: "explore-projects",
    chapter: "explore",
    targets: ['nav button[data-view="projects"]'],
    skip: (env) => env.role !== "viewer",
    title: "Projects & Repos",
    body: "Browse projects, their features and the repositories connected to them.",
  },
  {
    id: "explore-cases",
    chapter: "explore",
    targets: ['nav button[data-view="cases"]'],
    title: "Test Cases",
    body: "Every test case across your features, with filters, bulk actions and exports.",
  },
  {
    id: "explore-analysis",
    chapter: "explore",
    targets: ['nav button[data-view="cycles"]'],
    title: "Code Analysis",
    body: "Maps pull requests to the test cases they impact or cover. Needs a connected repository.",
  },
  {
    id: "explore-mindmap",
    chapter: "explore",
    targets: ['nav button[data-view="mindmap"]'],
    title: "Mind Map",
    body: "Sweeps your production code and shows which requirements are covered, partly covered or uncovered.",
  },
  {
    id: "explore-cycles",
    chapter: "explore",
    targets: ['nav button[data-view="testcycles"]'],
    title: "Test Cycles",
    body: "Plan test runs and record results.",
  },
  {
    id: "explore-help",
    chapter: "explore",
    targets: ["#wq-help-launcher"],
    title: "Need this again?",
    body: "Use this ? button any time to restart the tour or bring back the setup checklist.",
    nextLabel: "Finish",
  },
];

/**
 * The ordered steps for a tour run.
 *
 * - Without `startChapter`: every chapter that applies to this user and setup.
 * - With `startChapter` (a checklist "Show me"): that chapter even if its
 *   condition says it is done, followed by the later chapters that apply,
 *   without the welcome chapter.
 */
export function buildTour({ role, setup, startChapter = null }) {
  const env = { role: normaliseRole(role), setup: setup || {} };
  const startIdx = startChapter ? CHAPTERS.findIndex((c) => c.id === startChapter) : 0;
  if (startIdx < 0) return [];
  const chapters = CHAPTERS.slice(startIdx)
    .filter((c, i) => (startChapter && i === 0) || c.applies(env))
    .filter((c) => !(startChapter && c.id === "welcome"))
    .map((c) => c.id);
  return STEPS.filter(
    (s) => chapters.includes(s.chapter) && (!s.when || s.when(env.setup, env.role)),
  );
}

/**
 * Progress shown in the popup: which part of the tour (chapter) and which
 * step within it, e.g. "Part 2 of 5 · Create a project · step 1 of 3".
 */
export function tourProgress(steps, index) {
  const order = [];
  for (const s of steps) if (!order.includes(s.chapter)) order.push(s.chapter);
  const step = steps[index];
  if (!step) return null;
  const inPart = steps.filter((s) => s.chapter === step.chapter);
  return {
    part: order.indexOf(step.chapter) + 1,
    parts: order.length,
    title: CHAPTER_TITLE[step.chapter] || step.chapter,
    step: inPart.indexOf(step) + 1,
    steps: inPart.length,
  };
}

/** Resolve a step field that may be a function of env. */
export function resolveText(value, env) {
  return typeof value === "function" ? value(env) : value;
}

/** Is this an action step (the user must do something on the page)? */
export function isActionStep(step) {
  return Boolean(step && (step.waitFor || step.advanceOnClick));
}

/**
 * Keyboard handling for the tour popup. Returns "close", "next", "back" or
 * null. Arrow keys are ignored while the user is typing in a field, so the
 * tour never steals keys from the form it is pointing at.
 */
export function keyAction(key, { typing = false, actionStep = false } = {}) {
  if (key === "Escape") return "close";
  if (typing) return null;
  if (key === "ArrowRight" && !actionStep) return "next";
  if (key === "ArrowLeft") return "back";
  return null;
}

/**
 * Where to put the popup next to the highlighted element.
 * `rect` is the target's bounding box (or null for a centred popup), `pop` the
 * popup size and `vp` the viewport size. Prefers below, then above, then the
 * side with more room (with `prefer: "side"`, the sides come first, so the
 * popup does not cover the rest of a form); always clamped inside the viewport.
 */
export function popoverPosition(rect, pop, vp, { gap = 12, margin = 12, prefer = null } = {}) {
  const clampX = (x) => Math.max(margin, Math.min(x, vp.width - pop.width - margin));
  const clampY = (y) => Math.max(margin, Math.min(y, vp.height - pop.height - margin));
  if (!rect) {
    return {
      placement: "center",
      left: clampX((vp.width - pop.width) / 2),
      top: clampY((vp.height - pop.height) / 2),
    };
  }
  const centeredX = clampX(rect.left + rect.width / 2 - pop.width / 2);
  const centeredY = clampY(rect.top + rect.height / 2 - pop.height / 2);
  if (prefer === "side") {
    if (rect.right + gap + pop.width <= vp.width - margin) {
      return { placement: "right", left: rect.right + gap, top: centeredY };
    }
    if (rect.left - gap - pop.width >= margin) {
      return { placement: "left", left: rect.left - gap - pop.width, top: centeredY };
    }
  }
  if (rect.bottom + gap + pop.height <= vp.height - margin) {
    return { placement: "bottom", left: centeredX, top: rect.bottom + gap };
  }
  if (rect.top - gap - pop.height >= margin) {
    return { placement: "top", left: centeredX, top: rect.top - gap - pop.height };
  }
  const roomRight = vp.width - rect.right;
  if (roomRight >= rect.left && rect.right + gap + pop.width <= vp.width - margin) {
    return { placement: "right", left: rect.right + gap, top: centeredY };
  }
  if (rect.left - gap - pop.width >= margin) {
    return { placement: "left", left: rect.left - gap - pop.width, top: centeredY };
  }
  return { placement: "over", left: centeredX, top: clampY(vp.height - pop.height - margin) };
}
