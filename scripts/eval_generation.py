#!/usr/bin/env python3
"""Generation-quality evaluation runner (issue #43, first slice).

Runs the REAL generate_fresh_testcases_pipeline() on a fixed corpus (examples/sample-prd.md)
with an explicitly chosen local model, and records what the pipeline itself reports about
quality, plus timing and token usage. It is the measurement foundation for model guidance;
it does not recommend a model and says nothing about documents other than the one it runs.

HOW IT DIFFERS FROM scripts/eval_rag_live.py
  * It never touches your wardenIQ Settings or your normal database. It builds its own
    Store, LLM and Embedder from command-line options, and refuses to run if the app's
    live-state modules (core.state / core.deps) were imported.
  * Every repeat gets its own throwaway database, named wardeniq_eval_*, dropped afterwards.
    It only ever creates/drops databases with that prefix.
  * The corpus is fixed, the model is explicit, and a seed is sent to Ollama.

REQUIREMENTS
  * Ollama reachable, with the model and the embedding model ALREADY pulled. The runner
    never downloads anything.
  * A MongoDB you do not mind it creating throwaway databases on, passed with --mongo-uri or
    EVAL_MONGO_URI. There is deliberately no default. A disposable one:
        docker run -d --rm --name wardeniq-eval-mongo -p 127.0.0.1:27099:27017 mongo:7
        --mongo-uri 'mongodb://127.0.0.1:27099/?directConnection=true'
    A plain mongod has no mongot, so retrieval uses the app's exact numpy fallback rather
    than the bundled stack's vector search.

EXAMPLE
    python scripts/eval_generation.py --model qwen2.5:3b --repeats 3 \\
        --mongo-uri 'mongodb://127.0.0.1:27099/?directConnection=true' \\
        --out docs/eval-results/generation-qwen2.5-3b.json

Only local Ollama is supported in this first slice. No API keys are read or written.
Exit status: 0 all repeats ran, 1 at least one repeat failed (output is still written),
2 bad options or a failed pre-flight check (nothing was run).
"""
import argparse
import contextlib
import json
import os
import platform
import re
import secrets
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT), str(ROOT / "app")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import httpx  # noqa: E402
import llm as llm_module  # noqa: E402
import testgen.service as svc  # noqa: E402
import usage  # noqa: E402
from embeddings import Embedder  # noqa: E402
from extract import chunk as chunk_doc  # noqa: E402
from tests.eval import generation_fixture as fixture  # noqa: E402
from tests.eval import generation_metrics as metrics  # noqa: E402

SCHEMA_VERSION = 1
DB_PREFIX = "wardeniq_eval_"
ALLOWED_PROVIDERS = ("ollama",)
LIVE_STATE_MODULES = ("core.state", "core.deps", "main")
PIPELINE_KEYS = ("cases_new", "cases_reused", "steps_new", "steps_reused", "by_type",
                 "discovered_api_count", "rag_gap_count", "errors", "warnings",
                 "evidence_insufficient")


class EvalError(Exception):
    """A problem with the options or environment (not a model/pipeline failure)."""


class EvalConfig:
    def __init__(self, *, model, mongo_uri, provider="ollama", ollama_url="http://localhost:11434",
                 embed_model="nomic-embed-text", embed_dim=768, repeats=1, seed=42, total=16,
                 note=""):
        self.provider = provider
        self.model = model
        self.mongo_uri = mongo_uri
        self.ollama_url = ollama_url
        self.embed_model = embed_model
        self.embed_dim = embed_dim
        self.repeats = repeats
        self.seed = seed
        self.total = total
        self.note = note

    def seed_for(self, repeat: int) -> int:
        return self.seed + (repeat - 1)


# --------------------------------------------------------------------------- safety
def assert_isolated():
    """The runner must never share process state with a live wardenIQ app."""
    loaded = [m for m in LIVE_STATE_MODULES if m in sys.modules]
    if loaded:
        raise EvalError(
            "refusing to run: live application state is loaded (" + ", ".join(loaded) + "). "
            "This runner must not share a process with the app's settings or database.")


def redact_argv(argv):
    """argv with the MongoDB URI (which may embed credentials) removed."""
    out, skip = [], False
    for token in argv:
        if skip:
            out.append("<redacted>")
            skip = False
        elif token == "--mongo-uri":
            out.append(token)
            skip = True
        elif token.startswith("--mongo-uri="):
            out.append("--mongo-uri=<redacted>")
        else:
            out.append(token)
    return out


