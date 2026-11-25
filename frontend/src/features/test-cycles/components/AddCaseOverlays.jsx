import { useRef, useState } from "react";
import { createPortal } from "react-dom";

import { typeLabel } from "../../test-cases/lib/testCases.js";
import { filterCases } from "../lib/cycles.js";

/*
 * The "+ Add test cases" overlays of a cycle, rendered into document.body like
 * the old ones: the chooser, the existing-case picker and the feature picker
 * for a new case.
 */

function Overlay({ onClose, children }) {
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
        if (e.target === e.currentTarget) onClose();
      }}
    >
      {children}
    </div>,
    document.body,
  );
}

const BOX = { background: "#0d151f", border: "1px solid var(--line)", borderRadius: "14px", padding: "18px" };

function Chooser({ cid, tc }) {
  return (
    <Overlay onClose={tc.closeOverlay}>
      <div style={{ ...BOX, maxWidth: "420px", width: "88%" }}>
        <div style={{ fontWeight: 700, fontSize: "15px", marginBottom: "12px" }}>Add test cases</div>
        <button className="go" id="acc-existing" style={{ width: "100%", marginBottom: "8px", padding: "9px" }} onClick={() => tc.openAddExisting(cid)}>
          From existing project cases
        </button>{" "}
        <button className="ghost" id="acc-new" style={{ width: "100%", padding: "9px" }} onClick={() => tc.openNewCase(cid)}>
          Create a new test case
        </button>
        <div style={{ textAlign: "right", marginTop: "12px" }}>
          <button className="ghost" id="acc-cancel" onClick={tc.closeOverlay}>
            Cancel
          </button>
        </div>
      </div>
    </Overlay>
  );
}

/** As before, filtering redraws the list, so only ticked rows on screen are added. */
function ExistingCases({ cid, cases, tc }) {
  const [query, setQuery] = useState("");
  const listRef = useRef(null);
  const shown = filterCases(cases, query);
  const add = () =>
    tc.addExisting(
      cid,
      [...listRef.current.querySelectorAll(".addcase-chk")].filter((x) => x.checked).map((x) => x.value),
    );
  return (
    <Overlay onClose={tc.closeOverlay}>
      <div style={{ ...BOX, maxWidth: "660px", width: "92%", maxHeight: "80vh", display: "flex", flexDirection: "column" }}>
        <div style={{ fontWeight: 700, fontSize: "15px", marginBottom: "4px" }}>Add existing test cases</div>
        <div className="muted" style={{ fontSize: "12px", marginBottom: "10px" }}>
          Pick cases from this project to add to the cycle.
        </div>
        <input
          id="addcase-q"
          placeholder="Filter by title or ID…"
          style={{ marginBottom: "10px" }}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <div
          id="addcase-list"
          ref={listRef}
          key={query}
          style={{ overflow: "auto", flex: "1", border: "1px solid var(--line)", borderRadius: "8px", padding: "8px" }}
        >
          {shown.length ? (
            shown.map((c) => (
              <label
                key={c.id}
                style={{
                  display: "flex",
                  gap: "8px",
                  alignItems: "center",
                  padding: "6px 4px",
                  fontSize: "12.5px",
                  borderBottom: "1px solid rgba(255,255,255,.04)",
                }}
              >
                <input type="checkbox" className="addcase-chk" value={c.id} style={{ width: "auto" }} />
                {c.display_id ? <code style={{ fontSize: "10px", color: "#94a3b8" }}>{c.display_id}</code> : null}
                <span style={{ flex: "1" }}>{c.title}</span>
                <span className={`badge ${c.type}`}>{typeLabel(c.type)}</span>
              </label>
            ))
          ) : (
            <div className="muted" style={{ padding: "8px" }}>
              No matching cases.
            </div>
          )}
        </div>
        <div style={{ display: "flex", justifyContent: "flex-end", gap: "8px", marginTop: "14px" }}>
          <button className="ghost" id="addcase-cancel" onClick={tc.closeOverlay}>
            Cancel
          </button>
          <button className="go" id="addcase-add" onClick={add}>
            Add selected
          </button>
        </div>
      </div>
    </Overlay>
  );
}

function FeatureChooser({ cid, features, tc }) {
  const [fid, setFid] = useState(features[0].id);
  return (
    <Overlay onClose={tc.closeOverlay}>
      <div style={{ ...BOX, maxWidth: "460px", width: "90%" }}>
        <div style={{ fontWeight: 700, fontSize: "15px", marginBottom: "6px" }}>New test case → which feature?</div>
        <div className="muted" style={{ fontSize: "12px", marginBottom: "10px" }}>
          Every test case belongs to a feature. It&apos;ll also be added to this cycle and tagged <code>from-test-cycle</code>.
        </div>
        <select id="ncf-feat" style={{ width: "100%" }} value={fid} onChange={(e) => setFid(e.target.value)}>
          {features.map((f) => (
            <option key={f.id} value={f.id}>
              {f.name}
            </option>
          ))}
        </select>
        <div style={{ display: "flex", justifyContent: "flex-end", gap: "8px", marginTop: "14px" }}>
          <button className="ghost" id="ncf-cancel" onClick={tc.closeOverlay}>
            Cancel
          </button>
          <button className="go" id="ncf-go" onClick={() => tc.pickFeature(cid, fid)}>
            Continue
          </button>
        </div>
      </div>
    </Overlay>
  );
}

export default function AddCaseOverlays({ tc }) {
  const o = tc.overlay;
  if (!o) return null;
  if (o.kind === "chooser") return <Chooser cid={o.cid} tc={tc} />;
  if (o.kind === "existing") return <ExistingCases cid={o.cid} cases={o.cases} tc={tc} />;
  return <FeatureChooser cid={o.cid} features={o.features} tc={tc} />;
}
