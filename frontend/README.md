# WardenIQ Frontend

Production-oriented React + Vite + Tailwind frontend for WardenIQ.

## Development

```bash
npm ci
npm run dev
```

The Vite dev server proxies `/api` to the configured FastAPI backend in `vite.config.js`.

## Quality checks

```bash
npm run lint
npm run build
```

## Architecture

Read [`ARCHITECTURE.md`](./ARCHITECTURE.md) before adding or moving frontend code.

Key rules:

- Put screen code under `src/features/<feature>/`.
- Put reusable product-wide components under `src/components/`.
- Put permanent navigation/chrome under `src/layouts/`.
- Use Tailwind utilities for new React UI.
- Do not add new styles to `src/styles/compat/`.
- Do not create another global runtime file.
- `src/compat/runtime/controllers/` preserves existing behavior while screens are progressively converted from imperative DOM rendering to React state/rendering.

## Compatibility runtime loading

All 18 compatibility controllers are bundled eagerly, then combined in filename
order into one classic script to preserve their shared global scope. The bridge
shares pending initialization and guards against duplicate injection, including
React StrictMode effect replays. A failed script insertion is logged and leaves
initialization available to a later loader call; it is not retried automatically.
Successful insertion does not guarantee error-free controller execution.

Controllers are not fetched separately or deferred until a screen opens. This
avoids startup request fan-out and separate-chunk compression overhead rather than
optimizing the main-chunk size. Production sourcemaps are disabled independently
of this loading strategy; Vite's large-chunk warning may still appear.
