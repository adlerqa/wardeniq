import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "../../../lib/api.js";
import {
  currentFeatureId,
  currentFeatureName,
  currentProjectId,
  loadFeatures,
  openFeature,
  toast,
} from "../../../lib/compatBridge.js";
import {
  IMPORT_POLL_LIMIT_MS,
  IMPORT_POLL_MS,
  breakdownReason,
  importKpis,
  initialReview,
  priorityTone,
  reviewPayload,
  sourceRow,
  stepsText,
} from "../lib/imports.js";
import { SheetDetail, SheetKpis, SheetPill } from "./SheetParts.jsx";

const ANALYZING = "AI analyzing test cases...";

/**
 * "Import test cases" dialog (was the import half of 15-imports.js): pick a
 * CSV / XLSX, upload it, follow the import job, then review which rows are
 * included in the feature.
 *
 * Opened from the feature card menu and the feature workspace through
 * window.importSheetForFeature(fid, pid) / window.openImportSheetModal(fid, pid),
 * registered while mounted.
 */
export default function ImportSheetModal() {
  const [open, setOpen] = useState(false);
  const [scope, setScope] = useState({ fid: null, pid: null });
  const [heading, setHeading] = useState("Import test cases");
  const [subtitle, setSubtitle] = useState(null);
  const [fileName, setFileName] = useState("");
  const [status, setStatus] = useState(null); // { tone, text } | null
  const [progress, setProgress] = useState(false);
  const [uploadDisabled, setUploadDisabled] = useState(false);
  const [finished, setFinished] = useState(false); // upload hidden, Cancel reads "Close"
  const [summary, setSummary] = useState(null);
  const [review, setReview] = useState([]);
  const fileInput = useRef(null);
  const scopeRef = useRef(scope);
  scopeRef.current = scope;

  const resetResult = () => {
    setSummary(null);
    setStatus(null);
    setFinished(false);
    setProgress(false);
  };

  const openFor = useCallback((fid, pid) => {
    const f = fid || currentFeatureId() || null;
    const p = pid || currentProjectId() || null;
    if (!f || !p) {
      toast("Open a feature first", true);
      return;
    }
    setScope({ fid: f, pid: p });
    setFileName("");
    setHeading("Import test cases");
    setSubtitle({ prefix: "Updating: ", name: currentFeatureName() || "this feature" });
    if (fileInput.current) fileInput.current.value = "";
    resetResult();
    setUploadDisabled(false);
    setOpen(true);
  }, []);

  useEffect(() => {
    const hooks = {
      openImportSheetModal: (fid, pid) => openFor(fid, pid),
      importSheetForFeature: (fid, pid) => openFor(fid, pid),
    };
    Object.assign(window, hooks);
    return () => {
      for (const [k, fn] of Object.entries(hooks)) if (window[k] === fn) delete window[k];
    };
  }, [openFor]);

  const close = () => setOpen(false);

  const showSummary = (data, fid, iid) => {
    const items = data.items || [];
    setReview(initialReview(items));
    setHeading("Spreadsheet import finished");
    setFinished(true);
    if (!items.length) {
      setStatus(
        data.alreadyUploaded
          ? { tone: "ok", text: "✓ Already uploaded · no parsing was repeated" }
          : { tone: "muted", text: "No test rows recognized in this sheet." },
      );
      return;
    }
    setSubtitle({ prefix: "Imported into ", name: currentFeatureName() || "this feature" });
    setStatus(null);
    setSummary({ data, items, fid, iid });
    if (items.some((i) => i.action === "matched")) {
      loadFeatures();
      if (fid && currentFeatureId() === fid) setTimeout(() => openFeature(currentFeatureId()), 300);
    }
  };

  const upload = async () => {
    const file = fileInput.current?.files?.[0];
    if (!file) {
      toast("Pick a file first", true);
      return;
    }
    const fid = scopeRef.current.fid || currentFeatureId();
    const pid = scopeRef.current.pid || currentProjectId();
    if (!fid || !pid) {
      toast("No feature in scope", true);
      return;
    }
    setHeading("Import test cases");
    setStatus({ tone: "", text: ANALYZING });
    setSummary(null);
    setProgress(true);
    setUploadDisabled(true);
    const fd = new FormData();
    fd.append("file", file);
    let resp;
    try {
      const r = await fetch(`/api/projects/${pid}/features/${fid}/tests/import`, { method: "POST", body: fd });
      resp = await r.json();
      if (!r.ok) throw new Error(resp.detail || `${r.status}`);
      if (resp.alreadyUploaded) toast("Already uploaded · reusing saved import");
    } catch (e) {
      toast(e.message, true);
      setUploadDisabled(false);
      setProgress(false);
      setStatus({ tone: "err", text: e.message });
      return;
    }
    const iid = resp.feature_import_id;
    const start = Date.now();
    const poll = async () => {
      let s;
      try {
        s = await api(`/api/features/${fid}/tests/import/${iid}/status`);
      } catch {
        s = null;
      }
      if (!s) {
        setUploadDisabled(false);
        return;
      }
      const d = s.data || {};
      setStatus({ tone: "", text: d.details || d.status || ANALYZING });
      if (d.completed) {
        setProgress(false);
        showSummary(d.result_json || {}, fid, iid);
        setUploadDisabled(false);
        return;
      }
      if (Date.now() - start > IMPORT_POLL_LIMIT_MS) {
        setUploadDisabled(false);
        return;
      }
      setTimeout(poll, IMPORT_POLL_MS);
    };
    poll();
  };

  const onFileChange = (e) => {
    const f = e.target.files && e.target.files[0];
    setFileName(f ? f.name : "");
    resetResult();
  };

  const clearFile = () => {
    if (fileInput.current) fileInput.current.value = "";
    setFileName("");
    resetResult();
  };

  const downloadTemplate = (fmt) => {
    const fid = scopeRef.current.fid || currentFeatureId() || "_";
    window.location.href = `/api/features/${fid}/tests/import/template?format=${fmt}`;
  };

  const setRow = (idx, included) =>
    setReview((rv) => rv.map((r, i) => (i === idx ? { ...r, included: !!included } : r)));
  const setNote = (idx, note) => setReview((rv) => rv.map((r, i) => (i === idx ? { ...r, note } : r)));

  const saveReview = async () => {
    const fid = summary?.fid;
    const iid = summary?.iid;
    if (!fid || !iid) {
      toast("Nothing to save", true);
      return;
    }
    try {
      const r = await api(`/api/features/${fid}/tests/import/${iid}/review`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(reviewPayload(review)),
      });
      const d = r.data || {};
      toast(`Review saved · ${d.included || 0} included, ${d.excluded || 0} removed`);
      loadFeatures();
      if (fid && currentFeatureId() === fid) setTimeout(() => openFeature(currentFeatureId()), 300);
    } catch (e) {
      toast(e.message, true);
    }
  };

  return (
    <div
      className={open ? "modal sheet-modal show" : "modal sheet-modal"}
      id="imp-modal"
      onClick={(e) => {
        if (e.target === e.currentTarget) close();
      }}
    >
      <div className="box">
        <div className="editor-head">
          <div className="sheet-head-left">
            <div className="sheet-icon">XLS</div>
            <div className="sheet-title">
              <h2 id="imp-heading">{heading}</h2>
              <div className="muted" id="imp-subtitle">
                {subtitle ? (
                  <>
                    {subtitle.prefix}
                    <b>{subtitle.name}</b>
                  </>
                ) : (
                  "Upload a spreadsheet and link tests to this feature."
                )}
              </div>
            </div>
          </div>
          <button className="ghost sheet-close" id="imp-close" onClick={close}>
            Close
          </button>
        </div>
        <div className="sheet-body">
          <div className="muted" style={{ fontSize: "14px", maxWidth: "720px" }}>
            Upload a CSV or XLSX spreadsheet containing your test cases. WardenIQ will automatically extract and link
            them to this feature.
          </div>
          <div className="sheet-template-panel">
            <div>
              <b>Need a template?</b>
              <div className="muted">Download our system-shaped starter template to format your testcases.</div>
            </div>
            <div className="sheet-template-actions">
              <button className="ghost" id="imp-template-csv" type="button" onClick={() => downloadTemplate("csv")}>
                CSV Template
              </button>
              <button className="ghost" id="imp-template-xlsx" type="button" onClick={() => downloadTemplate("xlsx")}>
                XLSX Template
              </button>
            </div>
          </div>
          <div className="sheet-upload-panel">
            <div className="sheet-file-row">
              <input
                type="file"
                id="imp-file"
                ref={fileInput}
                accept=".csv,.xlsx,.xlsm,.tsv"
                onChange={onFileChange}
              />
              <button
                className="ghost sheet-file-btn"
                id="imp-file-pick"
                type="button"
                onClick={() => fileInput.current?.click()}
              >
                Choose file
              </button>
              <button className="ghost" id="imp-file-clear" type="button" onClick={clearFile}>
                Clear
              </button>
              <span className="sheet-selected" id="imp-selected">
                Selected: {fileName || "none"}
              </span>
            </div>
            <div className="muted" style={{ marginTop: "14px" }}>
              Imported test cases are saved as feature memory to be inherited by future versions.
            </div>
            <div className="sheet-progress" id="imp-progress" hidden={!progress}>
              <span></span>
            </div>
            <div id="imp-status" className="sheet-status">
              {status ? <span className={status.tone || undefined}>{status.text}</span> : null}
            </div>
          </div>
          <div id="imp-summary">
            {summary ? (
              <ImportSummary
                summary={summary}
                fileName={fileName}
                review={review}
                onSetRow={setRow}
                onSetNote={setNote}
                onSave={saveReview}
              />
            ) : null}
          </div>
        </div>
        <div className="sheet-footer">
          <button className="ghost" id="imp-cancel" type="button" onClick={close}>
            {finished ? "Close" : "Cancel"}
          </button>
          <button
            className="go sheet-primary"
            id="imp-upload"
            disabled={uploadDisabled}
            style={finished ? { display: "none" } : undefined}
            onClick={upload}
          >
            Upload and analyse
          </button>
        </div>
      </div>
    </div>
  );
}

