// ---- dashboard ----

function clampPercent(value) {
  const number = Number(value) || 0;
  return Math.max(0, Math.min(100, number));
}

function dashboardMetric(label, value, icon, tone = "cyan") {
  return `
    <div class="dashboard-metric dashboard-metric-${tone}">

      <div class="dashboard-metric-header">

        <span class="dashboard-metric-label">
          ${esc(label)}
        </span>

        <div class="dashboard-metric-icon">
          ${icon}
        </div>

      </div>

      <div class="dashboard-metric-value">
        ${value ?? 0}
      </div>

      <div class="dashboard-metric-caption">
        Across workspace
      </div>

    </div>
  `;
}

function dashboardCoverageRow({ label, description, value, className }) {
  const pct = clampPercent(value);

  return `
    <div class="dashboard-coverage-item">
      <div class="dashboard-coverage-copy">
        <div>
          <div class="dashboard-coverage-label">
            ${esc(label)}
          </div>

          <div class="dashboard-coverage-description">
            ${esc(description)}
          </div>
        </div>

        <div class="dashboard-coverage-value">
          ${pct}%
        </div>
      </div>

      <div
        class="dashboard-progress"
        role="progressbar"
        aria-valuemin="0"
        aria-valuemax="100"
        aria-valuenow="${pct}"
        aria-label="${esc(label)}"
      >
        <div
          class="dashboard-progress-fill ${className}"
          style="width:${pct}%"
        ></div>
      </div>
    </div>
  `;
}

function dashboardEmptyState(text) {
  return `
    <div class="dashboard-empty">
      <div class="dashboard-empty-icon">
        <svg
          viewBox="0 0 24 24"
          width="18"
          height="18"
          fill="none"
          stroke="currentColor"
          stroke-width="1.7"
          stroke-linecap="round"
          stroke-linejoin="round"
        >
          <path d="M4 19V9"></path>
          <path d="M10 19V5"></path>
          <path d="M16 19v-7"></path>
          <path d="M22 19H2"></path>
        </svg>
      </div>

      <span>${esc(text)}</span>
    </div>
  `;
}

