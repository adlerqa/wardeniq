"""Live application singletons.

Moved out of main.py (Phase 1 of docs/internal/REFACTOR_PLAN.md). This module owns the
process-wide mutable state: the single `Store` instance, the poller/sync
status dict, and the `embedder` singleton.

CRITICAL — embedder: `embedder` is declared here as a placeholder (`None`)
rather than computed. It is populated as an import-time side effect by
`core/deps.py` (Phase 2), via `state.embedder = current_embedder()`, once
`current_embedder()` is defined there. Building it here instead would require
importing `core.deps` from this module, which imports `core.state` back —
a circular import.

Consumers that need the *live* embedder object (it is reassigned at runtime —
see `_reembed_worker`, the one `global embedder` rebind in the codebase) MUST
do:

    from core import state
    ... state.embedder ...

and MUST NOT do:

    from core.state import embedder

The latter binds a name to whatever `state.embedder` pointed to at import
time; it is never updated when `core.deps` (or the reembed worker) later does
`state.embedder = <new Embedder>`, so any consumer that name-imported it would
silently keep using a stale, pre-switch embedder forever.
"""
from core.config import DB_NAME, EMBED_DIM, MONGO_URI
from embeddings import Embedder
from store import Store

store = Store(MONGO_URI, DB_NAME, EMBED_DIM)

# Shared poller/sync status dict, read by /api/sync/status and written by the
# background GitHub/GitLab poller loop. Deliberately left without a type
# annotation, matching the original main.py: mypy's baseline "Need type
# annotation for SYNC" error (and the ~10 downstream errors it causes at SYNC's
# call sites) is pre-existing docs/internal/REFACTOR_PLAN.md baseline debt, not something to
# fix incidentally as part of this move.
SYNC = {"running": False, "last": None, "ingested": 0, "mapped": 0, "errors": []}

# Placeholder — see module docstring. Populated by core/deps.py in Phase 2, before
# any request-handling code runs. Annotated as a concrete Embedder (not Optional)
# because every consumer (main.py's routes, the workers moving here in Phase 3)
# treats it as always-present post-import and calls .embed()/.provider/.model/
# .dim/.health() directly with no None-check — matching the ORIGINAL code, where
# `embedder = current_embedder()` was never Optional either. The `None` default
# below is a deliberate, localized fib to the type checker for this one line only;
# `# type: ignore[assignment]` keeps it from cascading into a spurious
# "X | None has no attribute embed" error at every one of the ~20 call sites.
embedder: Embedder = None  # type: ignore[assignment]
