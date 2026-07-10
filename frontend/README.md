# wardenIQ — Frontend (React + Vite)

Migration of the legacy single-file frontend (`app/static/index.html`) into a
scalable React + Vite codebase. **Currently on branch `master` — do not merge
to `main` until the migration reaches full feature parity.**

## Migration approach: strangler fig

The legacy `index.html` was ~6,750 lines with ~4,600 lines of imperative JS
that drove the DOM by ID. Rewriting every view in a single pass would be huge
and risky, so the migration follows a **strangler-fig** pattern:

- The React shell owns entry point, HMR, `/api` proxy, and shared
  infrastructure (auth flow, API client, toast/modal utilities).
- Until refactored, each view runs from a "vessel" component
  (`src/legacy/LegacyApp.jsx`) that mounts the original HTML + JS into a ref.
  Behavior is 100% identical to the pre-migration app because it *is* the
  same code, hosted inside React.
- Views migrate one at a time under `src/features/<name>/`. Each rewrite
  removes its fragment from `src/legacy/legacyShellHtml.js` and its init
  functions from `src/legacy/legacyApp.js`, so the legacy vessel shrinks
  until it's gone.

This is the standard pattern for large legacy migrations and keeps the app
shippable at every step.

## Folder structure

```
frontend/
├── index.html                  # Vite entry HTML (mounts #root)
├── package.json
├── vite.config.js              # /api → :8000 proxy, build → app/static-react
├── .eslintrc.cjs
└── src/
    ├── main.jsx                # React root
    ├── App.jsx                 # ToastProvider + ModalProvider + <LegacyApp/>
    ├── styles/
    │   ├── global.css          # Ported from the legacy <style> blocks
    │   └── reset.css
    ├── lib/
    │   ├── api.js              # fetch wrapper, 401 handling
    │   ├── toast.jsx           # <ToastProvider/> + toast() global helper
    │   └── modal.jsx           # uiPrompt / uiConfirm / uiModalHTML
    ├── hooks/
    │   └── useSession.js       # /api/auth/me lifecycle
    ├── layout/                 # AppShell, Sidebar, Header — ready to swap in
    ├── features/
    │   ├── README.md           # Per-view migration checklist
    │   ├── auth/               # LoginPage, InviteGate (idiomatic React)
    │   ├── dashboard/          # Placeholder — see index.jsx TODO
    │   ├── projects/           # Placeholder
    │   ├── features/           # Placeholder (feature workspace)
    │   ├── cases/              # Placeholder
    │   ├── cycles/             # Placeholder
    │   ├── mindmap/            # Placeholder
    │   ├── steps/              # Placeholder
    │   ├── usage/              # Placeholder
    │   ├── config/             # Placeholder
    │   ├── users/              # Placeholder
    │   ├── validator/          # Placeholder
    │   ├── testplan/           # Placeholder
    │   └── gap/                # Placeholder
    └── legacy/                 # Vessel — see README there
        ├── README.md
        ├── legacyShellHtml.js  # Extracted HTML (login + shell + modals)
        ├── legacyApp.js        # ~4,600 lines of original JS, wrapped
        └── LegacyApp.jsx       # Mounts the above into a ref
```

## Local development

Prerequisites: Node 18+ (Node 20 LTS recommended) and the FastAPI backend
running on `http://localhost:8000` (via the repo root `./run.sh`).

```bash
cd frontend
npm install
npm run dev            # Vite serves at http://localhost:5173
```

The Vite dev server proxies `/api/*` and cookies to `http://localhost:8000`,
so the passwordless email OTP session flow works transparently.

Production build:

```bash
npm run build          # emits into app/static-react/
npm run preview        # local preview of the built bundle
```

Note: FastAPI serves this built SPA from `app/static-react/` at `:8001` (see the
`/assets` mount + `/` route in `app/main.py`). The legacy `app/static/index.html`
has been removed. In Docker, `./run.sh` builds `frontend/` and bakes the output
into the image automatically, so running the app needs no host Node and no
separate `npm run dev`. `app/static-react/` is git-ignored (a build artifact).

## Styling: Tailwind for new code, legacy CSS for the vessel

- **All new React components use Tailwind utility classes.** See
  `src/features/auth/LoginPage.jsx` as the reference pattern.
- Design tokens (colors, fonts) are bridged in `tailwind.config.js` so you can
  write `bg-panel`, `text-muted`, `border-line`, `text-accent2`, etc. — these
  resolve to the same CSS variables the legacy stylesheet uses, so the look
  stays consistent across ported and unported views.
- Tailwind&apos;s `preflight` (CSS reset) is **disabled** on purpose. The legacy
  stylesheet already establishes typography, form-control styling, and layout
  rules that ported code inherits. When the vessel is fully retired and every
  view is idiomatic React, re-enable preflight and drop `src/styles/global.css`.
- Never edit `src/styles/global.css` to add new rules — it&apos;s the frozen
  legacy stylesheet and should only shrink over time.

## Adding a new view

1. Open `src/features/<view>/index.jsx` — it's a placeholder.
2. Follow the per-view checklist in `src/features/README.md`.
3. Remove the corresponding HTML fragment from
   `src/legacy/legacyShellHtml.js` and the init logic from
   `src/legacy/legacyApp.js` in the same PR.
4. Wire the new component into `App.jsx` via React Router (already installed).

## Verification checklist (before merging to `main`)

- [ ] All 13 views migrated (see `src/features/README.md` for the list).
- [ ] `src/legacy/` folder is empty / deleted.
- [ ] `npm run build` succeeds and `npm run preview` renders the app.
- [ ] Manual smoke: sign in, dashboard KPIs, create project, generate a
      feature, view test cases, run code analysis, open Mind Map.
- [ ] FastAPI serves the built React bundle in place of `app/static/`.
- [ ] `pytest` still passes.
