import "../styles/usage.css";

/**
 * UsagePage
 *
 * UI structure only.
 * Existing API/data behavior remains handled by the usage controller.
 */
export default function UsagePage() {
  return (
    <section id="view-usage" className="view" hidden>
      <div className="usage-page">
        {/* =====================================================
            PAGE HEADER
        ====================================================== */}
        <div className="usage-header">
          <div>
            <span className="usage-eyebrow">AI OPERATIONS</span>

            <h1>LLM Usage &amp; Cost</h1>

            <p>
              Monitor token consumption and AI spend across WardenIQ.
            </p>
          </div>

          <button
            type="button"
            className="ghost usage-refresh"
            id="usage-refresh"
          >
            <svg
              viewBox="0 0 24 24"
              width="15"
              height="15"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M20 11a8 8 0 1 0-2.34 5.66" />
              <path d="M20 4v7h-7" />
            </svg>

            <span>Refresh</span>
          </button>
        </div>

        {/* =====================================================
            KPI CARDS
            Controller inserts cards here
        ====================================================== */}
        <div
          id="usage-totals"
          className="usage-stats"
        />

        {/* =====================================================
            COST INFORMATION
        ====================================================== */}
        <div className="usage-cost-info">
          <div className="usage-info-icon">
            <svg
              viewBox="0 0 24 24"
              width="15"
              height="15"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <circle cx="12" cy="12" r="9" />
              <path d="M12 11v5" />
              <path d="M12 8h.01" />
            </svg>
          </div>

          <div>
            <strong>How cost is calculated</strong>

            <span>
              Cost is calculated from input and output tokens using each
              model&apos;s configured pricing. Local Ollama models are free.
              Provider totals may vary slightly because of caching or batch
              discounts.
            </span>
          </div>
        </div>

        {/* =====================================================
            RECENT PROCESSES
        ====================================================== */}
        <section className="usage-panel usage-recent-panel">
          <div className="usage-panel-header">
            <div className="usage-panel-heading">
              <div className="usage-section-icon blue">
                <svg
                  viewBox="0 0 24 24"
                  width="17"
                  height="17"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.8"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <path d="M3 12h4l2-7 4 14 2-7h6" />
                </svg>
              </div>

              <div>
                <h2>Recent processes</h2>

                <p>
                  Review token usage and estimated cost for each AI operation.
                </p>
              </div>
            </div>

            <div className="usage-search-wrapper">
              <svg
                viewBox="0 0 24 24"
                width="15"
                height="15"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <circle cx="11" cy="11" r="7" />
                <path d="m20 20-4-4" />
              </svg>

              <input
                id="usage-recent-search"
                className="usage-search"
                placeholder="Search process, project or feature..."
              />
            </div>
          </div>

          <div className="usage-table-area">
            <div id="usage-recent" />
          </div>
        </section>

        {/* =====================================================
            MODEL / PROJECT BREAKDOWN
        ====================================================== */}
        <div className="usage-breakdown-grid">
          {/* BY MODEL */}
          <details
            className="usage-breakdown-card"
            open
          >
            <summary>
              <div className="usage-breakdown-heading">
                <div className="usage-section-icon violet">
                  <svg
                    viewBox="0 0 24 24"
                    width="17"
                    height="17"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.8"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  >
                    <rect
                      x="4"
                      y="4"
                      width="16"
                      height="16"
                      rx="3"
                    />
                    <path d="M8 9h8" />
                    <path d="M8 13h5" />
                  </svg>
                </div>

                <div>
                  <span className="usage-breakdown-title">
                    By model
                  </span>

                  <span className="usage-breakdown-subtitle">
                    Compare tokens and spend across AI models.
                  </span>
                </div>
              </div>

              <svg
                className="usage-chevron"
                viewBox="0 0 24 24"
                width="16"
                height="16"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="m6 9 6 6 6-6" />
              </svg>
            </summary>

            <div className="usage-breakdown-body">
              <div className="usage-filter">
                <label htmlFor="usage-model-filter">
                  Model
                </label>

                <select
                  id="usage-model-filter"
                  className="usage-select"
                  aria-label="Filter by model"
                >
                  <option value="">
                    All models
                  </option>
                </select>
              </div>

              <div
                id="usage-by-model"
                className="usage-breakdown-table"
              />
            </div>
          </details>

          {/* BY PROJECT */}
          <details
            className="usage-breakdown-card"
            open
          >
            <summary>
              <div className="usage-breakdown-heading">
                <div className="usage-section-icon emerald">
                  <svg
                    viewBox="0 0 24 24"
                    width="17"
                    height="17"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.8"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  >
                    <path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
                  </svg>
                </div>

                <div>
                  <span className="usage-breakdown-title">
                    By project
                  </span>

                  <span className="usage-breakdown-subtitle">
                    See which projects are driving AI usage.
                  </span>
                </div>
              </div>

              <svg
                className="usage-chevron"
                viewBox="0 0 24 24"
                width="16"
                height="16"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="m6 9 6 6 6-6" />
              </svg>
            </summary>

            <div className="usage-breakdown-body">
              <div className="usage-filter">
                <label htmlFor="usage-project-filter">
                  Project
                </label>

                <select
                  id="usage-project-filter"
                  className="usage-select"
                  aria-label="Filter by project"
                >
                  <option value="">
                    All projects
                  </option>
                </select>
              </div>

              <div
                id="usage-by-project"
                className="usage-breakdown-table"
              />
            </div>
          </details>
        </div>
      </div>
    </section>
  );
}