def redact_text(text, cfg):
    """Remove the MongoDB URI and any credentials in it from free text (error messages)."""
    text = str(text)
    uri = cfg.mongo_uri or ""
    secrets_found = [uri] if uri else []
    userinfo = urlparse(uri).netloc.rpartition("@")[0] if "@" in uri else ""
    if userinfo:
        secrets_found.append(userinfo)
        secrets_found.extend(p for p in userinfo.split(":") if p)
    for secret in sorted(set(secrets_found), key=len, reverse=True):
        text = text.replace(secret, "<redacted>")
    return text


def safe_error(exc, cfg):
    return redact_text(f"{type(exc).__name__}: {exc}", cfg)[:500]


def new_database_name(repeat: int) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    return f"{DB_PREFIX}{stamp}_{secrets.token_hex(3)}_r{repeat}"


def drop_database(store, name: str):
    """Drop a benchmark database. Refuses anything that is not a wardeniq_eval_* name."""
    if not name.startswith(DB_PREFIX):
        raise EvalError(f"refusing to drop database {name!r}: not a {DB_PREFIX}* database")
    store.client.drop_database(name)


# --------------------------------------------------------------------------- model client
class RecordingLLM(llm_module.LLM):
    """The real LLM client, with every call timed. Behaviour is otherwise unchanged."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.calls = []
        self._calls_lock = threading.Lock()

    def _raw_chat(self, system, user, *args, **kwargs):
        started = time.perf_counter()
        ok, text = True, ""
        try:
            text = super()._raw_chat(system, user, *args, **kwargs)
            return text
        except Exception:
            ok = False
            raise
        finally:
            record = {"label": task_label(user),
                      "seconds": round(time.perf_counter() - started, 3),
                      "prompt_chars": len(system or "") + len(user or ""),
                      "response_chars": len(text or ""), "ok": ok}
            with self._calls_lock:
                self.calls.append(record)


def task_label(prompt: str) -> str:
    """The pipeline prompts open with a 'TASK: ...' line; use it to group calls."""
    match = re.search(r"TASK:\s*([^\n]{1,80})", prompt or "")
    return match.group(1).strip() if match else "other"


class _HttpxWithSeed:
    """Stands in for the `httpx` name inside llm.py only: adds a fixed `seed` to Ollama chat
    requests so a run is repeatable where Ollama allows it. Everything else passes through."""

    def __init__(self, real, seed):
        self._real = real
        self._seed = seed

    def post(self, url, *args, **kwargs):
        body = kwargs.get("json")
        if str(url).endswith("/api/chat") and isinstance(body, dict):
            options = dict(body.get("options") or {})
            options.setdefault("seed", self._seed)
            kwargs = {**kwargs, "json": {**body, "options": options}}
        return self._real.post(url, *args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._real, name)


@contextlib.contextmanager
def seeded_ollama(seed):
    real = llm_module.httpx
    llm_module.httpx = _HttpxWithSeed(real, seed)
    try:
        yield
    finally:
        llm_module.httpx = real


@contextlib.contextmanager
def capture_requirement_gaps(sink):
    """Record what the pipeline's own gap check returned, without changing it."""
    original = svc._requirement_gaps

    def wrapped(raw_text, suites):
        result = original(raw_text, suites)
        sink.append(result)
        return result

    svc._requirement_gaps = wrapped
    try:
        yield
    finally:
        svc._requirement_gaps = original


# --------------------------------------------------------------------------- ingest
def summary_prompt(name: str, raw: str) -> str:
    """Mirrors core.deps._generate_feature_summary (kept in step by a test)."""
    return f"""
Create a clean feature summary for a QA workspace.

Rules:
- 2 to 3 concise sentences.
- Describe product/user behavior, not document filenames.
- Do not mention PRD, HLD, LLD, source document, uploaded file, or markdown headings.
- Do not include test-case counts.
- Return JSON only: {{"summary": "..."}}

Feature name: {name}

Evidence:
{(raw or '')[:6000]}
""".strip()


def build_summary(llm, name: str, raw: str):
    """(summary, source). The app writes this summary with the SAME model at ingest time,
    so it is part of what a model's first run looks like; `source` records a fallback."""
    try:
        data = llm.chat_json("You write concise feature summaries for QA managers.",
                             summary_prompt(name, raw), temperature=0.1)
        summary = " ".join(str((data or {}).get("summary") or "").split()).strip()
        if len(summary) >= 40:
            return summary[:700], "model"
    except Exception:  # noqa: BLE001
        pass
    return name, "fallback"


