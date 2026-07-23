"""Pluggable LLM client — local Ollama or a hosted provider (OpenAI / Anthropic /
Mistral / any OpenAI-compatible endpoint). One `chat_json` entrypoint; the rest of
the app never cares which provider is configured.
"""
import json
import httpx

import usage
from prompts import SYSTEM, build_prompt, TYPE_GUIDANCE

TEST_TYPES = list(TYPE_GUIDANCE.keys())  # functional, e2e, api, nfr

DEFAULT_BASE = {
    "openai": "https://api.openai.com",
    "mistral": "https://api.mistral.ai",
    "anthropic": "https://api.anthropic.com",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai",
    # Groq is OpenAI-compatible and very fast (free tier available). It uses the same
    # /v1/chat/completions path as the openai branch below, so no special handling.
    "groq": "https://api.groq.com/openai",
}


# Models that reject an explicit `temperature` (GPT-5 / o-series and similar only
# allow the provider default). Learned at runtime on the first rejection, then
# reused so we never waste a second call on the same model in this process.
_NO_CUSTOM_TEMPERATURE: set[str] = set()


def _friendly_model_error(provider: str, model: str, r) -> RuntimeError:
    """Turn a hosted-provider 400/404 into an actionable message about the model
    id (the usual cause when a custom/typed model doesn't exist for the account),
    surfacing the provider's own error text."""
    detail = ""
    try:
        j = r.json()
        detail = (j.get("error") or {}).get("message") or j.get("message") or ""
    except Exception:  # noqa: BLE001
        detail = (r.text or "").strip()[:200]
    msg = (f"model '{model}' was rejected by {provider} (HTTP {r.status_code}) — "
           f"check the exact model id exists and your API key has access to it.")
    return RuntimeError(f"{msg} Provider said: {detail}" if detail else msg)


