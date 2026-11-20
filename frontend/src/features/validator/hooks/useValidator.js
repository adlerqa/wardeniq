import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "../../../lib/api.js";
import {
  currentFeatureId,
  currentFeatureName,
  toast,
  uiConfirm,
  usageLogLines,
  watchJob,
} from "../../../lib/compatBridge.js";
import {
  MSG_ANSWER_ALL,
  RETAKE_CONFIRM,
  hasUnanswered,
  initialAnswers,
  jobLogLines,
  submitPayload,
} from "../lib/validator.js";

const INITIAL = {
  hasFeature: false,
  title: "MCQ Validator",
  progressVisible: false,
  barWidth: 0, // percent
  logVisible: false,
  logLines: [],
  status: { text: "", error: false },
  qa: null, // null | { kind: "skeleton", label } | { kind: "questions", questions }
  results: null, // score from the API
  generateVisible: true,
  generateDisabled: false,
  retakeVisible: true,
  retakeDisabled: false,
  answers: {},
  submitting: false,
};

const ok = (text) => ({ text, error: false });
const err = (text) => ({ text, error: true });

/**
 * State and actions for the MCQ Validator screen, ported from the compat
 * 12-validator.js (initValidator, runValidator, watchValidatorJob, answer
 * handlers, submit, retake). navigateTo("validator") in 00-core.js calls
 * window.initValidator(); this hook registers it while mounted.
 *
 * One deliberate difference: opening the screen again stops following the
 * previous generation job, so a job for another feature cannot replace what
 * is on screen.
 */
export default function useValidator() {
  const [state, setState] = useState(INITIAL);
  const mounted = useRef(false);
  const stopJob = useRef(null);
  const retryTimer = useRef(null);
  const runId = useRef(null);
  const seq = useRef(0);
  const answersRef = useRef({});
  const initRef = useRef(() => {});

  const patch = useCallback((p) => {
    if (!mounted.current) return;
    if (p.answers) answersRef.current = p.answers;
    setState((prev) => ({ ...prev, ...p }));
  }, []);

  const stop = useCallback(() => {
    if (stopJob.current) stopJob.current();
    stopJob.current = null;
    clearTimeout(retryTimer.current);
    retryTimer.current = null;
  }, []);

  const showResults = useCallback((score) => patch({ qa: null, results: score }), [patch]);

  const watch = useCallback(
    (jobId) => {
      if (stopJob.current) stopJob.current();
      stopJob.current = null;
      patch({
        progressVisible: true,
        logVisible: true,
        status: ok("Generating validator questions…"),
      });
      if (!jobId) {
        retryTimer.current = setTimeout(() => initRef.current(), 1500);
        return;
      }
      stopJob.current = watchJob(jobId, (j) => {
        const lines = jobLogLines(j, usageLogLines);
        patch({
          barWidth: j.progress || 5,
          logLines: lines,
          logVisible: lines.length > 0,
          status: ok(j.status === "running" ? j.stage || "Generating…" : ""),
        });
        if (j.status === "succeeded") initRef.current();
        if (j.status === "failed") {
          patch({
            progressVisible: false,
            logVisible: false,
            qa: null,
            status: err(j.error || "Validator generation failed"),
            generateVisible: true,
            generateDisabled: false,
          });
        }
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
      title: `${currentFeatureName() || "Feature"} — MCQ Validator`,
      results: null,
      qa: { kind: "skeleton", label: "Loading validator" },
      progressVisible: false,
      logVisible: false,
      generateVisible: false,
      retakeVisible: false,
      status: ok("Loading validator..."),
    });
    try {
      const res = await api(`/api/features/${featureId}/validator/latest`);
      if (!current()) return;
      if (!res || res.mode === "none") {
        patch({
          qa: null,
          status: ok("No validator generated yet."),
          generateVisible: true,
          generateDisabled: false,
        });
        return;
      }
      runId.current = res.run && res.run.id;
      if (res.mode === "generating") {
        watch(res.run && res.run.job_id);
        return;
      }
      patch({ qa: null, status: ok(""), retakeVisible: true, retakeDisabled: false });
      if (res.mode === "score") {
        showResults(res.score);
      } else {
        patch({
          answers: initialAnswers(res.questions, res.answers),
          qa: { kind: "questions", questions: res.questions },
          submitting: false,
        });
      }
    } catch (e) {
      if (!current()) return;
      patch({ progressVisible: false, qa: null, status: err(e.message) });
    }
  }, [patch, showResults, stop, watch]);
  initRef.current = init;

  const run = useCallback(
    async (forceNew) => {
      const featureId = currentFeatureId();
      if (!featureId) return;
      patch({
        results: null,
        generateVisible: false,
        retakeDisabled: true,
        qa: { kind: "skeleton", label: "Generating validator questions" },
        progressVisible: true,
        barWidth: 40,
        status: ok("Loading validator..."),
      });
      try {
        const res = await api(`/api/features/${featureId}/validator`, {
          method: "POST",
          json: { forceNew },
        });
        runId.current = res.run && res.run.id;
        if (res.mode === "generating") {
          watch(res.job_id || (res.run && res.run.job_id));
          return;
        }
        // An existing run was returned directly: reload the view to render it.
        initRef.current();
      } catch (e) {
        patch({
          progressVisible: false,
          qa: null,
          status: err(e.message),
          generateVisible: true,
          generateDisabled: false,
        });
      }
    },
    [patch, watch],
  );

  const setAnswer = useCallback(
    (qid, change) => {
      const answers = { ...answersRef.current, [qid]: { ...answersRef.current[qid], ...change } };
      patch({ answers });
    },
    [patch],
  );

  const submit = useCallback(async () => {
    const answers = answersRef.current;
    if (hasUnanswered(answers)) {
      toast(MSG_ANSWER_ALL, true);
      return;
    }
    patch({ submitting: true });
    try {
      const score = await api(`/api/validator/runs/${runId.current}/submit`, {
        method: "POST",
        json: submitPayload(answers),
      });
      toast("Answers submitted!");
      showResults(score);
    } catch (e) {
      toast(e.message, true);
      patch({ submitting: false });
    }
  }, [patch, showResults]);

  const retake = useCallback(async () => {
    if (await uiConfirm(RETAKE_CONFIRM, "Retake Validator")) run(true);
  }, [run]);

  useEffect(() => {
    mounted.current = true;
    const hook = () => initRef.current();
    window.initValidator = hook;
    return () => {
      mounted.current = false;
      seq.current += 1;
      stop();
      if (window.initValidator === hook) delete window.initValidator;
    };
  }, [stop]);

  return {
    state,
    generate: () => run(false),
    retake,
    selectOption: (qid, index) => setAnswer(qid, { selectedIndex: index }),
    selectConfidence: (qid, level) => setAnswer(qid, { confidence: level }),
    setComment: (qid, comment) => setAnswer(qid, { comment }),
    submit,
  };
}
