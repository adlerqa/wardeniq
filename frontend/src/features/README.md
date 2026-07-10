# Features

Each subfolder is a self-contained feature module. During the migration, most
folders start as **placeholders** — the corresponding view still runs from the
legacy shell inside `<LegacyApp/>`. When ready, port the view into idiomatic
React and swap it in from `src/App.jsx`.

## Per-view checklist

1. Create `index.jsx` that renders the view using real React state.
2. Use `api()` from `src/lib/api.js` for backend calls (never touch fetch
   directly, and never import from `src/legacy/*`).
3. Use `useToast()` / `useModal()` from `src/lib/*` for feedback + dialogs.
4. Style with **Tailwind utility classes** (`bg-panel`, `text-muted`,
   `border-line`, etc. — see `tailwind.config.js` for the design-token
   bridge). See `auth/LoginPage.jsx` for the reference pattern. Never add
   new rules to `src/styles/global.css` — that stylesheet is legacy and
   should only shrink.
5. Delete the corresponding HTML fragment from
   `src/legacy/legacyShellHtml.js` and the init/render functions from
   `src/legacy/legacyApp.js`.
6. Update `src/App.jsx` — introduce React Router (already installed) and
   route the new view under its path (`/dashboard`, `/projects`, etc.).
7. Add a smoke test under `frontend/tests/` (once test infra lands).

## Migration order (suggested)

Simpler views first, so the shared infrastructure gets exercised early:

1. `dashboard` — read-only KPIs + coverage gauges (uses `/api/dashboard`).
2. `config` — settings form CRUD (uses `/api/settings`).
3. `users` — admin table (uses `/api/users`).
4. `usage` — LLM cost + call stats (uses `/api/usage`).
5. `steps` — Step Library CRUD.
6. `cases` — Test Cases (list + filters + editor).
7. `projects` + `features` — Projects/Repos landing, create wizard, feature
   workspace. Largest surface — split further as needed.
8. `cycles` — Code Analysis & Cycles.
9. `mindmap` — Deep code analysis / coverage review.
10. `validator`, `testplan`, `gap` — sub-flows.
