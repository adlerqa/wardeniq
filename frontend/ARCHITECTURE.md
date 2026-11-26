# WardenIQ Frontend Architecture

The frontend is a React 18 + Vite + Tailwind single-page app, organized by
**application responsibility** rather than by file type. Every screen, overlay and
piece of shared behaviour is React; the former compatibility runtime (imperative
controllers injected as one global script) was removed in #257.

## Source layout

```text
src/
├── main.jsx
├── app/                    # root composition, start-up and navigation
│   ├── App.jsx
│   ├── boot.js             # start-up sequence (invite links, sign-in check, first-run redirect, last view)
│   ├── useBoot.js          # runs it once on mount; status / identity refresh timers; autofill hardening
│   ├── navigation.js       # navigateTo, back bar + breadcrumbs model, goTo* shortcuts
│   ├── navState.js         # open project / feature, view, signed-in user, page title
│   └── useNavigation.js    # registers navigation + state on window; header title hook
├── layouts/                # permanent chrome
│   ├── ApplicationFrame.jsx  # sidebar, boot banner, header, back bar, screens
│   ├── Header.jsx, ServiceChips.jsx, useServiceStatus.js
│   ├── Sidebar.jsx
│   └── Backbar.jsx
├── components/
│   ├── brand/
│   ├── feedback/           # AppErrorBoundary, Skeleton
│   └── overlays/           # AppOverlays + one component per modal (toast, confirm, prompt, HTML dialog, …)
├── features/               # one folder per screen: pages/ components/ hooks/ lib/
│   ├── auth/  dashboard/  projects/  features/  test-cases/  code-analysis/
│   ├── test-cycles/  mind-map/  step-library/  usage/  configuration/  users/
│   ├── validator/  test-plan/  gap-analysis/  imports/
├── lib/
│   ├── api.js              # fetch helper: JSON, friendly errors, 401 → sign-in, 403 → "Not allowed"
│   ├── compatBridge.js     # cross-screen calls (see below)
│   ├── jobs.js             # background-job watcher (SSE + safety poll) and job log
│   ├── format.js, html.js, toast.js, bootStatus.js, brandLoader.js, skeleton.js
│   └── useSharedGlobals.js # registers the job helpers and the branded loader on window
└── styles/
    ├── tailwind.css
    ├── app.css
    └── compat/             # legacy CSS still used by existing markup (see Tailwind rule)
```

## Inside a feature

- `lib/` — pure helpers (formatting, view models, request bodies). Unit-tested without a DOM.
- `hooks/` — the screen's state, requests, pollers and actions.
- `components/` — markup only; state and handlers come from the hook.
- `pages/` — the screen's `<section class="view" id="view-…">`, composing the above.

Requests go through `src/lib/api.js`. Toasts and dialogs go through `src/lib/compatBridge.js`.

## How screens talk to each other

A screen registers the functions other parts of the app need on `window` while it is
mounted (for example `window.openFeature`, `window.loadProjects`, `window.initGap`), and
removes them on unmount if they are still its own. Callers never touch `window`
directly: they go through `src/lib/compatBridge.js`, which looks the function up at call
time and degrades to a no-op when it isn't registered. Tests stub a screen by assigning
the function on `window`.

`app/navigation.js` `navigateTo(view)` shows the view's section (by toggling the
sections' `hidden` flag), highlights the sidebar entry, calls the screen's loader through
those registrations, redraws the back bar and remembers the view (`#hash`, `wq_nav`).

Start-up (`app/useBoot.js`) runs once in App's mount effect, after every screen and
overlay has registered its functions (child effects run first).

## Tailwind rule

**All new React-owned UI must be styled with Tailwind classes in JSX.**

Do not add new rules to `styles/compat/`. Those files hold the styles of markup carried
over unchanged from the imperative UI (class names such as `card`, `badge`,
`case-group`). Delete the relevant rules when that markup is restyled with Tailwind.

`styles/app.css` is intentionally tiny and is only for truly application-wide base behavior.

## Component rule

A page component should coordinate a screen, not contain the entire product feature.

- Projects → `ProjectListPanel`, `ProjectDetailPanel`
- Features → list, create, workspace components
- Configuration → one component per settings area
- Users → invite, users list, audit log
- Test cycles → create, templates, list, detail
- Validator / Test Plan / Gap Analysis → header, empty state, workspace
- Overlays → one component per modal

## Tests

`npm test` (`node --test`) runs `frontend/tests/`: pure helper tests, and component /
hook tests that bundle a screen with esbuild and render it in jsdom with a stubbed
`fetch` and stubbed `window` registrations. `npm run check` runs ESLint (zero warnings)
and the production build.
