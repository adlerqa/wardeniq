"""Pluggable embedding client — local Ollama or a hosted provider (OpenAI /
Google Gemini / Voyage / any OpenAI-compatible endpoint).

IMPORTANT: every embedding stored in a collection's vector index must share the
same dimension. Different models emit different dimensions (nomic 768, OpenAI
1536/3072, Voyage 1024/1536, Gemini 768/3072), so switching the model requires
rebuilding the vector indexes and re-embedding all stored vectors — see
store.rebuild_vector_indexes / store.reembed_all and the `reembed` job. This
client never mixes dimensions; it just produces vectors for the active model.
"""
import json

import httpx

import usage

DOC_PREFIX = "search_document: "
QUERY_PREFIX = "search_query: "

# Default API base per hosted provider (mirrors llm.DEFAULT_BASE).
DEFAULT_BASE = {
    "openai": "https://api.openai.com",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai",
    "voyage": "https://api.voyageai.com",
}


class Embedder:
    def __init__(self, provider: str = "ollama", model: str = "nomic-embed-text",
                 dim: int | None = None, api_key: str = "", base_url: str = "",
                 ollama_url: str = "http://localhost:11434", region: str = ""):
        self.provider = (provider or "ollama").strip()
        self.model = model
        # AWS region for Bedrock (ignored by every other provider).
        self.region = (region or "").strip()
        # `dim` is the OUTPUT dimension to request (OpenAI/Gemini support this). When
        # None we don't request one, so the model returns its NATIVE dimension — which
        # is what probe_dim() must measure at switch time. Forcing a default here would
        # silently downgrade e.g. gemini-embedding-001 from 3072-d to that default.
        self.dim = int(dim) if dim else None
        self.api_key = (api_key or "").strip()
        self.ollama_url = (ollama_url or "http://localhost:11434").strip().rstrip("/")
        self.base_url = (base_url or DEFAULT_BASE.get(self.provider, "")).strip().rstrip("/")

    def _ollama_headers(self) -> dict:
        """Optional bearer auth for a secured/remote Ollama (proxy or hosted endpoint).
        Empty for plain local Ollama."""
        return {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}

    def embed(self, text: str, task: str = "document") -> list[float]:
        if self.provider == "ollama":
            return self._embed_ollama(text, task)
        if self.provider == "bedrock":
            return self._embed_bedrock(text, task)
        if self.provider == "voyage":
            return self._embed_voyage(text, task)
        # openai / gemini / openai-compatible
        return self._embed_openai(text)

    # ---- AWS Bedrock ---------------------------------------------------------
    def _aws_creds(self) -> tuple[str, str, str]:
        """Same unified-credential convention as llm.LLM: `api_key` holds
        `accessKeyId:secretAccessKey[:sessionToken]`; blank = default AWS chain
        (env / ~/.aws / IAM role)."""
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
        return session.client("bedrock-runtime", endpoint_url=(self.base_url or None))

    def _embed_bedrock(self, text: str, task: str) -> list[float]:
        client = self._bedrock_client()
        model = self.model or ""
        if model.startswith("cohere."):
            body = {"texts": [text],
                    "input_type": "search_query" if task == "query" else "search_document"}
            resp = client.invoke_model(modelId=model, body=json.dumps(body))
            data = json.loads(resp["body"].read())
            usage.record(model, max(1, len(text) // 4), 0, kind="embedding", estimated=True)
            return data["embeddings"][0]
        # Amazon Titan (v1/v2). Titan v2 accepts an output dimension.
        body = {"inputText": text}
        if self.dim:
            body["dimensions"] = self.dim
        resp = client.invoke_model(modelId=model, body=json.dumps(body))
        data = json.loads(resp["body"].read())
        pt = data.get("inputTextTokenCount")
        usage.record(model, pt if pt is not None else max(1, len(text) // 4),
                     0, kind="embedding", estimated=pt is None)
        return data["embedding"]

    # ---- providers -----------------------------------------------------------
    def _embed_ollama(self, text: str, task: str) -> list[float]:
        payload = (QUERY_PREFIX if task == "query" else DOC_PREFIX) + text
        r = httpx.post(f"{self.ollama_url}/api/embeddings",
                       headers=self._ollama_headers(),
                       json={"model": self.model, "prompt": payload}, timeout=120.0)
        if r.status_code == 404:
            raise RuntimeError(
                f"the embedding model '{self.model}' isn't downloaded in Ollama yet. Download it with: "
                f"docker compose exec ollama ollama pull {self.model}")
        r.raise_for_status()
        data = r.json()
        pt = data.get("prompt_eval_count")
        estimated = pt is None
        if estimated:
            pt = max(1, len(payload) // 4)
        usage.record(self.model, pt, 0, kind="embedding", estimated=estimated)
        return data["embedding"]

    def _embed_openai(self, text: str) -> list[float]:
        # Gemini's OpenAI-compat base already includes /v1beta/openai, so it uses
        # `/embeddings`; standard OpenAI-style bases use `/v1/embeddings`.
        url = (f"{self.base_url}/embeddings" if self.provider == "gemini"
               else f"{self.base_url}/v1/embeddings")
        body = {"model": self.model, "input": text}
        # text-embedding-3 (and Gemini's compat endpoint) accept an output dimension.
        if self.provider in ("openai", "gemini") and self.dim:
            body["dimensions"] = self.dim
        r = httpx.post(url, timeout=120.0,
                       headers={"Authorization": f"Bearer {self.api_key}",
                                "Content-Type": "application/json"}, json=body)
        r.raise_for_status()
        data = r.json()
        u = data.get("usage") or {}
        usage.record(self.model, u.get("prompt_tokens", u.get("total_tokens", 0)),
                     0, kind="embedding")
        return data["data"][0]["embedding"]

    def _embed_voyage(self, text: str, task: str) -> list[float]:
        base = self.base_url or DEFAULT_BASE["voyage"]
        r = httpx.post(f"{base}/v1/embeddings", timeout=120.0,
                       headers={"Authorization": f"Bearer {self.api_key}",
                                "Content-Type": "application/json"},
                       json={"model": self.model, "input": [text],
                             "input_type": "query" if task == "query" else "document"})
        r.raise_for_status()
        data = r.json()
        u = data.get("usage") or {}
        usage.record(self.model, u.get("total_tokens", 0), 0, kind="embedding")
        return data["data"][0]["embedding"]

    # ---- helpers -------------------------------------------------------------
    def probe_dim(self) -> int:
        """Embed a tiny string to learn the model's true output dimension.
        This is authoritative — the vector index is built from what the model
        actually returns, not a guessed number."""
        return len(self.embed("dimension probe", task="query"))

    def ok(self) -> bool:
        if self.provider == "ollama":
            return True
        if self.provider == "bedrock":
            return bool(self.model and self.region)
        return bool(self.api_key and self.model)

    def health(self) -> dict:
        if self.provider == "ollama":
            try:
                r = httpx.get(f"{self.ollama_url}/api/tags", timeout=10.0, headers=self._ollama_headers())
                r.raise_for_status()
                models = [m.get("name", "") for m in r.json().get("models", [])]
                return {"ok": any(self.model in m for m in models),
                        "provider": "ollama", "models": models}
            except Exception as e:  # noqa: BLE001
                return {"ok": False, "provider": "ollama", "error": str(e)}
        if self.provider == "bedrock":
            return {"ok": bool(self.model and self.region), "provider": "bedrock"}
        return {"ok": bool(self.api_key and self.model), "provider": self.provider}