function ImportSummary({ summary, fileName, review, onSetRow, onSetNote, onSave }) {
  const { data, items } = summary;
  return (
    <>
      <div
        className="sheet-chip-row"
        style={{ display: "flex", gap: "8px", flexWrap: "wrap", margin: "4px 0 18px" }}
      >
        <span className="pill">{fileName || "Uploaded sheet"}</span>
        <SheetPill tone="green">{data.alreadyUploaded ? "Already uploaded" : "First import for this feature"}</SheetPill>
      </div>
      <SheetKpis kpis={importKpis(items, data)} />
      <div className="sheet-meta-row">
        <b>Total rows: {items.length}</b>
        <span>Processed rows: {items.length}</span>
      </div>
      <div className="sheet-section-head">
        <div>
          <div className="typehdr">Review imported tests</div>
          <div className="muted">
            Include a row in this feature, or keep it in the project library for later. Then save.
          </div>
        </div>
        <button className="go" style={{ margin: "0" }} onClick={onSave}>
          Save review
        </button>
      </div>
      <div className="sheet-list" id="imp-review-list">
        {items.map((it, i) => (
          <ReviewCard
            key={i}
            item={it}
            decision={review[i] || { included: it.action === "matched", note: "" }}
            onSet={(included) => onSetRow(i, included)}
            onNote={(note) => onSetNote(i, note)}
          />
        ))}
      </div>
    </>
  );
}