def ingest_feature(store, embedder, llm, project_id, name, text, source_name):
    """Create the feature and its chunks the way the app's create-feature route does."""
    summary, source = build_summary(llm, name, text)
    embedding = embedder.embed(text[:2000])
    fid = store.create_feature(name, project_id, [source_name], text, summary, embedding)
    chunks = [{"source": source_name, "chunk_index": i, "text": piece,
               "embedding": embedder.embed(piece)}
              for i, piece in enumerate(chunk_doc(text, max_chars=1200, overlap=150))]
    store.add_feature_chunks(fid, project_id, chunks)
    return fid, summary, source, len(chunks)


# --------------------------------------------------------------------------- one repeat
def run_repeat(cfg, repeat, corpus_text, *, store_factory, llm_factory, embedder,
               pipeline_fn=None, clock=time.perf_counter):
    """One isolated run: fresh database, ingest, real pipeline, collect, drop the database."""
    assert_isolated()
    pipeline_fn = pipeline_fn or svc.generate_fresh_testcases_pipeline
    db_name = new_database_name(repeat)
    seed = cfg.seed_for(repeat)
    run = {"repeat": repeat, "seed": seed, "database": db_name, "ok": False, "error": None}
    store = None
    try:
        store = store_factory(db_name)
        if getattr(getattr(store, "db", None), "name", db_name) != db_name:
            raise EvalError("isolation check failed: the store is not bound to the benchmark database")
        llm = llm_factory()
        usage.start()
        marks, gap_sink = [], []

        def on_progress(stage, progress=None):
            marks.append((clock(), str(stage), progress))

        with seeded_ollama(seed):
            started = clock()
            project_id = store.create_project("generation-eval")
            fid, summary, summary_source, n_chunks = ingest_feature(
                store, embedder, llm, project_id, fixture.FEATURE_NAME, corpus_text,
                Path(fixture.CORPUS_PATH).name)
            ingest_done = clock()
            calls_before = len(getattr(llm, "calls", []))
            with capture_requirement_gaps(gap_sink):
                out = pipeline_fn(store=store, llm=llm, embedder=embedder,
                                  params={"feature_id": fid, "total": cfg.total, "focus": None,
                                          "smoke_mode": False},
                                  update_job_fn=on_progress)
            finished = clock()

        cases = store.get_feature_cases(fid)
        gaps = gap_sink[-1] if gap_sink else None
        calls = list(getattr(llm, "calls", []))
        pipeline_calls = calls[calls_before:]
        stages = metrics.stage_durations(marks, finished)
        by_label = {}
        for call in pipeline_calls:
            by_label.setdefault(call["label"], []).append(call)
        run.update({
            "ok": True,
            "timings": {"ingest_seconds": round(ingest_done - started, 3),
                        "pipeline_seconds": round(finished - ingest_done, 3),
                        "total_seconds": round(finished - started, 3)},
            "ingest": {"summary_source": summary_source, "summary_chars": len(summary),
                       "summary": summary, "chunks": n_chunks,
                       "llm_calls": metrics.llm_call_summary(calls[:calls_before])},
            "pipeline": {k: out.get(k) for k in PIPELINE_KEYS if k in out},
            "filter": metrics.summarize_filter(out.get("testgen_filter")),
            "requirement_gaps": (None if gaps is None else
                                 {"count": len(gaps),
                                  "items": [g.get("requirement") for g in gaps
                                            if isinstance(g, dict)]}),
            "requirement_coverage": metrics.requirement_coverage(
                fixture.REQUIREMENTS, [metrics.case_text(c) for c in cases]),
            "persisted_cases": [{"type": c.get("type"), "title": c.get("title")} for c in cases],
            "stages": stages,
            "grounding_survivors": metrics.parse_grounding_survivors(stages),
            "llm_calls": {**metrics.llm_call_summary(pipeline_calls),
                          "by_task": {label: metrics.llm_call_summary(items)
                                      for label, items in sorted(by_label.items())}},
            "usage": usage.summarize(usage.current()),
            "search_degraded": getattr(store, "search_degraded", lambda: {})() or {},
        })
    except Exception as exc:  # noqa: BLE001
        run["error"] = safe_error(exc, cfg)
    finally:
        usage.stop()
        if store is not None:
            try:
                drop_database(store, db_name)
            except Exception as exc:  # noqa: BLE001
                run["cleanup_error"] = safe_error(exc, cfg)
    return run


