import { useEffect, useRef, useState } from "react";

const INITIAL = {
  show: false,
  title: "Confirm testcase update",
  copy: "",
  summary: "",
  error: "",
  confirmLabel: "Update testcase",
  danger: false,
  cancel: true,
  secondaryLabel: "",
};

/**
 * The shared confirm dialog (was openCaseConfirmation / openInfoDialog in
 * 04-test-cases.js and uiConfirm in 00-core.js). Registered while mounted:
 *   window.openCaseConfirmation({ title, copy, summary (HTML — escape it), confirmLabel,
 *     danger, onConfirm, secondaryLabel, onSecondary })
 *     — an error thrown by onConfirm / onSecondary is shown in the dialog, which stays open.
 *   window.openInfoDialog({ title, copy, summary, closeLabel })
 *   window.uiConfirm(msg, title, confirmLabel, danger) → Promise<boolean>
 * Closing keeps the last content, as before (it is only hidden).
 */
export default function CaseConfirmationModal() {
  const [s, setS] = useState(INITIAL);
  const [busy, setBusy] = useState({ confirm: false, secondary: false });
  const actions = useRef({ confirm: null, secondary: null, cancel: null });

  useEffect(() => {
    const close = () => setS((x) => ({ ...x, show: false }));
    const run = (key, fn) => async () => {
      try {
        setBusy((b) => ({ ...b, [key]: true }));
        await fn();
        close();
      } catch (e) {
        setS((x) => ({ ...x, error: e.message }));
      } finally {
        setBusy((b) => ({ ...b, [key]: false }));
      }
    };
    const openCaseConfirmation = ({
      title,
      copy,
      summary,
      confirmLabel,
      danger = false,
      onConfirm,
      secondaryLabel = null,
      onSecondary = null,
    }) => {
      actions.current = {
        confirm: run("confirm", onConfirm),
        secondary: secondaryLabel ? run("secondary", onSecondary) : null,
        cancel: close,
      };
      setS({
        show: true,
        title,
        copy,
        summary: summary || "",
        error: "",
        confirmLabel,
        danger,
        cancel: true,
        secondaryLabel: secondaryLabel || "",
      });
    };
    const openInfoDialog = ({ title, copy, summary, closeLabel = "Close" }) => {
      actions.current = { ...actions.current, confirm: close, secondary: null };
      setS((x) => ({
        ...x,
        show: true,
        title,
        copy,
        summary: summary || "",
        error: "",
        confirmLabel: closeLabel,
        danger: false,
        cancel: false,
        secondaryShown: false,
      }));
    };
    const uiConfirm = (msg, title = "Confirm Action", confirmLabel = "Confirm", danger = false) =>
      new Promise((res) => {
        openCaseConfirmation({ title, copy: msg, summary: "", confirmLabel, danger, onConfirm: () => res(true) });
        actions.current.cancel = () => {
          close();
          res(false);
        };
      });
    const hooks = { openCaseConfirmation, openInfoDialog, uiConfirm };
    Object.assign(window, hooks);
    return () => {
      for (const [k, fn] of Object.entries(hooks)) if (window[k] === fn) delete window[k];
    };
  }, []);

  const secondaryShown = s.secondaryShown !== false && !!s.secondaryLabel;
  return (
    <div className={`modal${s.show ? " show" : ""}`} id="case-confirm">
      <div className="box confirm-box">
        <h2 id="cc-title" style={{ margin: "0", fontSize: "17px" }}>
          {s.title}
        </h2>
        <div id="cc-copy" className="muted" style={{ marginTop: "5px" }}>
          {s.copy}
        </div>
        {/* Hidden when empty so it doesn't show as a stray box. */}
        <div
          id="cc-summary"
          className="confirm-summary"
          style={{ display: s.summary ? "" : "none" }}
          dangerouslySetInnerHTML={{ __html: s.summary }}
        />
        <div id="cc-error" className="err">
          {s.error}
        </div>
        <div style={{ display: "flex", justifyContent: "flex-end", gap: "8px", marginTop: "16px" }}>
          <button
            className="danger"
            id="cc-secondary"
            style={{ display: secondaryShown ? "" : "none", marginRight: "auto" }}
            disabled={busy.secondary}
            onClick={() => actions.current.secondary && actions.current.secondary()}
          >
            {s.secondaryLabel}
          </button>
          <button
            className="ghost"
            id="cc-cancel"
            style={{ display: s.cancel ? "" : "none" }}
            onClick={() => actions.current.cancel && actions.current.cancel()}
          >
            Cancel
          </button>
          <button
            className={s.danger ? "danger" : "go"}
            id="cc-confirm"
            disabled={busy.confirm}
            onClick={() => actions.current.confirm && actions.current.confirm()}
          >
            {s.confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
