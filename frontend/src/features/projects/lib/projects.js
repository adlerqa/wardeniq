/**
 * Pure helpers for the Projects screen (was compat/runtime/controllers/02-projects.js).
 */

/** "Name — 2 repos · 3 features" (the project pickers on other screens). */
export const projectOptionLabel = (p) => `${p.name} — ${p.repo_count} repos · ${p.feature_count} features`;

/** "1 feature · 2 repositories" under a project card's name. */
export const cardMeta = (p) =>
  `${p.feature_count} feature${p.feature_count === 1 ? "" : "s"} · ${p.repo_count} repositor${p.repo_count === 1 ? "y" : "ies"}`;

/** "2 repositories · 3 features" under the project settings title. */
export const statsText = (p) => `${p.repo_count} repositories · ${p.feature_count} features`;

/** The project to select after a reload: the current one if it still exists, else the first (or ""). */
export function pickCurrent(projects, current) {
  if (!projects.length) return "";
  return current && projects.find((p) => p.id === current) ? current : projects[0].id;
}

/** Repo kinds offered when connecting a repository (display / badge only). */
export const REPO_KINDS = [
  ["BE", "Backend"],
  ["FE", "Frontend"],
  ["test", "Test"],
  ["infra", "Infrastructure"],
];

/** Default display name of a repo picked in the create wizard: "o/web-app_ui" → "web app ui". */
export const defaultRepoLabel = (fullName) => (fullName.split("/").pop() || fullName).replace(/[-_]+/g, " ");

export const patPlaceholder = (provider) => (provider === "gitlab" ? "glpat-..." : "ghp_...");

/** Jira projects not yet linked to another project, and how many are. */
export function jiraChoices(projects = []) {
  const avail = projects.filter((p) => !p.in_use);
  const used = projects.length - avail.length;
  return {
    options: avail.map((p) => ({ value: p.key, name: p.name, label: `${p.key} — ${p.name}` })),
    status: `${avail.length} project(s) available${used ? ` · ${used} already linked` : ""}`,
  };
}

export function confluenceChoices(spaces = []) {
  return {
    options: spaces.map((s) => ({ value: s.key, name: s.name, label: `${s.key} — ${s.name}` })),
    status: `${spaces.length} space(s) available`,
  };
}

/** Repos for one picker of the create wizard: everything loaded except what the other picker took. */
export function pickerRows(available, staged, otherStaged) {
  const mine = new Map(staged.map((r) => [r.full_name, r]));
  const taken = new Set(otherStaged.map((r) => r.full_name));
  return available.filter((r) => !taken.has(r.full_name)).map((r) => ({ repo: r, staged: mine.get(r.full_name) || null }));
}

/** POST /api/projects body from the create wizard. */
export function createBody({ name, description, jira, confluence, provider }) {
  return {
    name,
    description,
    jira_project_key: jira ? jira.value : null,
    jira_project_name: jira ? jira.name || jira.label : null,
    confluence_space_key: confluence ? confluence.value : null,
    confluence_space_name: confluence ? confluence.name || confluence.label : null,
    default_git_provider: provider,
  };
}

/** POST /api/projects/{id}/repos bodies for the staged repos, app repos first. */
export function stagedRepoBodies(appRepos, testRepos, provider) {
  return [
    ...appRepos.map((r) => ({ ...r, repo_type: "app" })),
    ...testRepos.map((r) => ({ ...r, repo_type: "test" })),
  ].map((r) => ({
    repo_full_name: r.full_name,
    label: (r.label || "").trim() || r.full_name,
    repo_type: r.repo_type,
    git_provider: provider,
    kind: r.kind || (r.repo_type === "test" ? "test" : "BE"),
  }));
}

export const connectingText = (n) => `Connecting ${n} repositor${n === 1 ? "y" : "ies"}…`;

export const deletedText = (r) =>
  `Project deleted · ${r.features} feature(s), ${r.removed_orphan_cases} orphan test case(s) removed, ${r.preserved_shared_cases} shared test case(s) preserved`;

/** Project PAT endpoint for the provider. */
export const patPath = (pid, provider) => `/api/projects/${pid}/${provider === "gitlab" ? "gitlab" : "github"}/pat`;

export const providerName = (provider) => (provider === "gitlab" ? "GitLab" : "GitHub");

/**
 * Provider a typed repository address points at: "gitlab" for the configured
 * GitLab host, "github" for github.com, else null. scp-style SSH addresses
 * (git@host:owner/repo) count too; anything that isn't a URL gives null.
 */
export function providerForAddress(value, gitlabHost) {
  let hostname;
  try {
    const ssh = !value.includes("://") && value.match(/^git@([^/:\s]+):/);
    const source = ssh ? `ssh://git@${ssh[1]}/${value.slice(ssh[0].length)}` : value;
    hostname = new URL(source).hostname.toLowerCase();
  } catch {
    return undefined;
  }
  if (hostname === gitlabHost) return "gitlab";
  return hostname.replace(/^www\./, "") === "github.com" ? "github" : null;
}

/** Loaded repos matching a typed filter (case-insensitive, at most 200). */
export function suggestMatches(cache, q) {
  const ql = (q || "").trim().toLowerCase();
  return cache.filter((x) => !ql || (x.full_name || "").toLowerCase().includes(ql)).slice(0, 200);
}

/** The sync status line: text plus the last poller error, if any. */
export function syncStatusLine(s) {
  return {
    text: `poller every ${s.poll_interval_s}s · ${s.github_authenticated ? "authenticated" : "public-only"} · ingested ${s.ingested}, mapped ${s.mapped}`,
    error: s.errors && s.errors.length ? s.errors.slice(-1)[0] : "",
  };
}
