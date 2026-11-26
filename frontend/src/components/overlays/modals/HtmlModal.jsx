import { useEffect, useRef, useState } from "react";

/**
 * Generic HTML dialog (was 00-core.js uiModalHTML). Registers
 * window.uiModalHTML(title, bodyHTML, confirmLabel = "Save"): resolves true on
 * the confirm button, false on Cancel / close. The body stays in the DOM after
 * it resolves so callers can read its inputs. `bodyHTML` is inserted as HTML:
 * callers escape every interpolated value (lib/html.js escapeHtml).
 *
 * The user-access body (users screen manageAccess) gets its scope toggle and
 * project search wired here, as before.
 */
export default function HtmlModal() {
  const [state, setState] = useState({ open: false, title: "", body: "", ok: "Save", seq: 0 });
  const resolver = useRef(null);
  const bodyRef = useRef(null);

  useEffect(() => {
    const fn = (title, bodyHTML, confirmLabel = "Save") =>
      new Promise((resolve) => {
        resolver.current = resolve;
        setState((s) => ({ open: true, title, body: bodyHTML, ok: confirmLabel, seq: s.seq + 1 }));
      });
    window.uiModalHTML = fn;
    return () => {
      if (window.uiModalHTML === fn) delete window.uiModalHTML;
    };
  }, []);

  // Wire the "specific projects" scope toggle and the project search (manageAccess).
  useEffect(() => {
    const root = bodyRef.current;
    if (!state.open || !root) return undefined;
    const scopes = [...root.querySelectorAll('input[name="ma-scope"]')];
    const onScope = () => {
      const some = (document.querySelector('input[name="ma-scope"]:checked') || {}).value === "some";
      const list = document.getElementById("ma-list");
      const search = document.getElementById("ma-search");
      if (list) list.hidden = !some;
      if (search) search.hidden = !some;
    };
    scopes.forEach((r) => (r.onchange = onScope));
    const search = document.getElementById("ma-search");
    const onSearch = () => {
      const q = search.value.trim().toLowerCase();
      document.querySelectorAll("#ma-list label").forEach((l) => {
        l.style.display = !q || (l.getAttribute("data-name") || "").includes(q) ? "" : "none";
      });
    };
    if (search) search.addEventListener("input", onSearch);
    return () => {
      if (search) search.removeEventListener("input", onSearch);
    };
  }, [state.open, state.seq]);

  const done = (v) => {
    const resolve = resolver.current;
    if (!resolve) return;
    resolver.current = null;
    setState((s) => ({ ...s, open: false }));
    resolve(v);
  };

  return (
    <div className={`modal${state.open ? " show" : ""}`} id="html-modal">
      <div className="box" style={{ maxWidth: "520px", width: "92vw" }}>
        <div className="editor-head">
          <h2 id="hm-title" style={{ margin: "0", fontSize: "17px" }}>{state.title}</h2>
          <button className="ghost" id="hm-x" onClick={() => done(false)}>close</button>
        </div>
        {/* Keyed by open count so each open starts from the given HTML. */}
        <div key={state.seq} ref={bodyRef} id="hm-body" style={{ padding: "16px 20px" }} dangerouslySetInnerHTML={{ __html: state.body }} />
        <div className="editor-foot" style={{ display: "flex", gap: "8px", justifyContent: "flex-end", padding: "14px 20px", borderTop: "1px solid var(--line)" }}>
          <button className="ghost" id="hm-cancel" onClick={() => done(false)}>Cancel</button>
          <button className="go" id="hm-ok" onClick={() => done(true)}>{state.ok}</button>
        </div>
      </div>
    </div>
  );
}
