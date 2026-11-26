import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "../../../lib/api.js";
import { currentFeatureId, currentFeatureName } from "../../../lib/compatBridge.js";

const INITIAL = {
  hasFeature: false,
  title: "Test Plan",
  progress: null, // null (hidden) | 20 | 30 | 60
  status: { text: "", error: false },
  content: null, // null (hidden) | { kind: "skeleton", blocks, label } | { kind: "plan", plan }
  mono: true, // content font: monospace, or inherited while generating
  generateVisible: true,
  generateDisabled: false,
  exportRunId: null,
};

const ok = (text) => ({ text, error: false });
const err = (text) => ({ text, error: true });

/**
 * State and actions for the Test Plan screen, ported from the compat
 * 14-test-plan.js (initTestPlan, the Generate handler, watchTestPlanStream).
 * The screen opens through navigateTo("testplan") in app/navigation.js, which calls
 * window.initTestPlan(); this hook registers it while mounted.
 *
 * One deliberate difference: re-opening the screen closes the previous
 * generation stream, so a plan still streaming for another feature can no
 * longer overwrite the one on screen.
 */
export default function useTestPlan() {
  const [state, setState] = useState(INITIAL);
  const mounted = useRef(false);
  const stream = useRef(null);
  const retryTimer = useRef(null);
  const seq = useRef(0);

  const patch = useCallback((p) => {
    if (mounted.current) setState((prev) => ({ ...prev, ...p }));
  }, []);

  const stop = useCallback(() => {
    if (stream.current) stream.current.close();
    stream.current = null;
    clearTimeout(retryTimer.current);
    retryTimer.current = null;
  }, []);

  // `init` and `watch` call each other (retry after a lost stream), so `init`
  // is reached through a ref.
  const initRef = useRef(() => {});

  const watch = useCallback(
    (runId) => {
      if (stream.current) stream.current.close();
      patch({
        progress: 30,
        status: ok("Synthesizing test plan via LLM..."),
        mono: false,
        content: { kind: "skeleton", blocks: [5, 4, 6], label: "Generating test plan" },
        generateVisible: false,
        exportRunId: null,
      });
      const es = new EventSource(`/api/test-plan/runs/${runId}/stream`);
      stream.current = es;
      const close = () => {
        es.close();
        if (stream.current === es) stream.current = null;
      };
      es.addEventListener("status", (e) => {
        if (stream.current !== es) return;
        const payload = JSON.parse(e.data);
        if (payload.status === "COMPLETED") {
          close();
          patch({
            progress: null,
            status: ok("Completed"),
            mono: true,
            content: { kind: "plan", plan: payload.testPlan },
            exportRunId: runId,
          });
        } else if (payload.status === "FAILED") {
          close();
          patch({
            progress: null,
            content: null,
            status: err("Failed to generate test plan."),
            generateVisible: true,
            generateDisabled: false,
          });
        } else {
          patch({ progress: 60, status: ok("Synthesizing sections via LLM...") });
        }
      });
      es.addEventListener("done", () => close());
      es.addEventListener("error", () => {
        if (stream.current !== es) return;
        close();
        patch({ progress: null, status: err("Connection lost. Re-checking...") });
        retryTimer.current = setTimeout(() => initRef.current(), 2000);
      });
    },
    [patch],
  );

  const init = useCallback(async () => {
    stop();
    const mySeq = ++seq.current;
    const current = () => mounted.current && mySeq === seq.current;
    const featureId = currentFeatureId();
    if (!featureId) {
      patch({ hasFeature: false });
      return;
    }
    patch({
      hasFeature: true,
      title: `${currentFeatureName() || "Feature"} — Test Plan`,
      content: { kind: "skeleton", blocks: [5, 4], label: "Loading test plan" },
      progress: 30,
      status: ok("Loading test plan status..."),
      generateVisible: false,
      exportRunId: null,
    });
    try {
      const res = await api(`/api/features/${featureId}/test-plan/latest`);
      if (!current()) return;
      const run = res.run;
      if (!run) {
        patch({
          progress: null,
          content: null,
          status: ok("No test plan generated yet."),
          generateVisible: true,
          generateDisabled: false,
        });
      } else if (run.status === "COMPLETED") {
        patch({
          progress: null,
          status: ok(""),
          content: { kind: "plan", plan: run.content },
          exportRunId: run.id,
        });
      } else if (run.status === "PROCESSING") {
        watch(run.id);
      } else {
        patch({
          progress: null,
          content: null,
          status: err("Previous generation failed."),
          generateVisible: true,
          generateDisabled: false,
        });
      }
    } catch (e) {
      if (!current()) return;
      patch({ progress: null, content: null, status: err(e.message) });
    }
  }, [patch, stop, watch]);
  initRef.current = init;

  const generate = useCallback(async () => {
    const featureId = currentFeatureId();
    if (!featureId) return;
    patch({
      generateDisabled: true,
      status: ok("Initializing test plan run..."),
      progress: 20,
    });
    try {
      const res = await api(`/api/features/${featureId}/test-plan`, { method: "POST" });
      watch(res.runId);
    } catch (e) {
      patch({ progress: null, status: err(e.message), generateDisabled: false });
    }
  }, [patch, watch]);

  useEffect(() => {
    mounted.current = true;
    const hook = () => initRef.current();
    window.initTestPlan = hook;
    return () => {
      mounted.current = false;
      seq.current += 1;
      stop();
      if (window.initTestPlan === hook) delete window.initTestPlan;
    };
  }, [stop]);

  return { state, generate };
}