async function loadDashboard() {
  const root = $("#dash-root");

  if (!root) return;

  skIn("#dash-root", skeleton.dashboard());

  try {
    const d = await api("/api/dashboard");

    const c = d.counts || {};
    const g = d.coverage || {};
    const bt = d.by_type || {};
    const projects = d.projects || [];

    const icons = {
      projects: `
        <svg viewBox="0 0 24 24">
          <path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"></path>
        </svg>
      `,

      features: `
        <svg viewBox="0 0 24 24">
          <rect x="3" y="3" width="7" height="7" rx="1.5"></rect>
          <rect x="14" y="3" width="7" height="7" rx="1.5"></rect>
          <rect x="3" y="14" width="7" height="7" rx="1.5"></rect>
          <rect x="14" y="14" width="7" height="7" rx="1.5"></rect>
        </svg>
      `,

      test_cases: `
        <svg viewBox="0 0 24 24">
          <rect x="5" y="3" width="14" height="18" rx="2"></rect>
          <path d="M9 8h6"></path>
          <path d="m9 13 2 2 4-4"></path>
        </svg>
      `,

      test_steps: `
        <svg viewBox="0 0 24 24">
          <path d="M8 6h13"></path>
          <path d="M8 12h13"></path>
          <path d="M8 18h13"></path>
          <circle cx="3.5" cy="6" r="1"></circle>
          <circle cx="3.5" cy="12" r="1"></circle>
          <circle cx="3.5" cy="18" r="1"></circle>
        </svg>
      `,

      documents: `
        <svg viewBox="0 0 24 24">
          <path d="M6 2h8l4 4v16H6z"></path>
          <path d="M14 2v5h5"></path>
          <path d="M9 13h6"></path>
          <path d="M9 17h4"></path>
        </svg>
      `,

      repos: `
        <svg viewBox="0 0 24 24">
          <circle cx="6" cy="5" r="2"></circle>
          <circle cx="18" cy="6" r="2"></circle>
          <circle cx="6" cy="19" r="2"></circle>
          <path d="M6 7v10"></path>
          <path d="M8 7c6 0 3 6 8 6"></path>
        </svg>
      `,

      pull_requests: `
        <svg viewBox="0 0 24 24">
          <circle cx="6" cy="5" r="2"></circle>
          <circle cx="18" cy="18" r="2"></circle>
          <path d="M6 7v12"></path>
          <path d="M18 16V9a3 3 0 0 0-3-3H9"></path>
          <path d="m12 3-3 3 3 3"></path>
        </svg>
      `,
    };

    /**
     * KPI metrics
     */
    const metricsConfig = [
      ["projects", "Projects", "cyan"],
      ["features", "Features", "violet"],
      ["test_cases", "Test cases", "blue"],
      ["test_steps", "Test steps", "indigo"],
      ["documents", "Documents", "amber"],
      ["repos", "Repositories", "emerald"],
      ["pull_requests", "Pull requests", "rose"],
    ];

    const metrics = metricsConfig
      .map(([key, label, tone]) =>
        dashboardMetric(label, c[key] ?? 0, icons[key], tone),
      )
      .join("");

    /**
     * Coverage
     */
    const codePct = clampPercent(g.code_pct);
    const automationPct = clampPercent(g.automation_pct);

    const coverage = `
      <div class="dashboard-coverage-list">

        ${dashboardCoverageRow({
          label: "Code coverage",
          description: "Test cases exercised by mapped pull requests",
          value: codePct,
          className: "code",
        })}

        ${dashboardCoverageRow({
          label: "Automation coverage",
          description: "Test cases backed by developer-written automated tests",
          value: automationPct,
          className: "automation",
        })}

      </div>

      <div class="dashboard-coverage-summary">

        <div class="dashboard-summary-item">
          <span class="dashboard-summary-dot covered"></span>

          <span>
            <strong>${g.covered_cases ?? 0}</strong>
            covered
          </span>
        </div>

        <div class="dashboard-summary-divider"></div>

        <div class="dashboard-summary-item">
          <span class="dashboard-summary-dot automated"></span>

          <span>
            <strong>${g.automated_cases ?? 0}</strong>
            automated
          </span>
        </div>

        <div class="dashboard-summary-divider"></div>

        <div class="dashboard-summary-item muted">
          ${c.test_cases ?? 0} total cases
        </div>

      </div>
    `;

    /**
     * Test case distribution
     */
    const typePalette = [
      RC_COLORS.sky,
      RC_COLORS.violet,
      RC_COLORS.emerald,
      RC_COLORS.amber,
      RC_COLORS.rose,
      RC_COLORS.teal,
    ];

    const maxTypeValue = Math.max(...Object.values(bt).map(Number), 1);

    const typeRows = Object.entries(bt)
      .map(([type, count], index) => {
        const value = Number(count) || 0;
        const width = (value / maxTypeValue) * 100;
        const color = typePalette[index % typePalette.length];

        return `
          <div class="dashboard-type-row">

            <div class="dashboard-type-name">
              ${esc(type)}
            </div>

            <div class="dashboard-type-track">
              <div
                class="dashboard-type-fill"
                style="
                  width:${width}%;
                  background:${color};
                "
              ></div>
            </div>

            <div class="dashboard-type-count">
              ${value}
            </div>

          </div>
        `;
      })
      .join("");

    const byType = typeRows
      ? `<div class="dashboard-type-list">${typeRows}</div>`
      : dashboardEmptyState("No test case data yet");

    /**
     * Project rollup
     */
    const rollup = projects.length
      ? `
        <div class="dashboard-table-wrap">
          <table class="dashboard-table">

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
              ${projects
                .map((p) => {
                  const projectCodePct = clampPercent(p.code_pct);

                  const projectAutomationPct = clampPercent(p.automation_pct);

                  return `
                    <tr>

                      <td>
                        <div class="dashboard-project-name">
                          <span class="dashboard-project-mark"></span>
                          ${esc(p.name)}
                        </div>
                      </td>

                      <td>
                        ${p.features ?? 0}
                      </td>

                      <td>
                        ${p.test_cases ?? 0}
                      </td>

                      <td>
                        <div class="dashboard-table-coverage">
                          <span>
                            ${projectCodePct}%
                          </span>

                          <div class="dashboard-mini-track">
                            <div
                              class="dashboard-mini-fill code"
                              style="width:${projectCodePct}%"
                            ></div>
                          </div>
                        </div>
                      </td>

                      <td>
                        <div class="dashboard-table-coverage">
                          <span>
                            ${projectAutomationPct}%
                          </span>

                          <div class="dashboard-mini-track">
                            <div
                              class="dashboard-mini-fill automation"
                              style="width:${projectAutomationPct}%"
                            ></div>
                          </div>
                        </div>
                      </td>

                      <td>
                        ${p.repos ?? 0}
                      </td>

                      <td>
                        ${p.prs ?? 0}
                      </td>

                    </tr>
                  `;
                })
                .join("")}
            </tbody>

          </table>
        </div>
      `
      : dashboardEmptyState("Create your first project to see project metrics");

    /**
     * Page markup
     */
    root.innerHTML = `
      <div class="dashboard-page">

        <!-- PAGE HEADER -->
        <div class="dashboard-heading">

          <div>
            <h1>Overview</h1>

            <p>
              Monitor projects, test coverage and engineering activity.
            </p>
          </div>

        </div>


        <!-- KPI GRID -->
        <div class="dashboard-metrics">
          ${metrics}
        </div>

        ${d.sync?.running
          ? `<p class="muted" style="margin: -8px 0 0;">
              Sync in progress (${d.sync.ingested ?? 0} PRs ingested so far) — counts
              below may change until it finishes, and can briefly disagree with the
              repository list fetched at a different moment.
            </p>`
          : ""}


        <!-- ANALYTICS -->
        <div class="dashboard-analytics-grid">

          <section class="dashboard-panel">

            <div class="dashboard-panel-heading">
              <div>
                <h2>Coverage</h2>

                <p>
                  How effectively your test cases are exercised by code and automation.
                </p>
              </div>
            </div>

            ${coverage}

          </section>


          <section class="dashboard-panel">

            <div class="dashboard-panel-heading">
              <div>
                <h2>Test cases by type</h2>

                <p>
                  Distribution of your current test case library.
                </p>
              </div>

              <span class="dashboard-total">
                ${c.test_cases ?? 0} total
              </span>
            </div>

            ${byType}

          </section>

        </div>


        <!-- PROJECTS -->
        <section class="dashboard-panel dashboard-projects">

          <div class="dashboard-panel-heading">

            <div>
              <h2>Projects</h2>

              <p>
                Coverage and repository activity across your projects.
              </p>
            </div>

            <span class="dashboard-total">
              ${c.projects ?? 0}
              ${Number(c.projects) === 1 ? "project" : "projects"}
            </span>

          </div>

          ${rollup}

        </section>

      </div>
    `;
  } catch (e) {
    root.innerHTML = `
      <div class="dashboard-page">

        <div class="dashboard-heading">
          <div>
            <h1>Overview</h1>

            <p>
              Monitor projects, test coverage and engineering activity.
            </p>
          </div>
        </div>

        <div class="dashboard-error">

          <div class="dashboard-error-icon">
            <svg
              viewBox="0 0 24 24"
              width="18"
              height="18"
              fill="none"
              stroke="currentColor"
              stroke-width="1.8"
              stroke-linecap="round"
              stroke-linejoin="round"
            >
              <circle cx="12" cy="12" r="9"></circle>
              <path d="M12 8v5"></path>
              <path d="M12 17h.01"></path>
            </svg>
          </div>

          <div class="dashboard-error-copy">
            <strong>Could not load dashboard</strong>
            <span>${esc(e.message)}</span>
          </div>

          <button
            type="button"
            class="ghost dashboard-retry"
            onclick="loadDashboard()"
          >
            Retry
          </button>

        </div>

      </div>
    `;
  }
}