# --------------------------------------------------------------------------- environment
def _sh(cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=5,
                              cwd=str(ROOT)).stdout.strip() or None
    except Exception:  # noqa: BLE001
        return None


def hardware_info():
    info = {"platform": platform.platform(), "machine": platform.machine(),
            "python": platform.python_version(), "cpu_count": os.cpu_count()}
    if sys.platform == "darwin":
        info["cpu"] = _sh(["sysctl", "-n", "machdep.cpu.brand_string"])
        mem = _sh(["sysctl", "-n", "hw.memsize"])
        info["ram_gb"] = round(int(mem) / 1024 ** 3, 1) if mem and mem.isdigit() else None
    else:
        try:
            cpu = next((line.split(":", 1)[1].strip() for line in open("/proc/cpuinfo")
                        if line.startswith("model name")), None)
            info["cpu"] = cpu
            info["ram_gb"] = round(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
                                   / 1024 ** 3, 1)
        except Exception:  # noqa: BLE001
            info["cpu"], info["ram_gb"] = None, None
    return info


def git_info():
    sha = _sh(["git", "rev-parse", "HEAD"])
    dirty = _sh(["git", "status", "--porcelain", "--untracked-files=no"])
    return {"sha": sha, "dirty": bool(dirty) if sha else None}


def _digest(entry):
    return (entry.get("digest") or "")[:12] or None


def preflight_ollama(cfg):
    """Check the models are already installed. Returns ({model: digest12}, ollama_version)."""
    base = cfg.ollama_url.rstrip("/")
    try:
        tags = httpx.get(f"{base}/api/tags", timeout=10.0)
        tags.raise_for_status()
        installed = {m.get("name"): m for m in tags.json().get("models", [])}
    except Exception as exc:  # noqa: BLE001
        raise EvalError(f"cannot reach Ollama at {urlparse(base).netloc or base}: "
                        f"{type(exc).__name__}") from None
    digests = {}
    for wanted in (cfg.model, cfg.embed_model):
        entry = installed.get(wanted) or installed.get(f"{wanted}:latest")
        if entry is None:
            raise EvalError(f"model {wanted!r} is not installed in Ollama. This tool never "
                            f"downloads models; pull it yourself first: ollama pull {wanted}")
        digests[wanted] = _digest(entry)
    try:
        version = httpx.get(f"{base}/api/version", timeout=5.0).json().get("version")
    except Exception:  # noqa: BLE001
        version = None
    return digests, version


def preflight_mongo(cfg):
    from pymongo import MongoClient
    try:
        client = MongoClient(cfg.mongo_uri, serverSelectionTimeoutMS=5000)
        info = client.server_info()
        client.close()
        return info.get("version")
    except Exception as exc:  # noqa: BLE001
        raise EvalError("cannot reach MongoDB: " + safe_error(exc, cfg)) from None


def build_meta(cfg, *, argv, corpus_bytes, digests, ollama_version, mongo_version, note=None):
    ollama_host = urlparse(cfg.ollama_url).hostname
    return {
        "tool": "scripts/eval_generation.py",
        "schema_version": SCHEMA_VERSION,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "command": "python scripts/eval_generation.py " + " ".join(redact_argv(argv)),
        "git": git_info(),
        "provider": cfg.provider,
        "model": cfg.model,
        "model_digest": (digests or {}).get(cfg.model),
        "embed_model": cfg.embed_model,
        "embed_model_digest": (digests or {}).get(cfg.embed_model),
        "embed_dim": cfg.embed_dim,
        "corpus": {"path": fixture.CORPUS_PATH, "sha256": metrics.corpus_hash(corpus_bytes),
                   "bytes": len(corpus_bytes), "feature_name": fixture.FEATURE_NAME},
        "fixture_sha256": fixture.fixture_hash(),
        "run_parameters": {"repeats": cfg.repeats, "seed_base": cfg.seed,
                           "seed_rule": "seed_base + repeat - 1", "total": cfg.total,
                           "num_ctx_cap": llm_module.OLLAMA_MAX_NUM_CTX},
        "hardware": hardware_info(),
        "runtime": {"ollama_version": ollama_version, "ollama_host": ollama_host,
                    "mongo_version": mongo_version, "note": note or cfg.note or None},
    }


