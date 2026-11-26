import { useEffect, useRef, useState } from "react";

/**
 * Shared one-line prompt (was 00-core.js uiPrompt; the file name is historical).
 * Registers window.uiPrompt(title, label, value): resolves the trimmed value on
 * OK / Enter, null on Cancel / Escape.
 */
export default function ProjectAccessModal() {
  const [state, setState] = useState({ open: false, title: "Input", label: "Value" });
  const [value, setValue] = useState("");
  const resolver = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => {
    const fn = (title, label, initial) =>
      new Promise((resolve) => {
        resolver.current = resolve;
        setState({ open: true, title, label: label || "Value" });
        setValue(initial || "");
        setTimeout(() => inputRef.current?.focus(), 50);
      });
    window.uiPrompt = fn;
    return () => {
      if (window.uiPrompt === fn) delete window.uiPrompt;
    };
  }, []);

  const done = (v) => {
    const resolve = resolver.current;
    if (!resolve) return;
    resolver.current = null;
    setState((s) => ({ ...s, open: false }));
    resolve(v);
  };

  return (
    <div className={`modal${state.open ? " show" : ""}`} id="pmodal">
      <div className="box" style={{ maxWidth: "420px" }}>
        <h2 id="pm-title" style={{ margin: "0 0 6px", fontSize: "16px" }}>{state.title}</h2>
        <label id="pm-label">{state.label}</label>
        <input
          id="pm-input"
          ref={inputRef}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") done(value.trim());
            if (e.key === "Escape") done(null);
          }}
        />
        <div style={{ marginTop: "14px", display: "flex", gap: "8px", justifyContent: "flex-end" }}>
          <button className="ghost" id="pm-cancel" onClick={() => done(null)}>Cancel</button>
          <button className="go" id="pm-ok" onClick={() => done(value.trim())}>OK</button>
        </div>
      </div>
    </div>
  );
}
