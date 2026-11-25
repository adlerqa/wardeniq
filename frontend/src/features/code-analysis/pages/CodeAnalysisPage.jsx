import GitRepoPicker from "../../mind-map/components/GitRepoPicker.jsx";
import { RepoRows } from "../../mind-map/components/MindmapControls.jsx";
import { AnalysisStatus, ImpactResults } from "../components/ImpactResults.jsx";
import useCodeAnalysis from "../hooks/useCodeAnalysis.js";
import "../styles/codeAnalysis.css";

/**
 * CodeAnalysisPage
 *
 * Change impact analysis: project / lookback / repo + branch selection,
 * the analysis run, the impacted cases and "create cycle from selection"
 * (useCodeAnalysis; was the code analysis half of
 * compat/runtime/controllers/08-code-analysis-and-cycles.js).
 */
export default function CodeAnalysisPage() {
  const ca = useCodeAnalysis();
  return (
    <section id="view-cycles" className="view" hidden>
      <div className="code-analysis-page">
        {/* =====================================================
            MAIN ANALYSIS CARD
        ====================================================== */}
        <section className="ca-main-card">
          {/* Header */}
          <div className="ca-header">
            <div className="ca-header-content">
              <h2>Change impact analysis</h2>

              <p>
                Review recent implementation changes, map them to affected test
                cases, and turn the result into a release regression cycle. Pick
                any of the project&apos;s repos below to include in the
                analysis.
              </p>
            </div>

            <button
              className="ghost ca-refresh-btn"
              id="cyc-refresh"
              type="button"
              title="Refresh"
              onClick={ca.refresh}
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
                aria-hidden="true"
              >
                <path d="M20 11a8 8 0 1 0-2.34 5.66" />
                <path d="M20 4v7h-7" />
              </svg>

              <span>Refresh</span>
            </button>
          </div>

          {/* =====================================================
              ANSWER EXPLAINER
          ====================================================== */}
          <div className="ca-answer">
            <svg
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
              <circle cx="12" cy="12" r="9" />
              <path d="M12 11v5" />
              <path d="M12 8h.01" />
            </svg>

            <span>
              Answers{" "}
              <b>“which test cases do recent commits touch?”</b>
              {" "}— a change-driven view. To see whether the codebase actually
              implements each case, use the{" "}
              <b>Implementation coverage map</b>.
            </span>
          </div>

          {/* =====================================================
              ANALYSIS CONTROLS
          ====================================================== */}
          <div className="ca-controls w-full">
            {/* Project */}
            <div className="ca-field ca-project">
              <label htmlFor="cyc-proj">Project</label>

              <div className="ca-select-wrapper">
                <select id="cyc-proj" value={ca.pid} onChange={(e) => ca.changeProject(e.target.value)}>
                  {ca.projects.map((p) => (
                    <option key={p.id} value={p.id}>
                      {`${p.name} — ${p.repo_count} repos · ${p.feature_count} features`}
                    </option>
                  ))}
                </select>

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
                  <path d="m6 9 6 6 6-6" />
                </svg>
              </div>
            </div>

            {/* Lookback */}
            <div className="ca-field ca-lookback">
              <label htmlFor="cyc-days">
                Lookback (days)
              </label>

              <input
                id="cyc-days"
                type="number"
                value={ca.days}
                onChange={(e) => ca.setDays(e.target.value)}
                min="1"
                max="180"
              />
            </div>

            {/* Analyze */}
            <button
              className="go ca-analyze-btn"
              id="cyc-analyze"
              type="button"
              disabled={ca.analyzeDisabled}
              title={ca.analyzeTitle}
              onClick={ca.analyze}
            >
              <svg
                viewBox="0 0 24 24"
                width="15"
                height="15"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.9"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <circle cx="11" cy="11" r="7" />
                <path d="m20 20-4-4" />
                <path d="M8 11h6" />
                <path d="M11 8v6" />
              </svg>

              <span>Analyze changes</span>
            </button>
          </div>

          {/* =====================================================
              REPOSITORIES
          ====================================================== */}
          <div className="ca-repositories">
            <div className="ca-repositories-heading">
              <div>
                <h3>Repos &amp; branches</h3>

                <p>
                  Uncheck any to exclude; set a branch per repo
                  (blank = its default). Infra repos start unchecked — tick
                  them to include.
                </p>
              </div>
            </div>

            <div
              id="cyc-repos"
              className="ca-repo-list"
            >
              <RepoRows repos={ca.repos} onChange={ca.updateRepo} cls="cyc-repo" />
            </div>

            <div className="ca-repo-footer">
              <button
                className="ghost ca-add-repo"
                id="cyc-add-git"
                type="button"
                onClick={ca.openPicker}
              >
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
                  <path d="M12 5v14" />
                  <path d="M5 12h14" />
                </svg>

                <span>Add a repo from GitHub</span>
              </button>

              <div
                id="cyc-status"
                className="ca-status"
              >
                <AnalysisStatus status={ca.status} />
              </div>
            </div>
          </div>
        </section>

        {/* =====================================================
            IMPACTED CASES
        ====================================================== */}
        <section className="ca-result-card">
          <div className="ca-result-header">
            <div className="ca-result-title">
              <div className="ca-section-icon violet">
                <svg
                  viewBox="0 0 24 24"
                  width="16"
                  height="16"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.8"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  aria-hidden="true"
                >
                  <path d="M4 4h6v6H4z" />
                  <path d="M14 4h6v6h-6z" />
                  <path d="M4 14h6v6H4z" />
                  <path d="M14 14h6v6h-6z" />
                </svg>
              </div>

              <div>
                <h2>Impacted test cases</h2>

                <p>
                  Test cases mapped to implementation changes found during the
                  selected lookback period.
                </p>
              </div>
            </div>
          </div>

          <div
            id="cyc-impacted"
            className="ca-impacted-content"
          >
            <ImpactResults ca={ca} />
          </div>
        </section>

        {/* =====================================================
            CREATE TEST CYCLE
        ====================================================== */}
        <section
          className="ca-cycle-card"
          id="cyc-create"
          style={{ display: ca.impacted && ca.impacted.list.length ? "" : "none" }}
        >
          <div className="ca-cycle-header">
            <div className="ca-section-icon emerald">
              <svg
                viewBox="0 0 24 24"
                width="16"
                height="16"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <path d="M8 6h13" />
                <path d="M8 12h13" />
                <path d="M8 18h13" />
                <path d="m3 6 1 1 2-2" />
                <path d="m3 12 1 1 2-2" />
                <path d="m3 18 1 1 2-2" />
              </svg>
            </div>

            <div>
              <h2>Create a test cycle</h2>

              <p>
                Pick the impacted cases you want to retest, name the cycle, and
                save it for execution.
              </p>
            </div>
          </div>

          <div className="ca-cycle-form">
            <div className="ca-field">
              <label htmlFor="cyc-name">
                Cycle name
              </label>

              <input
                id="cyc-name"
                placeholder="For example: Sprint 12 regression"
                value={ca.name}
                onChange={(e) => ca.setName(e.target.value)}
              />
            </div>

            <button
              className="go ca-create-btn"
              id="cyc-make"
              type="button"
              disabled={ca.shownOnce && ca.selected.size === 0}
              onClick={ca.createCycle}
            >
              {ca.shownOnce ? (
                ca.selected.size > 0 ? (
                  `Create cycle (${ca.selected.size})`
                ) : (
                  "Create cycle"
                )
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
                    <path d="M12 5v14" />
                    <path d="M5 12h14" />
                  </svg>

                  <span>Create cycle</span>
                </>
              )}
            </button>
          </div>
        </section>
      </div>
      {ca.picker ? <GitRepoPicker repos={ca.picker.repos} onCancel={ca.closePicker} onAdd={ca.addPicked} /> : null}
    </section>
  );
}