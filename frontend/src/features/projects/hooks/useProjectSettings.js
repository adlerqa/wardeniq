import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "../../../lib/api.js";
import { currentProjectId, gotoAnalyze, toast, uiConfirm } from "../../../lib/compatBridge.js";
import { patPath, providerForAddress, providerName, suggestMatches, syncStatusLine } from "../lib/projects.js";

/**
 * Project settings below the header (was 02-projects.js): the project's git
 * provider and PAT, "Connect repository" with its suggestion list, the
 * repository list and the sync status line. The project is the current
 * project (app/navState.js), read when each action runs.
 *
 * Registered while mounted: window.loadSyncStatus() — app/navigation.js navigateTo
 * and the Configuration sync card.
 *
 * patStatus / sync: null | { kind: "ok" | "muted", text } / null | { text, error } | { started: true }
 */
export default function useProjectSettings() {
  const [provider, setProviderState] = useState("github");
  const [patStatus, setPatStatus] = useState(null);
  const [pat, setPat] = useState("");
  const [repoUrl, setRepoUrl] = useState("");
  const [repoType, setRepoType] = useState("app");
  const [repoKind, setRepoKind] = useState("BE");
  const [cache, setCache] = useState([]); // "Load my repositories"; never trimmed by the filter
  const [suggest, setSuggest] = useState({ open: false, q: "" });
  const [repos, setRepos] = useState(null); // null until loaded
  const [sync, setSync] = useState(null);
  const providerRef = useRef("github");
  const gitlabHostRef = useRef(null);
  const cacheRef = useRef([]);
  const urlRef = useRef("");

  const setProvider = (p) => {
    providerRef.current = p;
    setProviderState(p);
  };
  const setPickCache = (list) => {
    cacheRef.current = list;
    setCache(list);
  };
  /** Show the suggestion panel filtered by `q` (hidden while nothing is loaded). */
  const showSuggest = (q) => setSuggest({ open: cacheRef.current.length > 0, q });
  const hideSuggest = () => setSuggest((s) => ({ ...s, open: false }));

  const refreshPatStatus = useCallback(async () => {
    const pid = currentProjectId();
    if (!pid) return;
    const p = providerRef.current;
    try {
      const r = await api(patPath(pid, p));
      setPatStatus(
        r.configured
          ? { kind: "ok", text: `${providerName(p)} PAT configured` }
          : { kind: "muted", text: `No ${providerName(p)} PAT set for this project` },
      );
    } catch {
      setPatStatus({ kind: "muted", text: "PAT status unknown" });
    }
  }, []);

  const loadRepos = useCallback(async () => {
    const pid = currentProjectId();
    if (!pid) return;
    try {
      const r = await api(`/api/projects/${pid}/repos`);
      setRepos({ pid, list: r.repos });
    } catch {
      /* keep the list */
    }
  }, []);

  const loadSyncStatus = useCallback(async () => {
    try {
      const s = await api("/api/sync/status");
      gitlabHostRef.current = s.gitlab_host || null;
      setSync(syncStatusLine(s));
    } catch {
      /* keep the line */
    }
  }, []);

  useEffect(() => {
    const hook = () => loadSyncStatus();
    window.loadSyncStatus = hook;
    return () => {
      if (window.loadSyncStatus === hook) delete window.loadSyncStatus;
    };
  }, [loadSyncStatus]);

  /** Settings opened for `pid`: start on the project's saved provider (not saved again). */
  const open = useCallback(
    async (pid) => {
      try {
        const proj = await api(`/api/projects/${pid}`);
        setProvider((proj.default_git_provider || "github").toLowerCase());
      } catch {
        /* keep the current toggle */
      }
      refreshPatStatus();
    },
    [refreshPatStatus],
  );

  /** Provider toggle: clears loaded repos and saves the choice on the project. */
  const chooseProvider = async (p) => {
    if (p === providerRef.current) return;
    setProvider(p);
    setPickCache([]);
    hideSuggest();
    const pid = currentProjectId();
    if (pid) {
      try {
        await api(`/api/projects/${pid}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ default_git_provider: p }),
        });
      } catch {
        /* the toggle still applies for this session */
      }
    }
    await refreshPatStatus();
  };

  const savePat = async () => {
    const token = pat.trim();
    if (!token) {
      toast("Enter a PAT first", true);
      return;
    }
    try {
      await api(patPath(currentProjectId(), providerRef.current), {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pat: token }),
      });
      setPat("");
      toast("PAT saved");
      refreshPatStatus();
    } catch (e) {
      toast(e.message, { type: "err", title: "Couldn't save project token" });
    }
  };

  const clearPat = async () => {
    try {
      await api(patPath(currentProjectId(), providerRef.current), { method: "DELETE" });
      setPat("");
      toast("PAT cleared");
      refreshPatStatus();
    } catch (e) {
      toast(e.message, { type: "err", title: "Couldn't clear project token" });
    }
  };

  const addRepo = async () => {
    const url = repoUrl.trim();
    const pid = currentProjectId();
    if (!url || !pid) return;
    try {
      await api(`/api/projects/${pid}/repos`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url, kind: repoKind, repo_type: repoType, git_provider: providerRef.current }),
      });
      urlRef.current = "";
      setRepoUrl("");
      loadRepos();
      toast("Repo added & watching");
    } catch (e) {
      toast(e.message, { type: "err", title: "Couldn't add repository" });
    }
  };

  /** Typing filters the suggestions and switches the provider to match a pasted URL. */
  const typeRepoUrl = async (raw) => {
    urlRef.current = raw;
    setRepoUrl(raw);
    const value = raw.trim();
    showSuggest(value);
    if (providerForAddress(value, gitlabHostRef.current) === undefined) return;
    if (!gitlabHostRef.current) await loadSyncStatus();
    if (urlRef.current.trim() !== value) return;
    const p = providerForAddress(value, gitlabHostRef.current);
    if (p && p !== providerRef.current) await chooseProvider(p);
  };

  const pickSuggestion = (fullName) => {
    urlRef.current = fullName;
    setRepoUrl(fullName);
    hideSuggest();
  };

  const loadPickList = async () => {
    const pid = currentProjectId();
    if (!pid) return;
    try {
      const r = await api(
        `/api/projects/${pid}/${providerRef.current === "gitlab" ? "gitlab" : "github"}/accessible-repos?page=1`,
      );
      setPickCache(r.repos || []);
      showSuggest("");
      toast(`${cacheRef.current.length} repos loaded — click the box to browse, or type to filter`);
    } catch (e) {
      toast(e.message, { type: "err", title: "Couldn't load repositories" });
    }
  };

  // The suggestion panel closes on a mousedown outside the address box, or Escape.
  useEffect(() => {
    if (!suggest.open) return;
    const onDown = (e) => {
      if (!e.target.closest("[data-repo-suggest-wrap]")) hideSuggest();
    };
    const onKey = (e) => {
      if (e.key === "Escape") hideSuggest();
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [suggest.open]);

  const syncRepo = async (id) => {
    await api(`/api/repos/${id}/sync`, { method: "POST" });
    setSync({ started: true });
    setTimeout(() => {
      loadRepos();
      loadSyncStatus();
    }, 1500);
  };

  const toggleWatch = async (id, watch) => {
    await api(`/api/repos/${id}/watch`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ watch }),
    });
    loadRepos();
  };

  const removeRepo = async (id) => {
    if (!(await uiConfirm("Remove this repo and its tracked PRs?", "Delete Repository", "Remove", true))) return;
    await api(`/api/repos/${id}`, { method: "DELETE" });
    loadRepos();
    toast("Repo removed");
  };

  return {
    provider,
    patStatus,
    pat,
    setPat,
    repoUrl,
    repoType,
    setRepoType,
    repoKind,
    setRepoKind,
    suggestOpen: suggest.open,
    suggestions: suggestMatches(cache, suggest.q),
    repos,
    sync,
    open,
    loadRepos,
    chooseProvider,
    savePat,
    clearPat,
    addRepo,
    typeRepoUrl,
    showAllSuggestions: () => showSuggest(""),
    pickSuggestion,
    loadPickList,
    analyzeRepo: (rid, pid) => gotoAnalyze(rid, pid),
    syncRepo,
    toggleWatch,
    removeRepo,
  };
}
