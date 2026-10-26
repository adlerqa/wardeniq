"""App-wide settings document (LLM/embedding config, `configured` first-run gate).

Moved out of store.py (Phase 5 of docs/internal/REFACTOR_PLAN.md).
"""


from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # mypy-only: gives this mixin visibility into the collection attributes and
    # cross-mixin helpers that store/__init__.py's Store actually composes in at
    # runtime (BaseStore.__init__ sets self.projects/self.cases/etc; other mixins
    # add their own methods). At runtime this mixin still inherits only `object`
    # (see the `else` branch) — Store's own MRO (store/__init__.py) is what really
    # provides these at runtime, unchanged from before this TYPE_CHECKING addition.
    from store.base import BaseStore as _Base
else:
    _Base = object


class SettingsMixin(_Base):
    """No __init__: shares the collection attributes/state that store/base.py's
    BaseStore.__init__ sets up (composed last in store/__init__.py's Store MRO)."""

    def _backfill_settings_configured(self):
        # First-run gate (`configured`) was added after launch. Existing installs
        # that already saved LLM settings should not be sent back to Configuration,
        # so mark them configured when meaningful LLM signals are present.
        try:
            s = self.db["settings"].find_one({"_id": "app"})
            if s and "configured" not in s and (
                s.get("llm_api_key_enc") or s.get("llm_model")
                or s.get("llm_provider") or s.get("ollama_url")
            ):
                self.db["settings"].update_one(
                    {"_id": "app"}, {"$set": {"configured": True}})
        except Exception:  # noqa: BLE001
            pass

    def get_settings(self):
        return self.db["settings"].find_one({"_id": "app"}) or {}

    def save_settings(self, doc):
        self.db["settings"].update_one({"_id": "app"}, {"$set": doc}, upsert=True)
