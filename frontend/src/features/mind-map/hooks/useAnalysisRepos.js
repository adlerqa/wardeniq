import { useCallback, useState } from "react";

import { api } from "../../../lib/api.js";
import { currentProjectId, toast } from "../../../lib/compatBridge.js";
import { repoAnalysisDefaultChecked, withoutConnected } from "../lib/mindmap.js";

/**
 * Repo rows (checkbox + branch picker each) and the "Add a repo from GitHub"
 * picker, shared by the Mind Map and Code Analysis screens (was
 * repoBranchRows / fillBranchDropdowns / openGitRepoPicker in the compat
 * runtime). `pidRef.current` is the screen's selected project.
 *
 * repos:  [{ id, full_name, kind, default_branch, checked, branch, defaultLabel, branchOptions }]
 * picker: { pid, repos } while the picker is open
 */
export default function useAnalysisRepos(pidRef) {
  const [repos, setRepos] = useState([]);
  const [picker, setPicker] = useState(null);

  const projectId = useCallback(() => pidRef.current || currentProjectId() || "", [pidRef]);

  /** `only`: tick just this repo id (Projects → "Analyze"); default ticks all but infra. */
  const loadRepos = useCallback(
    async ({ only } = {}) => {
      const p = projectId();
      if (!p) return;
      let list;
      try {
        const r = await api(`/api/projects/${p}/repos?repo_type=app`); // app repos only
        list = r.repos || [];
      } catch {
        return;
      }
      setRepos(
        list.map((rp) => ({
          ...rp,
          checked: only !== undefined ? rp.id === only : repoAnalysisDefaultChecked(rp.kind),
          branch: "",
          defaultLabel: rp.default_branch || "default",
          branchOptions: [],
        })),
      );
      // Branch lists come from each repo's provider, one repo at a time.
      for (const rp of list) {
        try {
          const r = await api(`/api/repos/${rp.id}/branches`);
          if (!(r.branches || []).length) continue;
          const def = r.default || rp.default_branch || "";
          setRepos((rows) =>
            rows.map((row) =>
              row.id === rp.id
                ? { ...row, defaultLabel: def || "default", branchOptions: r.branches.filter((b) => b !== def) }
                : row,
            ),
          );
        } catch {
          /* keep the default-only option */
        }
      }
    },
    [projectId],
  );

  const updateRepo = (id, patch) => setRepos((rows) => rows.map((r) => (r.id === id ? { ...r, ...patch } : r)));

  /** "+ Add a repo from GitHub": list what the project's PAT can see, minus connected repos. */
  const openPicker = async () => {
    const p = projectId();
    if (!p) {
      toast("Pick a project first", true);
      return;
    }
    let found = [];
    try {
      for (let page = 1; page <= 4; page++) {
        const r = await api(`/api/projects/${p}/github/accessible-repos?page=${page}`);
        const batch = r.repos || [];
        found = found.concat(batch);
        if (batch.length < 30) break;
      }
    } catch (e) {
      toast(
        `Couldn't list repos for this project (${e.message}). Check the project's GitHub PAT under Projects & Repos.`,
        true,
      );
      return;
    }
    try {
      const pr = await api(`/api/projects/${p}/repos`);
      found = withoutConnected(found, pr.repos);
    } catch {
      /* show everything */
    }
    if (!found.length) {
      toast("No new repos to add — all your accessible repos are already in this project", true);
      return;
    }
    setPicker({ pid: p, repos: found });
  };

  const addPicked = async (picks) => {
    if (!picks.length) {
      toast("Select at least one repo", true);
      return;
    }
    const p = picker.pid;
    let ok = 0,
      fail = 0;
    for (const pick of picks) {
      try {
        await api(`/api/projects/${p}/repos`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ repo_full_name: pick.full_name, default_branch: pick.def || "main", repo_type: "app" }),
        });
        ok++;
      } catch {
        fail++;
      }
    }
    setPicker(null);
    toast(`${ok} repo(s) added${fail ? ` · ${fail} skipped (already added or inaccessible)` : ""}`);
    loadRepos();
  };

  return {
    repos,
    picker,
    loadRepos,
    updateRepo,
    openPicker,
    closePicker: () => setPicker(null),
    addPicked,
  };
}
