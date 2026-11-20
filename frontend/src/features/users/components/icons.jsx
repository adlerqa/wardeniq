/** Row-action icons for the Users list (same paths as the legacy markup). */
const svg = (children, round = true) => (
  <svg
    viewBox="0 0 24 24"
    width="13"
    height="13"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin={round ? "round" : undefined}
    aria-hidden="true"
  >
    {children}
  </svg>
);

export const ICONS = {
  access: svg(<path d="M12 3l7 4v5c0 4-3 7-7 9-4-2-7-5-7-9V7z" />),
  resend: svg(
    <>
      <path d="M3 7l9 6 9-6" />
      <rect x="3" y="5" width="18" height="14" rx="2" />
    </>,
  ),
  cancel: svg(<path d="M18 6L6 18M6 6l12 12" />, false),
  disable: svg(
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M5 5l14 14" />
    </>,
    false,
  ),
  enable: svg(<path d="M20 6L9 17l-5-5" />),
  lock: svg(
    <>
      <rect x="5" y="11" width="14" height="9" rx="2" />
      <path d="M8 11V8a4 4 0 0 1 8 0v3" />
    </>,
  ),
  del: svg(<path d="M3 6h18M8 6V4h8v2M6 6l1 14h10l1-14" />),
};

