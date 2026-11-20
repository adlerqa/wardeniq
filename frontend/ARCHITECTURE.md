# WardenIQ Frontend Architecture

This frontend is now organized by **application responsibility** instead of by file type or one global script.

## Source layout

```text
src/
├── app/
│   └── App.jsx
├── components/
│   ├── brand/
│   │   └── BrandMark.jsx
│   ├── feedback/
│   │   └── AppErrorBoundary.jsx
│   └── overlays/
│       ├── AppOverlays.jsx
│       └── modals/
├── lib/
│   ├── api.js            # fetch helper (same behaviour as compat api())
│   ├── compatBridge.js   # toast / confirm / modal / sign-in from the compat runtime
│   └── html.js
├── layouts/
│   ├── ApplicationFrame.jsx
│   ├── Header.jsx
│   └── Sidebar.jsx
├── features/
│   ├── auth/
│   ├── dashboard/
│   ├── projects/
│   ├── features/
│   ├── test-cases/
│   ├── code-analysis/
│   ├── test-cycles/
│   ├── mind-map/
│   ├── step-library/
│   ├── usage/
│   ├── configuration/
│   ├── users/
│   ├── validator/
│   ├── test-plan/
│   └── gap-analysis/
├── compat/
│   └── runtime/
│       ├── RuntimeBridge.jsx
│       └── controllers/
└── styles/
    ├── tailwind.css
    ├── app.css
    └── compat/
```

## What changed

The previous migration still had three monoliths:

- `src/legacy/legacyApp.js` — about 10,800 lines / 424 KB
- `src/legacy/legacyShellHtml.js` — about 1,200 lines / 100 KB
- `src/styles/global.css` — about 7,500 lines / 146 KB

Those files no longer exist.

The screen shell is now actual React JSX. Every major screen has its own page boundary, larger screens are split into domain components, shared modals are individual components, and application chrome lives under `layouts/`.

The old imperative behavior from the current Piyush build is preserved in `src/compat/runtime/controllers/`, split into 17 domain files. This compatibility layer exists so this structural refactor does not silently change API behavior, permissions, imports, analysis flows, or generation workflows.

## Tailwind rule

**All new React-owned UI must be styled with Tailwind classes in JSX.**

Do not add new rules to `styles/compat/`. Those files only preserve styles required by HTML that the existing imperative controllers still generate at runtime. Delete the relevant compatibility CSS when a controller is replaced with React rendering.

`styles/app.css` is intentionally tiny and is only for truly application-wide base behavior.

## Component rule

A page component should coordinate a screen, not contain the entire product feature.

Examples already applied:

- Projects → `ProjectListPanel`, `ProjectDetailPanel`
- Features → list, create, workspace components
- Configuration → one component per settings area
- Users → invite, users list, audit log
- Test cycles → create, templates, list, detail
- Validator / Test Plan / Gap Analysis → header, empty state, workspace
- Overlays → one component per modal

## Compatibility controller map

| Controller | Responsibility |
|---|---|
| `00-core.js` | shared helpers, API helper, navigation, shared state |
| `01-dashboard.js` | dashboard |
| `02-projects.js` | projects and repositories |
| `03-features-and-usage.js` | feature workflows and usage |
| `04-test-cases.js` | test-case view/editor behavior |
| `05-step-workflows.js` | step workflows |
| `06-configuration.js` | settings |
| `07-library-and-crud.js` | step library and shared CRUD |
| `08-code-analysis-and-cycles.js` | analysis and test cycles |
| `09-mind-map-and-jobs.js` | mind map, jobs, regeneration |
| `10-auth.js` | authentication |
| `11-users.js` | user administration |
| `12-validator.js` | MCQ validator |
| `13-gap-analysis.js` | gap analysis |
| `14-test-plan.js` | test plan |
| `15-imports.js` | sheet imports / import library |
| `16-boot.js` | startup sequence |

These files are **not a target architecture**. They are an explicit migration boundary. New functionality should not be added as another large global controller.

## Next migration pattern

When converting a controller to fully idiomatic React:

1. Create API functions/hooks inside that feature, calling `src/lib/api.js`
   (and `src/lib/compatBridge.js` for toasts and dialogs).
2. Move DOM state into React state.
3. Replace `innerHTML` output with React components.
4. Remove that feature's imperative controller code.
5. Remove its corresponding compatibility CSS.
6. Add focused component/hook tests.

This allows WardenIQ to move toward a pure React/Tailwind frontend without a risky one-shot rewrite of all existing behavior.

## Verification performed

- JSX syntax parsing: passed.
- ESLint for React source: passed with zero warnings/errors.
- Original static DOM ID contract: **474 / 474 preserved**.
- Runtime behavior source: split files recombine byte-for-byte to the uploaded Piyush runtime.
- Compatibility CSS: split files recombine byte-for-byte to the uploaded stylesheet.
- Tailwind compilation: passed.
- Vite bundle could not run in this Linux sandbox because the uploaded dependency folder contains Windows Rollup native binaries. A clean `npm ci` on the target OS/Docker build installs the matching Rollup binary.
