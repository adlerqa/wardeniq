"""Per-process LLM / embedding token accounting.

Every background job runs in its own thread (see ``launch_job``). We bind a
thread-local *recorder* for the life of that job; the ``LLM`` and ``Embedder``
clients push each call's token counts into it, tagged by model. When the job
finishes we summarise the recorder (tokens per model + cost) and store it on
the job document, so the UI can show "this process used N tokens on model X,
costing $Y".

Cost comes from a price table in USD per 1,000,000 tokens (input, output).
Defaults below are ballpark public list prices and are meant to be overridden
in Settings; local Ollama models are free ($0).

NOTE: recording is thread-local, so calls made on *child* threads spawned by a
worker are not attributed. In practice the pipelines call the model
sequentially on the job thread, which is what we capture.
"""
import threading

_local = threading.local()

# USD per 1,000,000 tokens: {model_key: {"in": input_price, "out": output_price}}.
# Keys MUST match the model ids offered in the Settings dropdown (PREDEFINED_MODELS
# in the UI) so the pricing editor and the model picker stay consistent. Prices for
# newer models are tier-based estimates — refine them in Configuration → LLM pricing.
DEFAULT_PRICES = {
    # OpenAI
    "gpt-4o": {"in": 2.50, "out": 10.00},
    "gpt-4o-mini": {"in": 0.15, "out": 0.60},
    "gpt-4.1": {"in": 2.00, "out": 8.00},
    # Anthropic
    "claude-opus-4-6": {"in": 15.00, "out": 75.00},
    "claude-sonnet-4-6": {"in": 3.00, "out": 15.00},
    "claude-haiku-4-5": {"in": 0.80, "out": 4.00},
    # Google Gemini
    "gemini-3.5-flash": {"in": 0.10, "out": 0.40},
    "gemini-3.5-pro": {"in": 1.25, "out": 5.00},
    "gemini-3.1-pro": {"in": 1.25, "out": 5.00},
    "gemini-3.1-flash-lite": {"in": 0.05, "out": 0.20},
    # Mistral
    "mistral-large-latest": {"in": 2.00, "out": 6.00},
    "mistral-small-latest": {"in": 0.20, "out": 0.60},
    "open-mistral-nemo": {"in": 0.15, "out": 0.15},
    "codestral-latest": {"in": 0.30, "out": 0.90},
    # Local Ollama models — free
    "qwen2.5:7b": {"in": 0.0, "out": 0.0},
    "llama3:8b": {"in": 0.0, "out": 0.0},
    "mistral:7b": {"in": 0.0, "out": 0.0},
    # Local embeddings (Ollama) — free
    "nomic-embed-text": {"in": 0.0, "out": 0.0},
    "mxbai-embed-large": {"in": 0.0, "out": 0.0},
    # Hosted embeddings (input-only; no output tokens)
    "text-embedding-3-small": {"in": 0.02, "out": 0.0},
    "text-embedding-3-large": {"in": 0.13, "out": 0.0},
    "text-embedding-004": {"in": 0.0, "out": 0.0},
    "gemini-embedding-001": {"in": 0.15, "out": 0.0},
    "voyage-3": {"in": 0.06, "out": 0.0},
    "voyage-3-lite": {"in": 0.02, "out": 0.0},
    "voyage-3-large": {"in": 0.18, "out": 0.0},
}

