import { useEffect, useRef } from "react";

import { projectOptionLabel } from "../../projects/lib/projects.js";
import { FOCUS_LABELS, FOCUS_TYPES, focusTotal } from "../lib/features.js";

/** One test-type slider; a drag ends on the native change event (as before), or on blur. */
function FocusRow({ t, cf }) {
  const ref = useRef(null);
  const cfRef = useRef(cf);
  cfRef.current = cf;
  useEffect(() => {
    const el = ref.current;
    const end = () => cfRef.current.focusEnd();
    el.addEventListener("change", end);
    return () => el.removeEventListener("change", end);
  }, []);
  const v = cf.focus[t];
  return (
    <div className="focus-row">
      <span>{FOCUS_LABELS[t]}</span>
      <input
        ref={ref}
        className="focus-range"
        type="range"
        min="0"
        max="100"
        id={`foc-${t}`}
        value={v}
        style={{ "--fill": `${v}%` }}
        onPointerDown={() => cf.focusStart(t)}
        onFocus={() => cf.focusFocus(t)}
        onBlur={cf.focusEnd}
        onChange={(e) => cf.focusInput(t, e.target.value)}
      />
      <b className="focus-value" id={`foc-${t}-v`}>{`${v}%`}</b>
    </div>
  );
}

function CreateStatus({ status }) {
  if (!status) return null;
  switch (status.kind) {
    case "err":
      return <span className="err">{status.text}</span>;
    case "muted":
      return <span className="muted">{status.text}</span>;
    case "accepted":
      return (
        <>
          <span className="ok">{`✓ ${status.docs} document(s) accepted · ${status.chunks} chunk(s) prepared.`}</span>
          {" Live progress below."}
        </>
      );
    case "running":
      return (
        <>
          <span className="muted">{status.stage}</span>
          {` — ${status.line}`}
        </>
      );
    case "failed":
      return <span className="err">{`✕ Generation failed: ${status.text}`}</span>;
    case "startFailed":
      return <span className="err">{`✕ Couldn't start generation: ${status.text}`}</span>;
    default:
      return (
        <>
          <span className="ok">✓ Done</span>
          {` — ${status.line}`}
          {status.filterLine ? (
            <>
              <br />
              <span className="muted">{status.filterLine}</span>
            </>
          ) : null}
          {status.warnings.length ? (
            <>
              <br />
              <span className="warn">{status.warnings.join("; ")}</span>
            </>
          ) : null}
          {status.errors.length ? (
            <>
              <br />
              <span className="err">{status.errors.join("; ")}</span>
            </>
          ) : null}
        </>
      );
  }
}

/** The job log under Generate; it follows the newest line. */
function JobLog({ log }) {
  const ref = useRef(null);
  useEffect(() => {
    if (ref.current) ref.current.scrollTop = ref.current.scrollHeight;
  }, [log]);
  return (
    <div className="job-log" id="f-log" ref={ref} style={{ display: log ? "block" : "none" }}>
      {log ? log.join("\n") : ""}
    </div>
  );
}

