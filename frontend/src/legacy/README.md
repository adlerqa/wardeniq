# Legacy bridge

This directory holds the untouched HTML fragments and JavaScript that back each
view during the incremental migration to idiomatic React.

## Why it exists

`app/static/index.html` was ~6,750 lines with ~4,600 lines of imperative
DOM-manipulating JavaScript. Rewriting every view in one pass would be huge and
risky, so the migration follows a **strangler-fig** pattern:

1. The React shell owns routing, auth, layout, the API client, and the toast/
   modal utilities — all idiomatic React (see `src/layout/`, `src/lib/`,
   `src/hooks/`, `src/features/auth/`).
2. Views that haven&apos;t been refactored yet render inside a `<LegacyView>`
   component. `<LegacyView>` injects the original markup fragment into a DOM
   ref and runs the associated init function from `legacyApp.js`. Behavior is
   identical to the pre-migration single-file app because we&apos;re running the
   same code against the same DOM.
3. Views get refactored one at a time — replace the `<LegacyView>` call in
   `src/features/<name>/index.jsx` with real React components, and delete the
   corresponding fragment + init function from this folder.

## Files

- `legacyBody.js` — exports HTML fragments extracted from the original body,
  keyed by view name (e.g. `dashboard`, `projects`, `config`).
- `legacyApp.js` — the ~4,600 lines of vanilla JS from the original
  `<script>` blocks, wrapped so it can be initialized on demand.
- `LegacyView.jsx` — React wrapper. `<LegacyView view="dashboard" />` renders
  the corresponding fragment and calls the view&apos;s init hook.

## Rules for the strangler

- Do **not** import the legacy JS from any refactored (idiomatic) view; instead
  call `api()` from `src/lib/api.js` and drive UI with React state.
- When a view is fully ported, remove its fragment from `legacyBody.js` and
  strip its init from `legacyApp.js` in the same commit.
- Never re-use IDs (`#foo`) across legacy and React-owned code — the ported
  view should namespace with CSS classes to avoid conflicts.
