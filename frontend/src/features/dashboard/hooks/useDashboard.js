import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "../../../lib/api.js";

/**
 * Dashboard data. navigateTo("dashboard") in app/navigation.js calls
 * window.loadDashboard(); this hook registers it while mounted.
 */
export default function useDashboard() {
  const [state, setState] = useState({ status: "idle", data: null, error: "" });
  const mounted = useRef(false);
  const seq = useRef(0);

  const load = useCallback(async () => {
    const my = ++seq.current;
    setState((s) => ({ ...s, status: "loading" }));
    try {
      const data = await api("/api/dashboard");
      if (mounted.current && my === seq.current) setState({ status: "ready", data, error: "" });
    } catch (e) {
      if (mounted.current && my === seq.current) setState({ status: "error", data: null, error: e.message });
    }
  }, []);

  useEffect(() => {
    mounted.current = true;
    const hook = () => load();
    window.loadDashboard = hook;
    return () => {
      mounted.current = false;
      if (window.loadDashboard === hook) delete window.loadDashboard;
    };
  }, [load]);

  return { ...state, reload: load };
}
