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

# Guards mutation of a *shared* recorder. Worker pools (testgen, sheet import)
# bind the parent job's recorder into their child threads via bind(), so several
# threads may call record() on the same dict concurrently.
_lock = threading.Lock()

# USD per 1,000,000 tokens: {model_key: {"in": input_price, "out": output_price}}.
# Keys MUST match the model ids offered in the Settings dropdown (PREDEFINED_MODELS
# in the UI) so the pricing editor and the model picker stay consistent. Prices for
# newer models are tier-based estimates — refine them in Configuration → LLM pricing.
DEFAULT_PRICES = {
    # OpenAI — keyed to the models offered in the Settings dropdown. These are legacy
    # on OpenAI's current pricing page (which now lists GPT-5.4+), so these are their
    # established list prices; re-verify when the dropdown is refreshed. (2026-07-22)
    "gpt-5": {"in": 1.25, "out": 10.00},
    "gpt-5-mini": {"in": 0.25, "out": 2.00},
    "gpt-4.1": {"in": 2.00, "out": 8.00},
    "gpt-4.1-mini": {"in": 0.40, "out": 1.60},
    "gpt-4o": {"in": 2.50, "out": 10.00},
    "gpt-4o-mini": {"in": 0.15, "out": 0.60},
    # Anthropic — base input/output per 1M tokens. Source: Anthropic docs pricing
    # (platform.claude.com/docs/en/about-claude/pricing), verified 2026-07-22.
    # NOTE: prompt-cache reads/writes and Batch-API discounts are NOT modelled here;
    # wardenIQ makes uncached, non-batch calls, so these base rates match the console.
    "claude-fable-5": {"in": 10.00, "out": 50.00},
    "claude-mythos-5": {"in": 10.00, "out": 50.00},
    "claude-opus-4-8": {"in": 5.00, "out": 25.00},
    "claude-opus-4-7": {"in": 5.00, "out": 25.00},
    "claude-opus-4-6": {"in": 5.00, "out": 25.00},
    "claude-opus-4-5": {"in": 5.00, "out": 25.00},
    "claude-opus-4-1": {"in": 15.00, "out": 75.00},   # deprecated — legacy pricing
    # Sonnet 5 is introductory $2/$10 through 2026-08-31; reverts to $3/$15 on
    # 2026-09-01 — bump this then (or set it in Configuration → LLM pricing).
    "claude-sonnet-5": {"in": 2.00, "out": 10.00},
    "claude-sonnet-4-6": {"in": 3.00, "out": 15.00},
    "claude-sonnet-4-5": {"in": 3.00, "out": 15.00},
    "claude-haiku-4-5": {"in": 1.00, "out": 5.00},
    "claude-haiku-3-5": {"in": 0.80, "out": 4.00},          # retired — legacy pricing
    "claude-3-5-haiku-latest": {"in": 0.80, "out": 4.00},   # dropdown alias for Haiku 3.5
    # Google Gemini — keyed to the Settings dropdown. Source: ai.google.dev/gemini-api
    # /docs/pricing (paid tier, standard <=200k), verified 2026-07-22.
    "gemini-3-pro-preview": {"in": 2.00, "out": 12.00},    # priced as gemini-3.1-pro-preview
    "gemini-3-flash-preview": {"in": 0.50, "out": 3.00},
    "gemini-2.5-pro": {"in": 1.25, "out": 10.00},
    "gemini-2.5-flash": {"in": 0.30, "out": 2.50},
    "gemini-2.5-flash-lite": {"in": 0.10, "out": 0.40},
    "gemini-2.0-flash": {"in": 0.10, "out": 0.40},         # deprecated
    # Mistral — keyed to the Settings dropdown. Source: mistral.ai/pricing/api,
    # verified 2026-07-22 (the "-latest" aliases point to the versions noted).
    "mistral-large-latest": {"in": 0.50, "out": 1.50},     # Mistral Large 3
    "mistral-medium-latest": {"in": 1.50, "out": 7.50},    # Mistral Medium 3.5
    "mistral-small-latest": {"in": 0.15, "out": 0.60},     # Mistral Small 4
    "ministral-8b-latest": {"in": 0.15, "out": 0.15},      # Ministral 3 8B
    "open-mistral-nemo": {"in": 0.15, "out": 0.15},
    "codestral-latest": {"in": 0.30, "out": 0.90},
    # Groq — keyed to the Settings dropdown. Source: groq.com/pricing, verified
    # 2026-07-22. The older llama3 / gemma2 / mixtral entries are deprecated on
    # GroqCloud (last-known rates, kept so the dropdown options still price).
    "llama-3.3-70b-versatile": {"in": 0.59, "out": 0.79},
    "llama-3.1-8b-instant": {"in": 0.05, "out": 0.08},
    "llama3-70b-8192": {"in": 0.59, "out": 0.79},          # legacy/deprecated
    "llama3-8b-8192": {"in": 0.05, "out": 0.08},           # legacy/deprecated
    "gemma2-9b-it": {"in": 0.20, "out": 0.20},             # legacy/deprecated
    "mixtral-8x7b-32768": {"in": 0.24, "out": 0.24},       # legacy/deprecated
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
    (("gpt-5", "nano"), {"in": 0.05, "out": 0.40}),
    (("gpt-5", "mini"), {"in": 0.25, "out": 2.00}),
    (("gpt-5",), {"in": 1.25, "out": 10.00}),
    (("gpt-4o", "mini"), {"in": 0.15, "out": 0.60}),
    (("gpt-4o",), {"in": 2.50, "out": 10.00}),
    (("gpt-4.1", "nano"), {"in": 0.10, "out": 0.40}),
    (("gpt-4.1", "mini"), {"in": 0.40, "out": 1.60}),
    (("gpt-4.1",), {"in": 2.00, "out": 8.00}),
    (("gpt-4", "turbo"), {"in": 10.00, "out": 30.00}),
    (("gpt-3.5",), {"in": 0.50, "out": 1.50}),
    (("o3", "mini"), {"in": 1.10, "out": 4.40}),
    (("claude", "fable"), {"in": 10.00, "out": 50.00}),
    (("claude", "mythos"), {"in": 10.00, "out": 50.00}),
    (("claude", "haiku"), {"in": 1.00, "out": 5.00}),     # Haiku 4.5 current rate
    (("claude", "sonnet"), {"in": 3.00, "out": 15.00}),   # Sonnet standard (post-intro)
    (("claude", "opus"), {"in": 5.00, "out": 25.00}),     # Opus 4.5+ current rate
    (("gemini", "flash", "lite"), {"in": 0.10, "out": 0.40}),
    (("gemini", "flash"), {"in": 0.30, "out": 2.50}),
    (("gemini", "pro"), {"in": 1.25, "out": 10.00}),
    (("mistral", "large"), {"in": 0.50, "out": 1.50}),
    (("mistral", "medium"), {"in": 1.50, "out": 7.50}),
    (("mistral", "small"), {"in": 0.15, "out": 0.60}),
    (("ministral",), {"in": 0.15, "out": 0.15}),
    (("codestral",), {"in": 0.30, "out": 0.90}),
    # Hosted Llama/Gemma/Mixtral (e.g. Groq). Local Ollama tags (with a ":") are
    # matched as free earlier in price_for, so these only catch hosted names.
    (("llama",), {"in": 0.10, "out": 0.20}),
    (("gemma",), {"in": 0.20, "out": 0.20}),
    (("mixtral",), {"in": 0.24, "out": 0.24}),
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


def current():
    """The recorder bound to the current thread, or None. Capture this on a job
    thread and re-bind() it inside worker-pool child threads so their token
    counts are attributed to the parent job (see workers in testgen / sheet import)."""
    return getattr(_local, "rec", None)


def bind(rec):
    """Bind an existing recorder to the current thread (used by pool workers to
    inherit the parent job's recorder). No-op for None."""
    if rec is not None:
        _local.rec = rec


def record(model, prompt_tokens=0, completion_tokens=0, kind="llm", estimated=False):
    """Add one call's token counts to the current thread's recorder (no-op if
    no recorder is bound, e.g. calls made outside a tracked job)."""
    rec = getattr(_local, "rec", None)
    if rec is None:
        return
    key = model or "unknown"
    # Lock: the recorder may be shared across pool worker threads via bind().
    with _lock:
        m = rec.setdefault(key, {"calls": 0, "prompt_tokens": 0,
                                 "completion_tokens": 0, "kind": kind, "estimated": False})
        m["calls"] += 1
        m["prompt_tokens"] += int(prompt_tokens or 0)
        m["completion_tokens"] += int(completion_tokens or 0)
        if estimated:
            m["estimated"] = True
        if kind == "llm":            # llm wins over embedding if a model is used for both
            m["kind"] = "llm"


# Markers of a cloud-hosted model id (AWS Bedrock and similar). These embed a
# "provider." segment — optionally behind a region prefix (us.anthropic.…) or an
# inference-profile ARN — and their version suffix ends in ":0". That trailing ":0"
# must NOT be mistaken for a local Ollama tag, or paid Bedrock usage is priced as free.
_HOSTED_ID_MARKERS = ("anthropic.", "amazon.", "meta.", "cohere.", "mistral.",
                      "ai21.", "deepseek.", "arn:")


def price_for(model, prices):
    """Resolve a model's price entry. Order: exact → user/default substring →
    local Ollama tag (free) → model-family fallback. The family fallback also prices
    AWS Bedrock ids such as 'anthropic.claude-sonnet-4-20250514-v1:0' (→ Claude/sonnet).
    Returns None if nothing fits."""
    if not model:
        return None
    if model in prices:                     # exact (incl. Settings overrides)
        return prices[model]
    low = model.lower()
    for k, v in prices.items():             # case-insensitive substring either way
        kl = k.lower()
        if kl == low or kl in low or low in kl:
            return v
    # Ollama-style tag (e.g. qwen2.5:7b) → local/free. Guarded so a Bedrock id's
    # "-v1:0" suffix isn't treated as free — those carry a hosted provider marker and
    # instead fall through to the family fallback below (Bedrock Claude → Claude price).
    if ":" in low and not any(h in low for h in _HOSTED_ID_MARKERS):
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
