/**
 * Setup model shared by the Dashboard "Get started" checklist and the guided
 * tour (issue #254).
 *
 * Pure functions with no React or DOM access, so the rules can be unit tested
 * with `node --test` (see frontend/tests/setup-checklist.test.js).
 *
 * Inputs:
 * - `setup`  — the `setup` block of GET /api/dashboard (app/store/dashboard.py
 *              `setup_status`): booleans derived from real data, never clicks.
 * - `status` — GET /api/status, only needed while the LLM settings were never
 *              saved. Like the boot gate (16-boot.js, #279), a passing
 *              `llm.health` counts as configured, so a working built-in Ollama
 *              is not shown as a to-do.
 * - `jobs`   — GET /api/jobs?status=running (project-scoped), only needed while
 *              a feature exists without test cases, to tell "generation is
 *              running" apart from "generation never ran or failed".
 */

/** localStorage key remembering that the user dismissed the checklist. */
export const SETUP_DISMISS_KEY = "wq_setup_dismissed";

/** Public link to the example PRD, so a new user has a document to try. */
export const SAMPLE_PRD_URL =
  "https://github.com/adlerqa/wardeniq/blob/main/examples/sample-prd.md";

/** Does the checklist need GET /api/status to decide the LLM step? */
export function needsLlmStatus(setup) {
  return Boolean(setup) && !setup.llm_configured;
}

/** Does the checklist need the running jobs to describe the generate step? */
export function needsRunningJobs(setup) {
  return Boolean(setup) && Boolean(setup.has_feature) && !setup.has_test_cases;
}

/** Is a generation (or document ingest) job running, from GET /api/jobs?status=running? */
export function isGenerating(jobs) {
  const list = (jobs && jobs.jobs) || [];
  return list.some((j) => j.status === "running" && (j.type === "generate" || j.type === "ingest"));
}

/**
 * Merge the dashboard `setup` flags with the LLM health from /api/status and
 * the running jobs. Adds `llm_source`: "saved" (settings saved), "default"
 * (never saved but the model answers its health check) or null (not
 * configured), `llm_model`, and `generating` (a generation job is running).
 */
export function effectiveSetup(setup, status, jobs = null) {
  if (!setup) return null;
  const healthy = Boolean(status && status.llm && status.llm.health && status.llm.health.ok);
  const saved = Boolean(setup.llm_configured);
  return {
    ...setup,
    llm_configured: saved || healthy,
    llm_source: saved ? "saved" : healthy ? "default" : null,
    llm_model: (status && status.llm && status.llm.model) || null,
    generating: isGenerating(jobs),
  };
}

/** Setup is complete once every required step is done (the repository is optional). */
export function isSetupComplete(setup) {
  return Boolean(setup && setup.llm_configured && setup.has_project && setup.has_test_cases);
}

const STEP_DEFS = [
  {
    id: "llm",
    flag: "llm_configured",
    title: "Set up your AI model",
    description:
      "wardenIQ uses an LLM to write your test cases. The built-in Ollama works without an API key, or connect a hosted provider.",
    view: "config",
    action: "Open Configuration",
    adminOnly: true,
    blockedNote: "Ask an admin to set up the AI model in Configuration.",
  },
  {
    id: "project",
    flag: "has_project",
    title: "Create a project",
    description: "A project holds your features, repositories and test cases.",
    view: "projects",
    action: "Create a project",
  },
  {
    id: "repo",
    flag: "has_repo",
    title: "Connect a repository",
    description:
      "Lets wardenIQ map code changes to your tests (Code Analysis and Mind Map). You can do this later.",
    view: "projects",
    action: "Connect a repository",
    optional: true,
  },
  {
    id: "generate",
    flag: "has_test_cases",
    title: "Add a feature and generate test cases",
    description:
      "Open your project, add a feature from a requirements document (PDF, DOCX or Markdown) and run generation.",
    view: "projects",
    action: "Add a feature",
    sampleLink: true,
  },
];

/** Normalise the role the app exposes on <body>; anything unknown is treated as read-only. */
export function normaliseRole(role) {
  return role === "admin" || role === "editor" ? role : "viewer";
}

/** Can this role use the step's button? Viewers never get write actions. */
export function canAct(step, role) {
  const r = normaliseRole(role);
  if (r === "viewer") return false;
  if (step.adminOnly && r !== "admin") return false;
  return true;
}

/**
 * Build the ordered step list from an effective setup (see effectiveSetup).
 * `next` marks the first required step that is not done; optional steps are
 * never "next". `note` carries extra context for a step, if any.
 */
export function buildSetupSteps(setup) {
  const s = setup || {};
  const steps = STEP_DEFS.map((def) => {
    const step = { ...def, done: Boolean(s[def.flag]), next: false, note: null };
    if (def.id === "llm" && step.done && s.llm_source === "default") {
      step.note = s.llm_model
        ? `Using the built-in model (${s.llm_model}). You can change it any time in Configuration.`
        : "Using the built-in model. You can change it any time in Configuration.";
    }
    if (def.id === "generate" && !step.done && s.generating) {
      step.note = "Generation is running. This step ticks off when the first test cases are ready.";
      step.action = "Open my project";
    } else if (def.id === "generate" && !step.done && s.has_feature) {
      step.note = "You already have a feature without test cases. Open it and run generation.";
      step.action = "Open my project";
    }
    return step;
  });
  const next = steps.find((st) => !st.optional && !st.done);
  if (next) next.next = true;
  return steps;
}

/** Progress over the required steps only. */
export function setupProgress(steps) {
  const required = steps.filter((st) => !st.optional);
  return { done: required.filter((st) => st.done).length, total: required.length };
}

/**
 * What the card should render:
 * - "hidden"    no data yet, or setup complete
 * - "collapsed" dismissed by the user: only a small "Show setup checklist" link
 * - "open"      the full checklist
 */
export function checklistState(setup, dismissed) {
  if (!setup || isSetupComplete(setup)) return "hidden";
  return dismissed ? "collapsed" : "open";
}