/** The "New feature" page (useFeatureCreate). */
export default function FeatureCreatePanel({ fs, cf }) {
  return (
    <div id="feature-create-page" className="stage-page create-feature-form" hidden={fs.page !== "create"}>
      <div className="stage-header">
        <button className="ghost" id="feature-create-back" onClick={cf.back}>
          All features
        </button>
      </div>
      <div className="card">
        <h2>New feature</h2>
        <div className="sub">Upload requirement, design, API, or architecture docs and/or paste text. All sources are embedded for RAG; the pipeline generates business, end-to-end, API, UI-validation, and edge/reliability coverage.</div>
        <select id="f-project" hidden value={fs.projects.cur} onChange={() => {}}>
          {fs.projects.list.map((p) => (
            <option key={p.id} value={p.id}>
              {projectOptionLabel(p)}
            </option>
          ))}
        </select>
        <div className="feature-create-fields">
          <div>
            <label>Feature name</label>
            <input id="f-name" ref={cf.nameRef} placeholder="e.g: Login" value={cf.name} onChange={(e) => cf.setName(e.target.value)} />
          </div>
          <div>
            <label>Ticket key (optional)</label>
            <select id="f-key" value={cf.ticketKey} onChange={(e) => cf.setTicketKey(e.target.value)}>
              <option value="">{cf.ticket.none}</option>
              {cf.ticket.options.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label>PR match tag (optional)</label>
            <input id="f-match-key" placeholder="e.g. HOLDS" value={cf.matchKey} onChange={(e) => cf.setMatchKey(e.target.value)} />
          </div>
        </div>
        <div className="feature-create-jira-status" id="f-key-status">
          {cf.ticket.status.err ? <span className="err">{cf.ticket.status.text}</span> : cf.ticket.status.text}
        </div>
        <label>
          Upload documents
          <span className="muted" style={{ fontWeight: "400" }}>(PRD, HLD, LLD, architecture — PDF, DOCX, MD, TXT · you can select several)</span>
        </label>
        <input type="file" id="f-file" ref={cf.fileRef} accept=".pdf,.docx,.md,.txt,.markdown" multiple onChange={cf.pickFiles} />
        <div className="muted" id="f-filelist" style={{ fontSize: "11px" }}>
          {cf.files.length ? (
            <>
              <div>{`${cf.files.length} file(s):`}</div>
              {cf.files.map((f, i) => (
                <div key={i} className="f-file-row">
                  <span className="f-file-name">{f.name}</span>
                  <button
                    className="iconbtn"
                    type="button"
                    title={`Remove ${f.name}`}
                    aria-label={`Remove ${f.name}`}
                    onClick={() => cf.removeFile(i)}
                  >
                    ×
                  </button>
                </div>
              ))}
            </>
          ) : null}
        </div>
        <div className="muted" style={{ fontSize: "11px", marginTop: "4px" }}>Links inside PDFs (and their sub-links) are fetched automatically — public web only.</div>
        <label>
          Or paste requirement text
          <span className="muted" style={{ fontWeight: "400" }}>(optional)</span>
        </label>
        <textarea
          id="f-text"
          placeholder="Paste requirements, acceptance criteria, or extra context here…"
          value={cf.text}
          onChange={(e) => cf.changeText(e.target.value)}
        ></textarea>
        <label style={{ marginTop: "14px" }}>
          Confluence page link
          <span className="muted" style={{ fontWeight: "400" }}>(optional · one URL per line · uses your Jira/Atlassian token; child pages included)</span>
        </label>
        <textarea id="f-confluence" rows="2" value={cf.confluence} onChange={(e) => cf.setConfluence(e.target.value)} placeholder={`https://your-org.atlassian.net/wiki/spaces/…/pages/123456/…
https://your-org.atlassian.net/wiki/spaces/…/pages/789012/…`}></textarea>
        <label style={{ marginTop: "10px" }}>
          Figma design link
          <span className="muted" style={{ fontWeight: "400" }}>(optional · one URL per line · needs a Figma token in Configuration)</span>
        </label>
        <textarea id="f-figma" rows="2" value={cf.figma} onChange={(e) => cf.setFigma(e.target.value)} placeholder={`https://www.figma.com/file/<key>/…
https://www.figma.com/design/<key>/…`}></textarea>
        <label style={{ marginTop: "14px" }}>
          Import test sheet
          <span className="muted" style={{ fontWeight: "400" }}>(optional · CSV / XLSX)</span>
        </label>
        <input type="file" id="f-sheet" ref={cf.sheetRef} accept=".csv,.xlsx,.xlsm,.tsv" />
        <div className="muted" style={{ fontSize: "11px", marginTop: "4px" }}>
          Already keep test cases in a spreadsheet? Attach it — wardenIQ scores every row against this feature, promotes matches into the generated suite, and keeps the rest in your project library for other features to reuse.
          <a href="#" id="f-sheet-template" onClick={cf.sheetTemplate}>
            Download template
          </a>
        </div>
        <label style={{ marginTop: "10px" }}>
          Test type mix
          <span className="muted" style={{ fontWeight: "400" }}>— how much emphasis each category gets (not a fixed count)</span>
        </label>
        <div id="focus-ctrl" className="focus-panel">
          {FOCUS_TYPES.map((t) => (
            <FocusRow key={t} t={t} cf={cf} />
          ))}
          <div className="focus-total">
            <span>Changing one category adjusts the largest other category first.</span>
            <span>
              Total
              <b id="foc-total">{`${focusTotal(cf.focus)}%`}</b>
            </span>
          </div>
        </div>
        <div className="muted" id="f-cost-estimate" style={{ fontSize: "11px", marginTop: "10px" }}>
          {cf.estimate.cost}
          {cf.estimate.warning ? (
            <div style={{ color: "var(--amber)", marginTop: "6px" }}>{`⚠ ${cf.estimate.warning}`}</div>
          ) : null}
        </div>
        <button
          className="go"
          id="f-go"
          style={{ marginTop: "12px" }}
          disabled={cf.busy}
          aria-busy={cf.busy ? "true" : undefined}
          onClick={cf.generate}
        >
          Generate test cases
        </button>
        <div className="feature-create-live">
          <div className="muted" id="f-status">
            <CreateStatus status={cf.status} />
          </div>
          <JobLog log={cf.log} />
        </div>
      </div>
    </div>
  );
}
