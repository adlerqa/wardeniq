/* eslint-disable react-refresh/only-export-components --
   Provider module: intentionally co-locates the <ModalProvider> component with
   the Promise-based `uiPrompt` / `uiConfirm` / `uiModalHTML` helpers and the
   `useModal()` hook (they share module-level state and the same React context),
   so Fast Refresh's component-only export rule is waived for this file. */
import { createContext, useCallback, useContext, useEffect, useState } from "react";

// Global modal helpers — Promise-based prompt / confirm / custom HTML modals
// that replace window.prompt / window.confirm and match the legacy
// `uiPrompt` / `uiConfirm` / `uiModalHTML` helpers.

const ModalContext = createContext(null);

let externalPrompt = null;
let externalConfirm = null;
let externalHtml = null;

export function uiPrompt(title, label, value = "") {
  if (externalPrompt) return externalPrompt(title, label, value);
  return Promise.resolve(window.prompt(label || title, value));
}

export function uiConfirm(
  msg,
  title = "Confirm Action",
  confirmLabel = "Confirm",
  danger = false
) {
  if (externalConfirm) return externalConfirm({ msg, title, confirmLabel, danger });
   
  return Promise.resolve(window.confirm(msg));
}

export function uiModalHTML(title, bodyHTML, confirmLabel = "Save") {
  if (externalHtml) return externalHtml({ title, bodyHTML, confirmLabel });
  return Promise.resolve(null);
}

export function ModalProvider({ children }) {
  const [prompt, setPrompt] = useState(null);
  const [confirm, setConfirm] = useState(null);
  const [html, setHtml] = useState(null);
  const [promptValue, setPromptValue] = useState("");

  const openPrompt = useCallback((title, label, value = "") => {
    setPromptValue(value ?? "");
    return new Promise((resolve) => {
      setPrompt({ title, label, resolve });
    });
  }, []);

  const openConfirm = useCallback(({ msg, title, confirmLabel, danger }) => {
    return new Promise((resolve) => {
      setConfirm({ msg, title, confirmLabel, danger, resolve });
    });
  }, []);

  const openHtml = useCallback(({ title, bodyHTML, confirmLabel }) => {
    return new Promise((resolve) => {
      setHtml({ title, bodyHTML, confirmLabel, resolve });
    });
  }, []);

  useEffect(() => {
    externalPrompt = openPrompt;
    externalConfirm = openConfirm;
    externalHtml = openHtml;
    return () => {
      if (externalPrompt === openPrompt) externalPrompt = null;
      if (externalConfirm === openConfirm) externalConfirm = null;
      if (externalHtml === openHtml) externalHtml = null;
    };
  }, [openPrompt, openConfirm, openHtml]);

  const closePrompt = (value) => {
    if (prompt) prompt.resolve(value);
    setPrompt(null);
  };
  const closeConfirm = (value) => {
    if (confirm) confirm.resolve(value);
    setConfirm(null);
  };
  const closeHtml = (value) => {
    if (html) html.resolve(value);
    setHtml(null);
  };

  return (
    <ModalContext.Provider value={{ openPrompt, openConfirm, openHtml }}>
      {children}

      {prompt && (
        <div className="modal show" role="dialog" aria-modal="true">
          <div className="box">
            <h3 style={{ margin: "0 0 10px" }}>{prompt.title}</h3>
            <label>{prompt.label || "Value"}</label>
            <input
              autoFocus
              value={promptValue}
              onChange={(e) => setPromptValue(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") closePrompt(promptValue.trim());
                if (e.key === "Escape") closePrompt(null);
              }}
            />
            <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 12 }}>
              <button className="ghost" onClick={() => closePrompt(null)}>
                Cancel
              </button>
              <button className="go" onClick={() => closePrompt(promptValue.trim())}>
                OK
              </button>
            </div>
          </div>
        </div>
      )}

      {confirm && (
        <div className="modal show" role="dialog" aria-modal="true">
          <div className="box">
            <h3 style={{ margin: "0 0 10px" }}>{confirm.title}</h3>
            <p style={{ margin: "0 0 14px", fontSize: 13 }}>{confirm.msg}</p>
            <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
              <button className="ghost" onClick={() => closeConfirm(false)}>
                Cancel
              </button>
              <button
                className={confirm.danger ? "danger" : "go"}
                onClick={() => closeConfirm(true)}
              >
                {confirm.confirmLabel || "Confirm"}
              </button>
            </div>
          </div>
        </div>
      )}

      {html && (
        <div className="modal show" role="dialog" aria-modal="true">
          <div className="box" style={{ maxWidth: 720 }}>
            <h3 style={{ margin: "0 0 10px" }}>{html.title}</h3>
            { }
            <div dangerouslySetInnerHTML={{ __html: html.bodyHTML }} />
            <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 14 }}>
              <button className="ghost" onClick={() => closeHtml(null)}>
                Cancel
              </button>
              <button className="go" onClick={() => closeHtml(true)}>
                {html.confirmLabel || "Save"}
              </button>
            </div>
          </div>
        </div>
      )}
    </ModalContext.Provider>
  );
}

export function useModal() {
  return useContext(ModalContext);
}
