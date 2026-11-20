import { METRICS, clampPercent, projectsLabel, typeRows } from "../lib/dashboard.js";
import { METRIC_ICONS } from "./icons.jsx";

function Heading() {
  return (
    <div className="dashboard-heading">
      <div>
        <h1>Overview</h1>
        <p>Monitor projects, test coverage and engineering activity.</p>
      </div>
    </div>
  );
}

function EmptyState({ text }) {
  return (
    <div className="dashboard-empty">
      <div className="dashboard-empty-icon">
        <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
          <path d="M4 19V9" />
          <path d="M10 19V5" />
          <path d="M16 19v-7" />
          <path d="M22 19H2" />
        </svg>
      </div>
      <span>{text}</span>
    </div>
  );
}

function CoverageRow({ label, description, value, className }) {
  const pct = clampPercent(value);
  return (
    <div className="dashboard-coverage-item">
      <div className="dashboard-coverage-copy">
        <div>
          <div className="dashboard-coverage-label">{label}</div>
          <div className="dashboard-coverage-description">{description}</div>
        </div>
        <div className="dashboard-coverage-value">{pct}%</div>
      </div>
      <div
        className="dashboard-progress"
        role="progressbar"
        aria-valuemin="0"
        aria-valuemax="100"
        aria-valuenow={pct}
        aria-label={label}
      >
        {/* Width is the live percentage, so it stays an inline style. */}
        <div className={`dashboard-progress-fill ${className}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

function MiniCoverage({ value, className }) {
  const pct = clampPercent(value);
  return (
    <div className="dashboard-table-coverage">
      <span>{pct}%</span>
      <div className="dashboard-mini-track">
        <div className={`dashboard-mini-fill ${className}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

/** Loaded dashboard: KPI tiles, coverage, test cases by type and the project roll-up. */
export function DashboardOverview({ data }) {
  const c = data.counts || {};
  const g = data.coverage || {};
  const projects = data.projects || [];
  const types = typeRows(data.by_type);
  return (
    <div className="dashboard-page">
      <Heading />

      <div className="dashboard-metrics">
        {METRICS.map(([key, label, tone]) => (
          <div key={key} className={`dashboard-metric dashboard-metric-${tone}`}>
            <div className="dashboard-metric-header">
              <span className="dashboard-metric-label">{label}</span>
              <div className="dashboard-metric-icon">{METRIC_ICONS[key]}</div>
            </div>
            <div className="dashboard-metric-value">{c[key] ?? 0}</div>
            <div className="dashboard-metric-caption">Across workspace</div>
          </div>
        ))}
      </div>

      <div className="dashboard-analytics-grid">
        <section className="dashboard-panel">
          <div className="dashboard-panel-heading">
            <div>
              <h2>Coverage</h2>
              <p>How effectively your test cases are exercised by code and automation.</p>
            </div>
          </div>
          <div className="dashboard-coverage-list">
            <CoverageRow
              label="Code coverage"
              description="Test cases exercised by mapped pull requests"
              value={g.code_pct}
              className="code"
            />
            <CoverageRow
              label="Automation coverage"
              description="Test cases backed by developer-written automated tests"
              value={g.automation_pct}
              className="automation"
            />
          </div>
          <div className="dashboard-coverage-summary">
            <div className="dashboard-summary-item">
              <span className="dashboard-summary-dot covered" />
              <span>
                <strong>{g.covered_cases ?? 0}</strong> covered
              </span>
            </div>
            <div className="dashboard-summary-divider" />
            <div className="dashboard-summary-item">
              <span className="dashboard-summary-dot automated" />
              <span>
                <strong>{g.automated_cases ?? 0}</strong> automated
              </span>
            </div>
            <div className="dashboard-summary-divider" />
            <div className="dashboard-summary-item muted">{c.test_cases ?? 0} total cases</div>
          </div>
        </section>

        <section className="dashboard-panel">
          <div className="dashboard-panel-heading">
            <div>
              <h2>Test cases by type</h2>
              <p>Distribution of your current test case library.</p>
            </div>
            <span className="dashboard-total">{c.test_cases ?? 0} total</span>
          </div>
          {types.length ? (
            <div className="dashboard-type-list">
              {types.map((t) => (
                <div key={t.type} className="dashboard-type-row">
                  <div className="dashboard-type-name">{t.type}</div>
                  <div className="dashboard-type-track">
                    <div className="dashboard-type-fill" style={{ width: `${t.width}%`, background: t.color }} />
                  </div>
                  <div className="dashboard-type-count">{t.value}</div>
                </div>
              ))}
            </div>
          ) : (
            <EmptyState text="No test case data yet" />
          )}
        </section>
      </div>

      <section className="dashboard-panel dashboard-projects">
        <div className="dashboard-panel-heading">
          <div>
            <h2>Projects</h2>
            <p>Coverage and repository activity across your projects.</p>
          </div>
          <span className="dashboard-total">{projectsLabel(c.projects)}</span>
        </div>
        {projects.length ? (
          <div className="dashboard-table-wrap">
            <table className="dashboard-table">
              <thead>
                <tr>
                  <th>Project</th>
                  <th>Features</th>
                  <th>Test cases</th>
                  <th>Code coverage</th>
                  <th>Automation</th>
                  <th>Repos</th>
                  <th>PRs</th>
                </tr>
              </thead>
              <tbody>
                {projects.map((p, i) => (
                  <tr key={p.id || i}>
                    <td>
                      <div className="dashboard-project-name">
                        <span className="dashboard-project-mark" /> {p.name}
                      </div>
                    </td>
                    <td>{p.features ?? 0}</td>
                    <td>{p.test_cases ?? 0}</td>
                    <td>
                      <MiniCoverage value={p.code_pct} className="code" />
                    </td>
                    <td>
                      <MiniCoverage value={p.automation_pct} className="automation" />
                    </td>
                    <td>{p.repos ?? 0}</td>
                    <td>{p.prs ?? 0}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState text="Create your first project to see project metrics" />
        )}
      </section>
    </div>
  );
}

/** Shown when the dashboard request fails. */
export function DashboardError({ message, onRetry }) {
  return (
    <div className="dashboard-page">
      <Heading />
      <div className="dashboard-error">
        <div className="dashboard-error-icon">
          <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="9" />
            <path d="M12 8v5" />
            <path d="M12 17h.01" />
          </svg>
        </div>
        <div className="dashboard-error-copy">
          <strong>Could not load dashboard</strong>
          <span>{message}</span>
        </div>
        <button type="button" className="ghost dashboard-retry" onClick={onRetry}>
          Retry
        </button>
      </div>
    </div>
  );
}
