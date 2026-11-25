import { useRef, useState } from "react";

import { api } from "../../../lib/api.js";
import { openProjectFeatures, setCurrentProject, toast, updateBackbar } from "../../../lib/compatBridge.js";
import {
  confluenceChoices,
  connectingText,
  createBody,
  defaultRepoLabel,
  jiraChoices,
  stagedRepoBodies,
} from "../lib/projects.js";

const EMPTY_LIST = { options: [], status: null }; // status: null | { kind: "text" | "err", text }

/**
 * The "Create project" wizard (was the NEW_PROJ form in 02-projects.js).
 * `pj` is useProjects(): the wizard opens and closes through its page switch.
 *
 * status lines: null | { kind: "text" | "err" | "ok" | "spin", text }
 */
export default function useCreateProject(pj) {
  const [provider, setProvider] = useState("github");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [pat, setPat] = useState("");
  const [nameErr, setNameErr] = useState("");
  const [jira, setJira] = useState(EMPTY_LIST);
  const [jiraKey, setJiraKey] = useState("");
  const [confluence, setConfluence] = useState(EMPTY_LIST);
  const [confKey, setConfKey] = useState("");
  const [available, setAvailable] = useState([]);
  const [appRepos, setAppRepos] = useState([]); // [{ full_name, label, kind }]
  const [testRepos, setTestRepos] = useState([]);
  const [patStatus, setPatStatus] = useState(null);
  const [loadingRepos, setLoadingRepos] = useState(false);
  const [createStatus, setCreateStatus] = useState(null);
  const [saving, setSaving] = useState(false);
  const nameRef = useRef(null);

  const loadJira = async () => {
    setJira((j) => ({ ...j, status: { kind: "text", text: "Loading…" } }));
    try {
      const r = await api("/api/atlassian/accessible-jira-projects");
      const c = jiraChoices(r.projects || []);
      setJira({ options: c.options, status: { kind: "text", text: c.status } });
      setJiraKey("");
    } catch (e) {
      setJira((j) => ({ ...j, status: { kind: "err", text: e.message } }));
    }
  };

  const loadConfluence = async () => {
    setConfluence((c) => ({ ...c, status: { kind: "text", text: "Loading…" } }));
    try {
      const r = await api("/api/atlassian/accessible-confluence-spaces");
      const c = confluenceChoices(r.spaces || []);
      setConfluence({ options: c.options, status: { kind: "text", text: c.status } });
      setConfKey("");
    } catch (e) {
      setConfluence((c) => ({ ...c, status: { kind: "err", text: e.message } }));
    }
  };

  /** "+ New project": a blank wizard; the Jira / Confluence lists load right away. */
  const open = () => {
    setProvider("github");
    setName("");
    setDescription("");
    setPat("");
    setNameErr("");
    setPatStatus(null);
    setCreateStatus(null);
    setJira(EMPTY_LIST);
    setJiraKey("");
    setConfluence(EMPTY_LIST);
    setConfKey("");
    setAvailable([]);
    setAppRepos([]);
    setTestRepos([]);
    pj.showProjectCreate();
    setTimeout(() => nameRef.current && nameRef.current.focus(), 0);
    loadJira();
    loadConfluence();
  };

  const chooseProvider = (p) => {
    setProvider(p);
    setAvailable([]);
    setAppRepos([]);
    setTestRepos([]);
    setPatStatus(null);
  };

  const loadRepos = async () => {
    const token = pat.trim();
    if (!token) {
      setPatStatus({ kind: "err", text: "Enter a PAT first" });
      return;
    }
    setLoadingRepos(true);
    setPatStatus({ kind: "spin", text: "Loading repositories…" });
    try {
      let repos = [];
      for (let page = 1; page <= 5; page++) {
        const url = `/api/git/accessible-repos?provider=${encodeURIComponent(provider)}&page=${page}`;
        const r = await api(url, { headers: { "X-Provider-PAT": token } });
        if (!r.repos || !r.repos.length) break;
        repos = repos.concat(r.repos);
        if (r.repos.length < 30) break;
      }
      setAvailable(repos);
      setPatStatus({ kind: "ok", text: `${repos.length} repos loaded` });
    } catch (e) {
      setPatStatus({ kind: "err", text: e.message });
    } finally {
      setLoadingRepos(false);
    }
  };

  const bucket = (key) => (key === "app" ? [appRepos, setAppRepos] : [testRepos, setTestRepos]);
  const addRepo = (key, fullName) => {
    if (!available.some((r) => r.full_name === fullName)) return;
    bucket(key)[1]((rows) => [
      ...rows,
      { full_name: fullName, label: defaultRepoLabel(fullName), kind: key === "test" ? "test" : "BE" },
    ]);
  };
  const removeRepo = (key, fullName) => bucket(key)[1]((rows) => rows.filter((r) => r.full_name !== fullName));
  const updateRepo = (key, fullName, patch) =>
    bucket(key)[1]((rows) => rows.map((r) => (r.full_name === fullName ? { ...r, ...patch } : r)));

  const save = async () => {
    const projectName = name.trim();
    setNameErr("");
    if (!projectName) {
      setNameErr("Project name is required.");
      return;
    }
    const token = pat.trim();
    setCreateStatus({ kind: "spin", text: "Creating project…" });
    setSaving(true);
    let createdId;
    try {
      const r = await api("/api/projects", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(
          createBody({
            name: projectName,
            description: description.trim(),
            jira: jira.options.find((o) => o.value === jiraKey && jiraKey) || null,
            confluence: confluence.options.find((o) => o.value === confKey && confKey) || null,
            provider,
          }),
        ),
      });
      createdId = r.id;
    } catch (e) {
      setCreateStatus({ kind: "err", text: e.message });
      setSaving(false);
      return;
    }

    if (token) {
      try {
        await api(`/api/projects/${createdId}/${provider === "gitlab" ? "gitlab" : "github"}/pat`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ pat: token }),
        });
      } catch (e) {
        toast(`Project created, but PAT save failed: ${e.message}`, {
          type: "warn",
          title: "Project created, but PAT wasn't saved",
        });
      }
      const bodies = stagedRepoBodies(appRepos, testRepos, provider);
      let connected = 0;
      if (bodies.length) setCreateStatus({ kind: "spin", text: connectingText(bodies.length) });
      for (const body of bodies) {
        try {
          await api(`/api/projects/${createdId}/repos`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
          });
          connected += 1;
        } catch (e) {
          toast(`Repo ${body.repo_full_name} failed: ${e.message}`, {
            type: "warn",
            title: "Project created, but repository connection failed",
          });
        }
      }
      toast(connected > 0 ? `Project created · ${connected} repo(s) connected` : "Project created");
    } else {
      toast("Project created");
    }

    setCreateStatus({ kind: "spin", text: "Opening project…" });
    setCurrentProject(createdId);
    pj.showProjectList();
    try {
      await pj.loadProjects();
      await openProjectFeatures(createdId);
      updateBackbar();
    } finally {
      setSaving(false);
      setCreateStatus(null);
    }
  };

  return {
    nameRef,
    provider,
    name,
    setName,
    description,
    setDescription,
    pat,
    setPat,
    nameErr,
    jira,
    jiraKey,
    setJiraKey,
    loadJira,
    confluence,
    confKey,
    setConfKey,
    loadConfluence,
    available,
    appRepos,
    testRepos,
    patStatus,
    loadingRepos,
    createStatus,
    saving,
    open,
    cancel: () => pj.showProjectList(),
    chooseProvider,
    loadRepos,
    addRepo,
    removeRepo,
    updateRepo,
    save,
  };
}