class LLM:
    def __init__(self, provider="ollama", model="qwen2.5:7b", api_key="",
                 base_url="", ollama_url="http://localhost:11434", region=""):
        self.provider = provider or "ollama"
        self.model = model
        self.api_key = (api_key or "").strip()
        self.ollama_url = (ollama_url or "http://localhost:11434").strip().rstrip("/")
        self.base_url = (base_url or DEFAULT_BASE.get(self.provider, "")).strip().rstrip("/")
        # AWS region for Bedrock (ignored by every other provider).
        self.region = (region or "").strip()

    # ---- AWS Bedrock helpers -------------------------------------------------
    def _aws_creds(self) -> tuple[str, str, str]:
        """Bedrock's credential field is the unified `api_key`, holding
        `accessKeyId:secretAccessKey` (optionally `:sessionToken`). Blank means
        "use the default AWS credential chain" — env vars, ~/.aws, or the machine's
        IAM role (the recommended path for an air-gapped deployment)."""
        raw = self.api_key or ""
        if ":" in raw:
            parts = [p.strip() for p in raw.split(":")]
            return parts[0], parts[1], (parts[2] if len(parts) > 2 else "")
        return "", "", ""

    def _bedrock_client(self):
        import boto3  # lazy — only needed when Bedrock is selected
        ak, sk, tok = self._aws_creds()
        kw = {"region_name": self.region or None}
        if ak and sk:
            kw["aws_access_key_id"] = ak
            kw["aws_secret_access_key"] = sk
            if tok:
                kw["aws_session_token"] = tok
        session = boto3.session.Session(**kw)
        # base_url doubles as an optional private VPC/PrivateLink endpoint.
        return session.client("bedrock-runtime", endpoint_url=(self.base_url or None))

    def _bedrock_chat(self, system, user, temperature, max_tokens) -> str:
        # Converse is model-agnostic across Claude / Llama / Mistral / Titan / Nova,
        # so switching Bedrock models needs no code change.
        client = self._bedrock_client()
        resp = client.converse(
            modelId=self.model,
            system=[{"text": system + " Respond with a single JSON object only."}],
            messages=[{"role": "user", "content": [{"text": user}]}],
            inferenceConfig={"temperature": temperature, "maxTokens": max_tokens},
        )
        u = resp.get("usage") or {}
        usage.record(self.model, u.get("inputTokens", 0), u.get("outputTokens", 0), kind="llm")
        parts = (resp.get("output", {}).get("message", {}) or {}).get("content", []) or []
        return "".join(p.get("text", "") for p in parts if isinstance(p, dict))

    def _ollama_headers(self) -> dict:
        """Optional bearer auth for a SECURED/remote Ollama (e.g. one behind a reverse
        proxy or a hosted endpoint). Plain local Ollama needs none, so this is empty
        unless an API key/token is configured."""
        return {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}

    # ---- unified JSON chat ---------------------------------------------------
    def chat_json(self, system: str, user: str, num_ctx: int = 8192,
                  temperature: float = 0.2, max_tokens: int = 4000, retries: int = 1) -> dict:
        last = None
        for _ in range(retries + 1):
            try:
                content = self._raw_chat(system, user, num_ctx, temperature, max_tokens)
                return json.loads(_extract_json(content))
            except json.JSONDecodeError as e:
                last = e  # malformed → retry once
            except Exception as e:  # noqa: BLE001
                raise RuntimeError(f"LLM request failed ({self.provider}): {e}") from e
        raise RuntimeError(f"LLM returned unparseable JSON ({self.provider}): {last}")

    def _raw_chat(self, system, user, num_ctx, temperature, max_tokens,
                  timeout_seconds: float | None = None) -> str:
        if self.provider == "bedrock":
            return self._bedrock_chat(system, user, temperature, max_tokens)
        if self.provider == "ollama":
            # Cap num_ctx for local Ollama at 8192 to prevent memory thrashing/crashes on CPU
            ollama_ctx = min(num_ctx or 8192, 8192)
            r = httpx.post(f"{self.ollama_url}/api/chat",
                           timeout=timeout_seconds or 300.0,
                           headers=self._ollama_headers(), json={
                "model": self.model, "stream": False, "format": "json",
                "messages": [{"role": "system", "content": system},
                             {"role": "user", "content": user}],
                "options": {"temperature": temperature, "num_ctx": ollama_ctx}})
            # Ollama answers 404 when the model isn't pulled yet — turn that into an
            # actionable instruction instead of a bare HTTP error.
            if r.status_code == 404:
                raise RuntimeError(
                    f"the model '{self.model}' isn't downloaded in Ollama yet. Download it with: "
                    f"docker compose exec ollama ollama pull {self.model}  — or pick a model that's "
                    f"already installed (see: docker compose exec ollama ollama list).")
            r.raise_for_status()
            data = r.json()
            usage.record(self.model, data.get("prompt_eval_count", 0),
                         data.get("eval_count", 0), kind="llm")
            # Ollama can return "content": null (e.g. an empty/truncated generation)
            # instead of "" — normalize so every caller can rely on a plain string
            # ("" meaning "no content") regardless of which provider answered.
            return (data.get("message") or {}).get("content") or ""
        if self.provider == "anthropic":
            r = httpx.post(f"{self.base_url}/v1/messages",
                           timeout=timeout_seconds or 120.0,
                           headers={"x-api-key": self.api_key,
                                    "anthropic-version": "2023-06-01",
                                    "content-type": "application/json"},
                           json={"model": self.model, "max_tokens": max_tokens,
                                 "system": system + " Respond with a single JSON object only.",
                                 "messages": [{"role": "user", "content": user}]})
            if r.status_code in (400, 404):
                raise _friendly_model_error(self.provider, self.model, r)
            r.raise_for_status()
            data = r.json()
            u = data.get("usage") or {}
            usage.record(self.model, u.get("input_tokens", 0),
                         u.get("output_tokens", 0), kind="llm")
            return "".join(b.get("text", "") for b in data.get("content", []))
        # openai / mistral / any OpenAI-compatible / gemini
        if self.provider == "gemini":
            url = f"{self.base_url}/chat/completions"
        else:
            url = f"{self.base_url}/v1/chat/completions"
        headers = {"Authorization": f"Bearer {self.api_key}",
                   "Content-Type": "application/json"}
        payload = {"model": self.model,
                   "response_format": {"type": "json_object"},
                   "messages": [{"role": "system", "content": system},
                                {"role": "user", "content": user}]}
        # Only send an explicit temperature to models that accept one. Newer models
        # (GPT-5 / o-series) allow just the provider default and 400 on any value;
        # once we've seen that for a model we stop sending it (no wasted retries).
        if self.model not in _NO_CUSTOM_TEMPERATURE:
            payload["temperature"] = temperature
        r = httpx.post(url, timeout=timeout_seconds or 120.0, headers=headers, json=payload)
        # First time a model rejects the temperature: remember it, drop the param,
        # and retry once. Subsequent calls skip temperature upfront.
        if r.status_code == 400 and "temperature" in (r.text or "").lower():
            _NO_CUSTOM_TEMPERATURE.add(self.model)
            payload.pop("temperature", None)
            r = httpx.post(url, timeout=timeout_seconds or 120.0, headers=headers, json=payload)
        if r.status_code in (400, 404):
            raise _friendly_model_error(self.provider, self.model, r)
        r.raise_for_status()
        data = r.json()
        u = data.get("usage") or {}
        usage.record(self.model, u.get("prompt_tokens", 0),
                     u.get("completion_tokens", 0), kind="llm")
        # OpenAI-compatible providers (OpenAI / Mistral / Groq / Gemini) can return
        # "content": null (refusals, tool-call-only replies, content filtering) or
        # even an empty "choices" list. Normalize to "" instead of raising
        # IndexError/None so callers get the same "no content" signal for every
        # provider, matching the Ollama/Anthropic/Bedrock branches above.
        choices = data.get("choices") or []
        if not choices:
            return ""
        message = choices[0].get("message") or {}
        return message.get("content") or ""

    # ---- test-case generation -----------------------------------------------
    def generate_testcases(self, test_type: str, requirement_text: str, target: int | None = None) -> list[dict]:
        data = self.chat_json(SYSTEM, build_prompt(test_type, requirement_text, target))
        cases = data.get("test_cases", []) if isinstance(data, dict) else []
        return [self._normalize(c, test_type) for c in cases if isinstance(c, dict)]

    @staticmethod
    def _normalize(case: dict, test_type: str) -> dict:
        steps = []
        for s in case.get("steps", []):
            if isinstance(s, dict) and (s.get("action") or s.get("expected")):
                steps.append({"action": str(s.get("action", "")).strip(),
                              "expected": str(s.get("expected", "")).strip()})
        return {
            "title": str(case.get("title", "Untitled")).strip(),
            "type": test_type,
            "priority": str(case.get("priority", "P2")).strip() or "P2",
            "preconditions": str(case.get("preconditions", "")).strip(),
            "tags": [str(t).strip().lower() for t in case.get("tags", []) if str(t).strip()],
            "steps": steps,
        }

    def health(self) -> dict:
        if self.provider == "ollama":
            try:
                r = httpx.get(f"{self.ollama_url}/api/tags", timeout=10.0)
                r.raise_for_status()
                models = [m.get("name", "") for m in r.json().get("models", [])]
                return {"ok": any(self.model.split(":")[0] in m for m in models),
                        "provider": "ollama", "models": models}
            except Exception as e:  # noqa: BLE001
                return {"ok": False, "provider": "ollama", "error": str(e)}
        if self.provider == "bedrock":
            # Config-state check (no free ping): a model + region is the minimum;
            # credentials may come from the IAM role, so we don't require api_key.
            return {"ok": bool(self.model and self.region), "provider": "bedrock"}
        # hosted: we can't cheaply ping without spending a call; report config state
        return {"ok": bool(self.api_key and self.model), "provider": self.provider}

    def ping(self) -> dict:
        """Active check: do a tiny JSON round-trip (used by the 'test' button)."""
        d = self.chat_json("You are a health check. Respond with a valid JSON object.", 'Return {"ok": true} in JSON format.', num_ctx=512, max_tokens=50)
        out = {"ok": bool(d.get("ok", True)), "provider": self.provider, "model": self.model}
        # For Ollama, also report which models the reached instance has, so the UI can
        # confirm what it connected to (bundled container vs. a native install).
        if self.provider == "ollama":
            try:
                t = httpx.get(f"{self.ollama_url}/api/tags", timeout=10.0, headers=self._ollama_headers())
                t.raise_for_status()
                out["models"] = [m.get("name") for m in t.json().get("models", []) if m.get("name")]
            except Exception:  # noqa: BLE001
                pass
        return out


def _extract_json(text: str) -> str:
    """Hosted models sometimes wrap JSON in prose/fences; salvage the object."""
    t = (text or "").strip()
    if t.startswith("```"):
        t = t.strip("`")
        t = t[t.find("{"):] if "{" in t else t
    a, b = t.find("{"), t.rfind("}")
    return t[a:b + 1] if a != -1 and b != -1 and b > a else t
