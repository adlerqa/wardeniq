/** KPI tile icons (same shapes as the legacy markup; styled by Dashboard.css). */
export const METRIC_ICONS = {
  projects: (
    <svg viewBox="0 0 24 24">
      <path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
    </svg>
  ),
  features: (
    <svg viewBox="0 0 24 24">
      <rect x="3" y="3" width="7" height="7" rx="1.5" />
      <rect x="14" y="3" width="7" height="7" rx="1.5" />
      <rect x="3" y="14" width="7" height="7" rx="1.5" />
      <rect x="14" y="14" width="7" height="7" rx="1.5" />
    </svg>
  ),
  test_cases: (
    <svg viewBox="0 0 24 24">
      <rect x="5" y="3" width="14" height="18" rx="2" />
      <path d="M9 8h6" />
      <path d="m9 13 2 2 4-4" />
    </svg>
  ),
  test_steps: (
    <svg viewBox="0 0 24 24">
      <path d="M8 6h13" />
      <path d="M8 12h13" />
      <path d="M8 18h13" />
      <circle cx="3.5" cy="6" r="1" />
      <circle cx="3.5" cy="12" r="1" />
      <circle cx="3.5" cy="18" r="1" />
    </svg>
  ),
  documents: (
    <svg viewBox="0 0 24 24">
      <path d="M6 2h8l4 4v16H6z" />
      <path d="M14 2v5h5" />
      <path d="M9 13h6" />
      <path d="M9 17h4" />
    </svg>
  ),
  repos: (
    <svg viewBox="0 0 24 24">
      <circle cx="6" cy="5" r="2" />
      <circle cx="18" cy="6" r="2" />
      <circle cx="6" cy="19" r="2" />
      <path d="M6 7v10" />
      <path d="M8 7c6 0 3 6 8 6" />
    </svg>
  ),
  pull_requests: (
    <svg viewBox="0 0 24 24">
      <circle cx="6" cy="5" r="2" />
      <circle cx="18" cy="18" r="2" />
      <path d="M6 7v12" />
      <path d="M18 16V9a3 3 0 0 0-3-3H9" />
      <path d="m12 3-3 3 3 3" />
    </svg>
  ),
};
