import { useRef, useState } from "react";
import { createPortal } from "react-dom";

import { filterPickerRepos } from "../lib/mindmap.js";

/**
 * "Add a repo from GitHub" overlay (was openGitRepoPicker). Rendered into
 * document.body like the old overlay. As before, filtering redraws the list,
 * so ticks only count for the rows on screen when "Add selected" is clicked.
 */
export default function GitRepoPicker({ repos, onCancel, onAdd }) {
  const [query, setQuery] = useState("");
  const listRef = useRef(null);
  const shown = filterPickerRepos(repos, query);

  const add = () => {
    const picks = [...listRef.current.querySelectorAll(".gitrepo-chk")]
      .filter((x) => x.checked)
      .map((x) => ({ full_name: x.value, def: x.dataset.def }));
    onAdd(picks);
  };

  return createPortal(
    <div
      style={{
        position: "fixed",
        inset: "0",
        background: "rgba(0,0,0,.55)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 9999,
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget) onCancel();
      }}
    >
      <div
        style={{
          background: "#0d151f",
          border: "1px solid var(--line)",
          borderRadius: "14px",
          maxWidth: "680px",
          width: "92%",
          maxHeight: "82vh",
          display: "flex",
          flexDirection: "column",
          padding: "18px",
        }}
      >
        <div style={{ fontWeight: 700, fontSize: "15px", marginBottom: "4px" }}>Add a repo from GitHub</div>
        <div className="muted" style={{ fontSize: "12px", marginBottom: "10px" }}>
          Any repository your GitHub token can access. Selected repos are added to the project and become available to
          analyze here.
        </div>
        <input
          id="gitrepo-q"
          placeholder="Filter repositories…"
          style={{ marginBottom: "10px" }}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <div
          id="gitrepo-list"
          ref={listRef}
          key={query}
          style={{ overflow: "auto", flex: "1", border: "1px solid var(--line)", borderRadius: "8px", padding: "8px" }}
        >
          {shown.length ? (
            shown.map((r) => (
              <label
                key={r.full_name}
                style={{
                  display: "flex",
                  gap: "8px",
                  alignItems: "center",
                  padding: "6px 4px",
                  fontSize: "12.5px",
                  borderBottom: "1px solid rgba(255,255,255,.04)",
                }}
              >
                <input
                  type="checkbox"
                  className="gitrepo-chk"
                  value={r.full_name}
                  data-def={r.default_branch || "main"}
                  style={{ width: "auto" }}
                />
                <span style={{ flex: "1" }}>{r.full_name}</span>
                {r.private ? <span className="pill">private</span> : null}
                {r.language ? <span className="badge">{r.language}</span> : null}
              </label>
            ))
          ) : (
            <div className="muted" style={{ padding: "8px" }}>
              No matches.
            </div>
          )}
        </div>
        <div style={{ display: "flex", justifyContent: "flex-end", gap: "8px", marginTop: "14px" }}>
          <button className="ghost" id="gitrepo-cancel" onClick={onCancel}>
            Cancel
          </button>
          <button className="go" id="gitrepo-add" onClick={add}>
            Add selected
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
