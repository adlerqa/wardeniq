import "./modal css/step-modal.css";

/** Shared step-modal overlay. */
export default function StepModal() {
  return (
    <div
      className="modal step-modal-overlay"
      id="step-modal"
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
              Create Step
            </h2>

            <p>
              Create a reusable step for your test cases.
            </p>
          </div>

          <button
            id="step-modal-close"
            type="button"
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
              <select id="step-modal-prefix" aria-label="Filter by Prefix">
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
            />
          </div>

          {/* Warning */}
          <div
            id="step-modal-warn"
            className="step-modal-warning"
            style={{ display: "none" }}
          />
        </div>

        {/* Footer */}
        <div className="step-modal-footer">
          <button
            id="step-modal-cancel"
            type="button"
            className="step-modal-cancel"
          >
            Cancel
          </button>

          <button
            id="step-modal-save"
            type="button"
            className="step-modal-save"
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
              <path d="m5 12 4 4L19 6" />
            </svg>

            <span>Save step</span>
          </button>
        </div>
      </div>
    </div>
  );
}