const smallButton = { padding: "4px 10px", fontSize: "11px", margin: "0" };

function ReviewCard({ item: it, decision, onSet, onNote }) {
  const { included } = decision;
  const reason = breakdownReason(it.breakdown);
  return (
    <div className={`sheet-test-card ${included ? "included" : "pending"}`}>
      <div className="sheet-card-top">
        <div className="sheet-card-title">{it.title || "(no title)"}</div>
        <SheetPill tone={included ? "green" : "amber"}>{included ? "Included" : "Stored"}</SheetPill>
      </div>
      <div className="sheet-card-meta">
        <SheetPill>Source row {sourceRow(it)}</SheetPill>
        {it.category ? <SheetPill tone="blue">{it.category}</SheetPill> : null}
        {it.priority ? <SheetPill tone={priorityTone(it.priority)}>{it.priority}</SheetPill> : null}
        <SheetPill>{it.endpoint ? `${it.method || ""} ${it.endpoint}` : "No endpoint"}</SheetPill>
      </div>
      <SheetDetail steps={stepsText(it)} expected={it.expected_result} />
      {reason ? (
        <div className="sheet-reason">
          <b>Reason:</b> {reason}
        </div>
      ) : null}
      <div
        className="imp-review-controls"
        style={{ display: "flex", gap: "6px", alignItems: "center", marginTop: "10px", flexWrap: "wrap" }}
      >
        <button className={included ? "go" : "ghost"} style={smallButton} onClick={() => onSet(true)}>
          Include
        </button>
        <button className={included ? "ghost" : "go"} style={smallButton} onClick={() => onSet(false)}>
          Keep for later
        </button>
        <input
          type="text"
          placeholder="note (optional)"
          value={decision.note || ""}
          onChange={(e) => onNote(e.target.value)}
          style={{ flex: "1", minWidth: "140px", fontSize: "11.5px", padding: "4px 8px" }}
        />
      </div>
    </div>
  );
}
