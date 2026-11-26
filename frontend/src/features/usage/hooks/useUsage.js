import { useCallback, useEffect, useState } from "react";

import { api } from "../../../lib/api.js";
import { keepValue, modelRows, projectOptions } from "../lib/usage.js";

/**
 * LLM Usage & Cost (was loadUsage in 03-features-and-usage.js).
 * navigateTo("usage") in app/navigation.js calls window.loadUsage(), registered while
 * mounted; nothing loads on mount. A failed reload shows the error in place of
 * the KPI cards and keeps the tables from the last load, as before.
 */
export default function useUsage() {
  const [data, setData] = useState(null); // { totals, models, projects, recent }
  const [error, setError] = useState("");
  const [modelOpts, setModelOpts] = useState([]);
  const [projectOpts, setProjectOpts] = useState([]);
  const [search, setSearch] = useState("");
  const [model, setModel] = useState("");
  const [project, setProject] = useState("");

  const loadUsage = useCallback(async () => {
    try {
      const r = await api("/api/usage"); // global view — the tables break it down by project
      const models = modelRows(r.by_model);
      const projects = r.by_project || [];
      let names = [];
      try {
        const pr = await api("/api/projects");
        names = (pr.projects || pr || []).map((p) => p.name).filter(Boolean);
      } catch {
        /* only projects with usage */
      }
      const mOpts = models.map(([m]) => m);
      const pOpts = projectOptions(projects, names);
      setError("");
      setData({ totals: r.totals || {}, models, projects, recent: r.recent || [] });
      setModelOpts(mOpts);
      setModel((v) => keepValue(v, mOpts));
      setProjectOpts(pOpts);
      setProject((v) => keepValue(v, pOpts));
    } catch (e) {
      setError(e.message);
    }
  }, []);

  useEffect(() => {
    const hook = () => loadUsage();
    window.loadUsage = hook;
    return () => {
      if (window.loadUsage === hook) delete window.loadUsage;
    };
  }, [loadUsage]);

  return { data, error, modelOpts, projectOpts, search, setSearch, model, setModel, project, setProject, loadUsage };
}
