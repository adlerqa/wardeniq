import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "../../../lib/api.js";

/**
 * Configuration screen data (was loadConfig / loadDbStatus in
 * 06-configuration.js). navigateTo("config") in 00-core.js calls
 * window.loadConfig(), registered while mounted; nothing loads on mount.
 *
 * `version` goes up on every successful settings load. Cards re-read their
 * fields from the settings when it changes (as loadConfig rewrote them), but
 * keep what was typed into secret fields (keys, tokens, passwords), which
 * loadConfig never touched.
 */
export default function useConfiguration() {
  const [config, setConfig] = useState({ settings: null, version: 0 });
  const [db, setDb] = useState({ status: "idle", data: null, error: "", shown: false });
  const version = useRef(0);
  const dbSeq = useRef(0);

  const loadDbStatus = useCallback(async () => {
    const my = ++dbSeq.current;
    setDb((d) => ({ ...d, status: "loading" }));
    try {
      const data = await api("/api/db-status");
      if (my === dbSeq.current) setDb({ status: "ready", data, error: "", shown: true });
    } catch (e) {
      if (my === dbSeq.current)
        setDb({ status: "error", data: null, error: e.message || "could not load database status", shown: true });
    }
  }, []);

  /** Load the settings; resolves to the new version, or null when it failed (silently, as before). */
  const loadConfig = useCallback(async () => {
    try {
      const settings = await api("/api/settings");
      version.current += 1;
      setConfig({ settings, version: version.current });
      loadDbStatus();
      return version.current;
    } catch {
      return null;
    }
  }, [loadDbStatus]);

  /** PUT a settings section, then reload. Resolves to the version to tag messages with. */
  const saveSettings = useCallback(
    async (body) => {
      await api("/api/settings", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const v = await loadConfig();
      return v ?? version.current;
    },
    [loadConfig],
  );

  useEffect(() => {
    const hook = () => loadConfig();
    window.loadConfig = hook;
    return () => {
      if (window.loadConfig === hook) delete window.loadConfig;
    };
  }, [loadConfig]);

  return { ...config, db, loadConfig, loadDbStatus, saveSettings };
}
