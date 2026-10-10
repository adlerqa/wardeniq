"""Structural guard for the Phase 5 store/ mixin split (docs/internal/REFACTOR_PLAN.md section 13).

`Store` is composed from ~16 domain mixins plus `BaseStore` (see store/__init__.py).
Because Python's MRO silently picks the first match on a name collision, a duplicate
method/property name introduced across two mixins (e.g. by a future private-fork
addition, or a careless copy-paste during a later split) would shadow one
implementation with no error at import time and no obvious symptom until the shadowed
method's behavior goes missing in production. This test makes that failure loud and
immediate instead.
"""
from collections import Counter

import store


def test_no_duplicate_store_methods():
    names = [n for cls in store.Store.__mro__[1:] if cls is not object
             for n in vars(cls) if not n.startswith("__")]
    dupes = [n for n, c in Counter(names).items() if c > 1]
    assert dupes == [], f"duplicate member name(s) across Store mixins: {dupes}"