# --------------------------------------------------------------------------- entry point
def build_payload(cfg, runs, **meta_kwargs):
    return {"meta": build_meta(cfg, **meta_kwargs), "runs": runs,
            "aggregate": metrics.aggregate_repeats(runs)}


def parse_args(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--provider", default="ollama", choices=ALLOWED_PROVIDERS,
                    help="local Ollama only in this first slice")
    ap.add_argument("--model", required=True, help="model tag, e.g. qwen2.5:3b (must be pulled)")
    ap.add_argument("--ollama-url", default="http://localhost:11434")
    ap.add_argument("--embed-model", default="nomic-embed-text")
    ap.add_argument("--embed-dim", type=int, default=768)
    ap.add_argument("--repeats", type=int, default=1)
    ap.add_argument("--seed", type=int, default=42, help="base seed; repeat N uses seed + N - 1")
    ap.add_argument("--total", type=int, default=16, help="cases to request (app default 16)")
    ap.add_argument("--mongo-uri", default=os.getenv("EVAL_MONGO_URI", ""),
                    help="a MongoDB it may create throwaway wardeniq_eval_* databases on "
                         "(or set EVAL_MONGO_URI); never printed or written to results")
    ap.add_argument("--out", default="", help="write the JSON result here")
    ap.add_argument("--note", default="", help="free text recorded with the run, e.g. the "
                    "runtime ('Ollama in Docker, 8 GB VM, CPU-only')")
    args = ap.parse_args(argv)
    if args.repeats < 1:
        ap.error("--repeats must be at least 1")
    if not args.mongo_uri:
        ap.error("--mongo-uri (or EVAL_MONGO_URI) is required; there is intentionally no default")
    return args


def main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    args = parse_args(argv)
    cfg = EvalConfig(model=args.model, mongo_uri=args.mongo_uri, provider=args.provider,
                     ollama_url=args.ollama_url, embed_model=args.embed_model,
                     embed_dim=args.embed_dim, repeats=args.repeats, seed=args.seed,
                     total=args.total, note=args.note)
    try:
        assert_isolated()
        digests, ollama_version = preflight_ollama(cfg)
        mongo_version = preflight_mongo(cfg)
    except EvalError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    from store import Store
    corpus_path = ROOT / fixture.CORPUS_PATH
    corpus_bytes = corpus_path.read_bytes()
    corpus_text = corpus_bytes.decode("utf-8")
    embedder = Embedder(provider="ollama", model=cfg.embed_model, dim=cfg.embed_dim,
                        ollama_url=cfg.ollama_url)

    def store_factory(db_name):
        return Store(cfg.mongo_uri, db_name, cfg.embed_dim)

    def llm_factory():
        return RecordingLLM(provider=cfg.provider, model=cfg.model, ollama_url=cfg.ollama_url)

    runs = []
    for repeat in range(1, cfg.repeats + 1):
        print(f"[eval] repeat {repeat}/{cfg.repeats}  model={cfg.model}  seed={cfg.seed_for(repeat)}",
              flush=True)
        run = run_repeat(cfg, repeat, corpus_text, store_factory=store_factory,
                         llm_factory=llm_factory, embedder=embedder)
        runs.append(run)
        print("[eval]   " + summarize_run_line(run), flush=True)

    payload = build_payload(cfg, runs, argv=argv, corpus_bytes=corpus_bytes, digests=digests,
                            ollama_version=ollama_version, mongo_version=mongo_version)
    text = json.dumps(payload, indent=2, default=str) + "\n"
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text, encoding="utf-8")
        print(f"[eval] wrote {out_path}", flush=True)
    else:
        print(text)
    return 0 if all(r.get("ok") for r in runs) else 1


def summarize_run_line(run):
    if not run.get("ok"):
        return f"FAILED: {run.get('error')}"
    flt = run.get("filter") or {}
    timings = run.get("timings") or {}
    if not flt.get("available"):
        return f"ok, filter stats unavailable, {timings.get('total_seconds')}s"
    ex = flt["reasons"]["exemplar-copy"]
    return (f"ok  generated={flt['generated']} persisted={flt['persisted']} "
            f"rejected={flt['rejected']} exemplar-copy={ex['count']} "
            f"time={timings.get('total_seconds')}s")


if __name__ == "__main__":
    sys.exit(main())
