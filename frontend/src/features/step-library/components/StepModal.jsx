import { createPortal } from "react-dom";

import "../styles/step-modal.css";

/**
 * Create / edit step dialog for the Step Library (was wired by the compat
 * 07-library-and-crud.js). `modal` holds the fields; the parent saves.
 *
 * Rendered into document.body: the screen's .view container is animated
 * (transform), which would otherwise make it the containing block of this
 * position:fixed overlay and pin the dialog to the page instead of the window.
 */
export default function StepModal({ modal, setField, onClose, onSave }) {
  return createPortal(
    <div
      className={`modal step-modal-overlay${modal.open ? " show" : ""}`}
      role="dialog"
      aria-modal="true"
      aria-labelledby="step-modal-heading"
    >
      <div className="step-modal-dialog">
        {/* Header */}
        <div className="step-modal-header">
          <div>
            <span className="step-modal-eyebrow">
              STEP LIBRARY
            </span>

            <h2 id="step-modal-heading">
              {modal.heading}
            </h2>

            <p>
              Create a reusable step for your test cases.
            </p>
          </div>

          <button
            type="button"
            onClick={onClose}
            className="step-modal-close"
            title="Close"
            aria-label="Close modal"
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

        {/* Form */}
        <div className="step-modal-body">
          {/* Step type */}
          <div className="step-modal-field">
            <div className="step-modal-label-row">
              <label htmlFor="step-modal-prefix">
                Step type
              </label>

              <span>Optional prefix</span>
            </div>

            <div className="step-modal-select-wrap">
              <select
                id="step-modal-prefix"
                value={modal.prefix}
                onChange={(e) => setField("prefix", e.target.value)}
              >
                <option value="Given">Given</option>
                <option value="When">When</option>
                <option value="Then">Then</option>
                <option value="And">And</option>
                <option value="But">But</option>
                <option value="">
                  None / Custom
                </option>
              </select>

              <svg
                className="step-modal-select-icon"
                viewBox="0 0 24 24"
                width="15"
                height="15"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <path d="m6 9 6 6 6-6" />
              </svg>
            </div>
          </div>

          {/* Action */}
          <div className="step-modal-field">
            <div className="step-modal-label-row">
              <label htmlFor="step-modal-action">
                Action / Description
              </label>

              <span>Required</span>
            </div>

            <textarea
              id="step-modal-action"
              placeholder="e.g. user is on the login page"
              required
              value={modal.action}
              onChange={(e) => setField("action", e.target.value)}
            />
          </div>

          {/* Expected result */}
          <div className="step-modal-field">
            <div className="step-modal-label-row">
              <label htmlFor="step-modal-expected">
                Expected result
              </label>

              <span>Optional</span>
            </div>

            <textarea
              id="step-modal-expected"
              placeholder="e.g. login form is displayed"
              value={modal.expected}
              onChange={(e) => setField("expected", e.target.value)}
            />
          </div>

          {/* Warning */}
          {modal.warn && <div className="step-modal-warning">{modal.warn}</div>}
        </div>

        {/* Footer */}
        <div className="step-modal-footer">
          <button
            type="button"
            className="step-modal-cancel"
            onClick={onClose}
          >
            Cancel
          </button>

          <button
            type="button"
            className="step-modal-save"
            disabled={modal.saving}
            onClick={onSave}
          >
            {modal.saving ? (
              "Saving…"
            ) : (
              <>
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
              <path d="m5 12 4 4L19 6" />
            </svg>

            <span>Save step</span>
              </>
            )}
          </button>
        </div>
      </div>
    </div>
    ,
    document.body,
  );
}