import { useEffect, useRef, useState } from "react";

import { api } from "../../../lib/api.js";
import { toast } from "../../../lib/compatBridge.js";
import { splitLinks } from "../../../features/features/lib/features.js";
import "./modal css/validator-modal.css";

const callWindow = (name, ...args) => (typeof window[name] === "function" ? window[name](...args) : undefined);

function VmMsg({ msg }) {
  if (!msg) return null;
  if (msg.kind === "err") return <span className="err">{msg.text}</span>;
  if (msg.kind === "ok") return <span className="ok">{msg.text}</span>;
  return msg.text;
}

/**
 * "Upload new version" dialog for the open feature (was the #vmodal handlers
 * in 07-library-and-crud.js). Registered while mounted:
 * window.openNewVersionModal(featureId, label).
 */
export default function ValidatorModal() {
  const [show, setShow] = useState(false);
  const [label, setLabel] = useState("");
  const [text, setText] = useState("");
  const [confluence, setConfluence] = useState("");
  const [figma, setFigma] = useState("");
  const [replace, setReplace] = useState(false);
  const [msg, setMsg] = useState(null);
  const [busy, setBusy] = useState(false);
  const fileRef = useRef(null);
  const fidRef = useRef(null);
  const timer = useRef(null);
  useEffect(() => () => clearTimeout(timer.current), []);

  useEffect(() => {
    const open = (featureId, featureLabel) => {
      fidRef.current = featureId;
      setLabel(featureLabel || "");
      if (fileRef.current) fileRef.current.value = "";
      setText("");
      setConfluence("");
      setFigma("");
      setReplace(false);
      setMsg(null);
      setShow(true);
    };
    window.openNewVersionModal = open;
    return () => {
      if (window.openNewVersionModal === open) delete window.openNewVersionModal;
    };
  }, []);

  const handleClose = () => setShow(false);

  const create = async () => {
    const vConfl = splitLinks(confluence);
    const vFigma = splitLinks(figma);
    const files = [...(fileRef.current ? fileRef.current.files : [])];
    if (!files.length && !text.trim() && !vConfl.length && !vFigma.length) {
      setMsg({ kind: "err", text: "Upload a doc, paste text, or add a Confluence/Figma link." });
      return;
    }
    setBusy(true);
    setMsg({ kind: "text", text: "uploading + diffing against previous version…" });
    const fd = new FormData();
    for (const f of files) fd.append("files", f);
    fd.append("text", text);
    fd.append("replace", replace ? "true" : "false");
    vConfl.forEach((u) => fd.append("confluence_url", u));
    vFigma.forEach((u) => fd.append("figma_url", u));
    try {
      const r = await api(`/api/features/${fidRef.current}/versions`, { method: "POST", body: fd });
      const d = r.diff || {};
      setMsg({
        kind: "ok",
        text: `v${r.version} created — ${d.kept || 0} kept${d.retired && d.retired.length ? `, ${d.retired.length} retired` : ""}. Generating new cases…`,
      });
      toast(`Version ${r.version} created`);
      timer.current = setTimeout(() => {
        setShow(false);
        Promise.resolve(callWindow("openFeature", r.feature_id)).then(() => callWindow("watchFeatureGen", r.job_id, r.feature_id));
        callWindow("loadFeatures");
      }, 1200);
    } catch (e) {
      setMsg({ kind: "err", text: e.message });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      className={`modal validator-modal-overlay${show ? " show" : ""}`}
      id="vmodal"
      role="dialog"
      aria-modal="true"
      aria-labelledby="validator-modal-title"
    >
      <div className="validator-modal-dialog">
        {/* =====================================================
            HEADER
        ====================================================== */}
        <div className="validator-modal-header">
          <div className="validator-modal-heading">
            <div className="validator-modal-icon">
              <svg
                viewBox="0 0 24 24"
                width="18"
                height="18"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <path d="M12 3v12" />
                <path d="m7 10 5 5 5-5" />
                <path d="M5 21h14" />
              </svg>
            </div>

            <div>
              <span className="validator-modal-eyebrow">
                REQUIREMENT VERSION
              </span>

              <h2 id="validator-modal-title">
                Upload new version
              </h2>

              <div
                className="validator-modal-feature"
                id="vm-feat"
              >
                {label}
              </div>
            </div>
          </div>

          <button
            type="button"
            className="validator-modal-close"
            onClick={handleClose}
            aria-label="Close upload new version dialog"
            title="Close"
          >
            <svg
              viewBox="0 0 24 24"
              width="17"
              height="17"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <path d="M18 6 6 18" />
              <path d="m6 6 12 12" />
            </svg>
          </button>
        </div>

        {/* =====================================================
            BODY
        ====================================================== */}
        <div className="validator-modal-body">
          {/* DOCUMENTS */}
          <section className="validator-form-section">
            <div className="validator-section-heading">
              <div>
                <h3>Updated documents</h3>
                <p>
                  Upload one or more files containing the latest requirement
                  changes.
                </p>
              </div>

              <span className="validator-section-badge">
                Multiple files
              </span>
            </div>

            <div className="validator-field">
              <label htmlFor="vm-file">
                Modified documents
              </label>

              <input
                ref={fileRef}
                type="file"
                id="vm-file"
                multiple
                accept=".pdf,.docx,.md,.txt,.markdown"
                className="validator-file-input"
              />

              <div className="validator-field-hint">
                <svg
                  viewBox="0 0 24 24"
                  width="14"
                  height="14"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.8"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  aria-hidden="true"
                >
                  <circle cx="12" cy="12" r="9" />
                  <path d="M12 11v5" />
                  <path d="M12 8h.01" />
                </svg>

                <span>
                  Links inside PDFs and their sub-links are fetched
                  automatically when publicly accessible.
                </span>
              </div>
            </div>
          </section>

          {/* REQUIREMENT TEXT */}
          <section className="validator-form-section">
            <div className="validator-section-heading compact">
              <div>
                <h3>Requirement text</h3>
                <p>
                  Optionally paste updated requirements directly.
                </p>
              </div>

              <span className="validator-optional">
                Optional
              </span>
            </div>

            <div className="validator-field">
              <textarea
                id="vm-text"
                value={text}
                onChange={(e) => setText(e.target.value)}
                placeholder="Paste the updated requirement text here..."
              />
            </div>
          </section>

          {/* EXTERNAL SOURCES */}
          <section className="validator-form-section">
            <div className="validator-section-heading">
              <div>
                <h3>External sources</h3>
                <p>
                  Add supporting requirement or design links.
                </p>
              </div>

              <span className="validator-optional">
                Optional
              </span>
            </div>

            <div className="validator-source-grid">
              {/* Confluence */}
              <div className="validator-field">
                <label htmlFor="vm-confluence">
                  <span className="validator-label-icon confluence">
                    <svg
                      viewBox="0 0 24 24"
                      width="14"
                      height="14"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="1.8"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      aria-hidden="true"
                    >
                      <path d="M8 4h8l4 4v12H4V4z" />
                      <path d="M16 4v5h5" />
                    </svg>
                  </span>

                  Confluence pages
                </label>

                <textarea
                  id="vm-confluence"
                  value={confluence}
                  onChange={(e) => setConfluence(e.target.value)}
                  rows="2"
                  placeholder="https://your-org.atlassian.net/wiki/..."
                />

                <span className="validator-input-note">
                  One link per line · child pages included
                </span>
              </div>

              {/* Figma */}
              <div className="validator-field">
                <label htmlFor="vm-figma">
                  <span className="validator-label-icon figma">
                    <svg
                      viewBox="0 0 24 24"
                      width="14"
                      height="14"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="1.8"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      aria-hidden="true"
                    >
                      <circle cx="8" cy="6" r="3" />
                      <circle cx="16" cy="6" r="3" />
                      <circle cx="8" cy="12" r="3" />
                      <circle cx="16" cy="12" r="3" />
                      <circle cx="8" cy="18" r="3" />
                    </svg>
                  </span>

                  Figma designs
                </label>

                <textarea
                  id="vm-figma"
                  value={figma}
                  onChange={(e) => setFigma(e.target.value)}
                  rows="2"
                  placeholder="https://www.figma.com/file/<key>/..."
                />

                <span className="validator-input-note">
                  One link per line · requires Figma token
                </span>
              </div>
            </div>
          </section>

          {/* VERSION MODE */}
          <section className="validator-version-mode">
            <label
              htmlFor="vm-replace"
              className="validator-version-option"
            >
              <input
                type="checkbox"
                id="vm-replace"
                checked={replace}
                onChange={(e) => setReplace(e.target.checked)}
              />

              <span className="validator-checkbox-ui">
                <svg
                  viewBox="0 0 24 24"
                  width="13"
                  height="13"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2.4"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  aria-hidden="true"
                >
                  <path d="m5 12 4 4L19 6" />
                </svg>
              </span>

              <span className="validator-version-copy">
                <strong>
                  Replace current version
                </strong>

                <span>
                  Regenerate the current version instead of creating a new
                  version.
                </span>
              </span>
            </label>

            <div className="validator-version-help">
              <div>
                <span className="validator-version-dot new" />

                <p>
                  <strong>New version</strong>{" "}
                  keeps valid cases, retires obsolete cases and adds new ones
                  while preserving history.
                </p>
              </div>

              <div>
                <span className="validator-version-dot replace" />

                <p>
                  <strong>Replace</strong>{" "}
                  regenerates the current version from scratch.
                </p>
              </div>
            </div>
          </section>

          {/* EXISTING STATUS / ERROR TARGET */}
          <div
            id="vm-msg"
            className="validator-modal-message"
          >
            <VmMsg msg={msg} />
          </div>
        </div>

        {/* =====================================================
            FOOTER
        ====================================================== */}
        <div className="validator-modal-footer">
          <button
            className="ghost validator-cancel-btn"
            id="vm-cancel"
            type="button"
            onClick={handleClose}
          >
            Cancel
          </button>

          <button
            className="go validator-create-btn"
            id="vm-go"
            type="button"
            disabled={busy}
            onClick={create}
          >
            <svg
              viewBox="0 0 24 24"
              width="15"
              height="15"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <path d="M12 3v12" />
              <path d="m7 10 5 5 5-5" />
              <path d="M5 21h14" />
            </svg>

            <span>Create version</span>
          </button>
        </div>
      </div>
    </div>
  );
}