# Family fallbacks: matched when a concrete model name (e.g. "gemini-3.1-flash-lite")
# doesn't hit an exact/substring price. Checked in order, so put the more specific
# variants first. Prices are ballpark and meant to be refined in Settings.
FAMILY_FALLBACKS = [
    (("gpt-4o", "mini"), {"in": 0.15, "out": 0.60}),
    (("gpt-4o",), {"in": 2.50, "out": 10.00}),
    (("gpt-4.1", "nano"), {"in": 0.10, "out": 0.40}),
    (("gpt-4.1", "mini"), {"in": 0.40, "out": 1.60}),
    (("gpt-4.1",), {"in": 2.00, "out": 8.00}),
    (("gpt-4", "turbo"), {"in": 10.00, "out": 30.00}),
    (("gpt-3.5",), {"in": 0.50, "out": 1.50}),
    (("o3", "mini"), {"in": 1.10, "out": 4.40}),
    (("claude", "haiku"), {"in": 0.80, "out": 4.00}),
    (("claude", "sonnet"), {"in": 3.00, "out": 15.00}),
    (("claude", "opus"), {"in": 15.00, "out": 75.00}),
    (("gemini", "flash", "lite"), {"in": 0.05, "out": 0.20}),
    (("gemini", "flash"), {"in": 0.10, "out": 0.40}),
    (("gemini", "pro"), {"in": 1.25, "out": 5.00}),
    (("mistral", "large"), {"in": 2.00, "out": 6.00}),
    (("mistral", "small"), {"in": 0.20, "out": 0.60}),
]


def start():
    """Begin recording for the current thread. Returns the (empty) recorder."""
    _local.rec = {}
    return _local.rec


def stop():
    """Finish recording for the current thread and return what was collected."""
    rec = getattr(_local, "rec", None)
    _local.rec = None
    return rec or {}


def record(model, prompt_tokens=0, completion_tokens=0, kind="llm", estimated=False):
    """Add one call's token counts to the current thread's recorder (no-op if
    no recorder is bound, e.g. calls made outside a tracked job)."""
    rec = getattr(_local, "rec", None)
    if rec is None:
        return
    key = model or "unknown"
    m = rec.setdefault(key, {"calls": 0, "prompt_tokens": 0,
                             "completion_tokens": 0, "kind": kind, "estimated": False})
    m["calls"] += 1
    m["prompt_tokens"] += int(prompt_tokens or 0)
    m["completion_tokens"] += int(completion_tokens or 0)
    if estimated:
        m["estimated"] = True
    if kind == "llm":            # llm wins over embedding if a model is used for both
        m["kind"] = "llm"


def price_for(model, prices):
    """Resolve a model's price entry. Order: exact → user/default substring →
    local Ollama tag (free) → model-family fallback. Returns None if nothing fits."""
    if not model:
        return None
    if model in prices:                     # exact (incl. Settings overrides)
        return prices[model]
    low = model.lower()
    for k, v in prices.items():             # case-insensitive substring either way
        kl = k.lower()
        if kl == low or kl in low or low in kl:
            return v
    if ":" in low:                          # Ollama-style tag (e.g. qwen2.5:7b) → local/free
        return {"in": 0.0, "out": 0.0}
    for kws, price in FAMILY_FALLBACKS:     # e.g. gemini-3.1-flash-lite → gemini/flash/lite
        if all(t in low for t in kws):
            return price
    return None


def summarize(rec, prices=None):
    """Turn a raw recorder into {by_model, prompt_tokens, completion_tokens,
    total_tokens, cost_usd}. cost_usd is None when nothing could be priced."""
    price_map = {**DEFAULT_PRICES, **(prices or {})}
    by_model, tot_in, tot_out, tot_cost, any_priced = {}, 0, 0, 0.0, False
    for model, d in (rec or {}).items():
        pin = int(d.get("prompt_tokens", 0))
        pout = int(d.get("completion_tokens", 0))
        p = price_for(model, price_map)
        cost = None
        if p is not None:
            cost = (pin / 1e6) * float(p.get("in", 0)) + (pout / 1e6) * float(p.get("out", 0))
            tot_cost += cost
            any_priced = True
        by_model[model] = {
            "calls": int(d.get("calls", 0)),
            "prompt_tokens": pin,
            "completion_tokens": pout,
            "total_tokens": pin + pout,
            "kind": d.get("kind", "llm"),
            "estimated": bool(d.get("estimated", False)),
            "cost_usd": round(cost, 6) if cost is not None else None,
        }
        tot_in += pin
        tot_out += pout
    return {
        "by_model": by_model,
        "prompt_tokens": tot_in,
        "completion_tokens": tot_out,
        "total_tokens": tot_in + tot_out,
        "cost_usd": round(tot_cost, 6) if any_priced else None,
    }
