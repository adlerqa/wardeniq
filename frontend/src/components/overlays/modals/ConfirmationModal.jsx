import { useEffect, useRef, useState } from "react";

/**
 * Styled, promise-based replacement for window.confirm (was 00-core.js
 * confirmModal). Registers window.confirmModal({ title, body, confirmText, danger }):
 * resolves true on Continue / Enter, false on Cancel / backdrop / Escape.
 */
export default function ConfirmationModal() {
  const [state, setState] = useState({ open: false, title: "Please confirm", body: "", ok: "Continue", danger: false });
  const resolver = useRef(null);
  const okRef = useRef(null);

  const close = (value) => {
    const resolve = resolver.current;
    if (!resolve) return;
    resolver.current = null;
    setState((s) => ({ ...s, open: false }));
    resolve(value);
  };
  const closeRef = useRef(close);
  closeRef.current = close;

  useEffect(() => {
    const fn = (opts) => {
      opts = opts || {};
      setState({
        open: true,
        title: opts.title || "Please confirm",
        body: opts.body || "",
        ok: opts.confirmText || "Continue",
        danger: !!opts.danger,
      });
      setTimeout(() => okRef.current?.focus(), 40);
      return new Promise((resolve) => {
        resolver.current = resolve;
      });
    };
    window.confirmModal = fn;
    return () => {
      if (window.confirmModal === fn) delete window.confirmModal;
    };
  }, []);

  useEffect(() => {
    if (!state.open) return undefined;
    const onKey = (e) => {
      if (e.key === "Escape") closeRef.current(false);
      else if (e.key === "Enter") closeRef.current(true);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [state.open]);

  return (
    <div
      className={`modal${state.open ? " show" : ""}`}
      id="confirm-modal"
      onClick={(e) => {
        if (e.target === e.currentTarget) close(false); // backdrop click cancels
      }}
    >
      <div className="box confirm-box" style={{ maxWidth: "460px" }}>
        <h2 id="confirm-title" style={{ margin: "0", fontSize: "17px" }}>{state.title}</h2>
        <div id="confirm-body" className="muted" style={{ marginTop: "8px", lineHeight: "1.5", whiteSpace: "pre-wrap" }}>
          {state.body}
        </div>
        <div style={{ display: "flex", justifyContent: "flex-end", gap: "8px", marginTop: "18px" }}>
          <button className="ghost" id="confirm-cancel" onClick={() => close(false)}>Cancel</button>
          <button ref={okRef} className={state.danger ? "danger" : "go"} id="confirm-ok" onClick={() => close(true)}>
            {state.ok}
          </button>
        </div>
      </div>
    </div>
  );
}
