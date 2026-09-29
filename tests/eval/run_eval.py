"""Score wardenIQ's coverage verdicts and dedup decisions against labelled ground truth.

    # grounding layer only — no model needed, runs in CI, must stay at 1.00
    python -m tests.eval.run_eval --probes

    # dedup thresholds against labelled pairs
    python -m tests.eval.run_eval --dedup

    # full coverage accuracy against a REAL model (needs a reachable LLM)
    python -m tests.eval.run_eval --coverage --provider ollama --model qwen2.5:7b

Exit code is non-zero when a scored section falls below its threshold, so this can gate
a prompt or model change in CI rather than being a thing someone remembers to run.
"""
import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone

# Allow `python -m tests.eval.run_eval` from the repo root with app/ on the path.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "app"))

import coverage as cov  # noqa: E402
from testgen.lineage import (  # noqa: E402
    derive_scenario_kind,
    generate_test_identity_hash,
    lineage_token_set,
    normalize_endpoint,
    scenario_kinds_incompatible,
    token_set_similarity,
)

from . import dataset  # noqa: E402

STATUSES = ("covered", "partial", "uncovered")


# --------------------------------------------------------------------------- scoring
def _confusion(pairs):
    """pairs = [(expected, actual)]. Returns per-status precision/recall + accuracy."""
    matrix = {e: {a: 0 for a in STATUSES} for e in STATUSES}
    for exp, act in pairs:
        if exp in matrix and act in matrix[exp]:
            matrix[exp][act] += 1
    total = sum(sum(r.values()) for r in matrix.values())
    correct = sum(matrix[s][s] for s in STATUSES)
    per_status = {}
    for s in STATUSES:
        tp = matrix[s][s]
        fn = sum(matrix[s][a] for a in STATUSES if a != s)
        fp = sum(matrix[e][s] for e in STATUSES if e != s)
        per_status[s] = {
            "support": tp + fn,
            "precision": round(tp / (tp + fp), 3) if (tp + fp) else None,
            "recall": round(tp / (tp + fn), 3) if (tp + fn) else None,
        }
    return {"accuracy": round(correct / total, 3) if total else None,
            "n": total, "matrix": matrix, "per_status": per_status}


def _overclaim_rate(pairs):
    """Fraction of cases called MORE covered than the truth — the dangerous direction.

    Under-reporting coverage wastes a reviewer's time; over-reporting tells a team a
    behaviour is tested when it isn't. These are not symmetric errors and should never
    be collapsed into one accuracy number.
    """
    rank = {"uncovered": 0, "partial": 1, "covered": 2}
    over = sum(1 for e, a in pairs if rank.get(a, 0) > rank.get(e, 0))
    return round(over / len(pairs), 3) if pairs else None


# --------------------------------------------------------------------------- sections
def run_probes() -> dict:
    """Adversarial grounding check. No LLM: the claim is scripted, we score the guard."""
    rows, pairs = [], []
    for p in dataset.HALLUCINATION_PROBES:
        idx = cov.citation_index(p["excerpts"])
        claim = p["claim"]
        v = cov._ground_verdict(claim["status"], claim.get("rationale", ""),
                                claim.get("files") or [], idx,
                                model_confidence=claim.get("confidence"))
        ok = v["status"] == p["expected_status"]
        if p.get("expect_rejected_citation"):
            ok = ok and bool(v["files_rejected"])
        rows.append({"id": p["id"], "expected": p["expected_status"],
                     "actual": v["status"], "confidence": v["confidence"],
                     "rejected": v["files_rejected"], "pass": ok})
        pairs.append((p["expected_status"], v["status"]))
    passed = sum(1 for r in rows if r["pass"])
    return {"section": "hallucination_probes", "rows": rows,
            "score": round(passed / len(rows), 3) if rows else None,
            "passed": passed, "total": len(rows), "confusion": _confusion(pairs)}


def _reuse_same(a: dict, b: dict) -> bool:
    """Mirror of testgen.service._semantic_reuse_compatible, minus the store lookup.

    Kept structurally identical on purpose: if the production rule changes, this must be
    updated in lockstep or the harness stops measuring the real thing.
    """
    from testgen.lineage import REUSE_SIMILARITY_API, REUSE_SIMILARITY_GENERAL
    if generate_test_identity_hash(a) == generate_test_identity_hash(b):
        return True
    is_api = (a.get("category") == "api_tests" or a.get("method") or a.get("endpoint"))
    if is_api:
        if str(a.get("method") or "").upper() != str(b.get("method") or "").upper():
            return False
        if normalize_endpoint(a.get("endpoint")) != normalize_endpoint(b.get("endpoint")):
            return False
        if scenario_kinds_incompatible(derive_scenario_kind(a), derive_scenario_kind(b)):
            return False
        return token_set_similarity(lineage_token_set(a),
                                   lineage_token_set(b)) >= REUSE_SIMILARITY_API
    if scenario_kinds_incompatible(derive_scenario_kind(a), derive_scenario_kind(b)):
        return False
    return token_set_similarity(lineage_token_set(a),
                               lineage_token_set(b)) >= REUSE_SIMILARITY_GENERAL


def _score_pairs(pairs):
    rows = []
    for p in pairs:
        actual = _reuse_same(p["a"], p["b"])
        sim = round(token_set_similarity(lineage_token_set(p["a"]),
                                         lineage_token_set(p["b"])), 3)
        rows.append({"id": p["id"], "expected_same": p["expected_same"],
                     "actual_same": actual, "token_similarity": sim,
                     "pass": actual == p["expected_same"]})
    return rows


def run_dedup() -> dict:
    """Score the reuse decision against labelled duplicate / non-duplicate pairs.

    `DEDUP_PAIRS` are decidable — the structural keys (method, endpoint, status code)
    make the right answer unambiguous, so this section is expected to be perfect and any
    drop is a genuine regression.

    `KNOWN_LIMITATION_PAIRS` are REPORTED, NOT SCORED. They document a measured fact:
    for non-API cases the token-similarity metric cannot separate duplicates from
    distinct behaviours at any threshold (see dataset.py). Scoring them would just
    tempt someone into tuning a constant until the suite went green, which is how the
    constant became untrustworthy in the first place.
    """
    rows = _score_pairs(dataset.DEDUP_PAIRS)
    tp = sum(1 for r in rows if r["expected_same"] and r["actual_same"])
    fp = sum(1 for r in rows if not r["expected_same"] and r["actual_same"])
    fn = sum(1 for r in rows if r["expected_same"] and not r["actual_same"])
    passed = sum(1 for r in rows if r["pass"])

    limits = _score_pairs(dataset.KNOWN_LIMITATION_PAIRS)
    return {
        "section": "dedup", "rows": rows,
        "score": round(passed / len(rows), 3) if rows else None,
        "passed": passed, "total": len(rows),
        # A false merge destroys a distinct test case, so it is the error to minimise.
        "false_merge": fp, "missed_merge": fn,
        "precision": round(tp / (tp + fp), 3) if (tp + fp) else None,
        "recall": round(tp / (tp + fn), 3) if (tp + fn) else None,
        "known_limitations": limits,
        "known_limitation_failures": [r for r in limits if not r["pass"]],
    }


def run_coverage(llm, samples=1) -> dict:
    """Score real Mind Map verdicts against human labels. Requires a live LLM."""
    pairs, rows = [], []
    for ex in dataset.COVERAGE_EXAMPLES:
        res = cov.review_code_coverage(llm, ex["feature"], ex["requirement"],
                                       ex["cases"], ex["excerpts"], samples=samples)
        by_id = {c["test_case_id"]: c for c in res["cases"]}
        for cid, expected in ex["expected"].items():
            got = by_id.get(cid) or {}
            actual = got.get("status", "uncovered")
            pairs.append((expected, actual))
            rows.append({"example": ex["id"], "case": cid, "expected": expected,
                         "actual": actual, "confidence": got.get("confidence"),
                         "needs_review": got.get("needs_review"),
                         "rejected_citations": got.get("files_rejected") or [],
                         "pass": actual == expected})
    conf = _confusion(pairs)
    return {"section": "coverage", "rows": rows, "confusion": conf,
            "score": conf["accuracy"], "overclaim_rate": _overclaim_rate(pairs),
            "samples": samples}


# --------------------------------------------------------------------------- run metadata
def _dataset_fingerprint() -> str:
    """A short, reproducible identifier for the exact corpus a run was scored against.

    Computed (not hand-maintained) so it can never go stale the way a manually-bumped
    version constant would: it changes if and only if the actual dataset content
    changes, which is exactly what "reproduce/interpret a run later" needs. Only the
    fields that affect scoring go in (ids + the ground truth), not free-text notes —
    a wording fix to a `note` explaining a label shouldn't look like a corpus change.
    """
    material = repr((
        [(p["id"], p["expected_status"]) for p in dataset.HALLUCINATION_PROBES],
        [(p["id"], p["expected_same"]) for p in dataset.DEDUP_PAIRS],
        [(p["id"], p["expected_same"]) for p in dataset.KNOWN_LIMITATION_PAIRS],
        [(e["id"], tuple(sorted(e["expected"].items()))) for e in dataset.COVERAGE_EXAMPLES],
    )).encode()
    return hashlib.sha256(material).hexdigest()[:12]


def _run_metadata(args, reports) -> dict:
    """Safe-to-publish metadata for reproducing/interpreting a run later (#43's own
    benchmark needs this to compare runs across models). Deliberately excludes
    anything that isn't already a public identifier: no API key, no URL that might
    embed credentials (ollama_url is local-network-only by convention, but is still
    left out here since it's never needed to interpret a result)."""
    return {
        "tool": "tests.eval.run_eval",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "dataset_fingerprint": _dataset_fingerprint(),
        "sections_run": [r["section"] for r in reports],
        # Only meaningful (and only ever populated) when --coverage actually ran --
        # the offline sections don't call a model at all, so labelling them with
        # whatever --provider/--model happened to be passed would be misleading.
        "provider": args.provider if getattr(args, "coverage", False) else None,
        "model": args.model if getattr(args, "coverage", False) else None,
    }


# --------------------------------------------------------------------------- reporting
def _print(report: dict):
    print(f"\n=== {report['section']} ===")
    if report.get("score") is not None:
        print(f"score: {report['score']}  "
              f"({report.get('passed', '?')}/{report.get('total', '?')})")
    if report.get("overclaim_rate") is not None:
        print(f"overclaim rate (worse than wrong): {report['overclaim_rate']}")
    for k in ("false_merge", "missed_merge", "precision", "recall"):
        if report.get(k) is not None:
            print(f"{k}: {report[k]}")
    conf = report.get("confusion")
    if conf and conf.get("accuracy") is not None:
        print(f"accuracy: {conf['accuracy']} over n={conf['n']}")
        for s, m in conf["per_status"].items():
            if m["support"]:
                print(f"  {s:<10} support={m['support']:<3} "
                      f"precision={m['precision']} recall={m['recall']}")
    for r in report["rows"]:
        if not r.get("pass", True):
            print(f"  FAIL {r}")
    limits = report.get("known_limitations")
    if limits:
        bad = [r for r in limits if not r["pass"]]
        print(f"known limitations (reported, not scored): "
              f"{len(bad)}/{len(limits)} currently decided wrongly")
        for r in limits:
            flag = "  " if r["pass"] else "! "
            want = "same" if r["expected_same"] else "distinct"
            got = "same" if r["actual_same"] else "distinct"
            print(f"  {flag}{r['id']}: similarity={r['token_similarity']} "
                  f"truth={want} decided={got}")
        if bad:
            print("  -> token-set similarity cannot separate these classes; see "
                  "dataset.KNOWN_LIMITATION_PAIRS before changing any threshold.")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--probes", action="store_true", help="adversarial grounding checks")
    ap.add_argument("--dedup", action="store_true", help="dedup threshold scoring")
    ap.add_argument("--coverage", action="store_true", help="real-model coverage accuracy")
    ap.add_argument("--samples", type=int, default=1, help="Mind Map samples per batch")
    ap.add_argument("--provider", default=os.getenv("EVAL_PROVIDER", "ollama"))
    ap.add_argument("--model", default=os.getenv("EVAL_MODEL", "qwen2.5:7b"))
    ap.add_argument("--ollama-url", default=os.getenv("OLLAMA_URL", "http://localhost:11434"))
    ap.add_argument("--api-key", default=os.getenv("EVAL_API_KEY", ""))
    ap.add_argument("--min-probes", type=float, default=1.0,
                    help="probes must score at least this (default 1.0 — the grounding "
                         "layer is deterministic, so anything less is a real regression)")
    ap.add_argument("--min-dedup", type=float, default=1.0)
    ap.add_argument("--min-coverage", type=float, default=0.0,
                    help="set a floor once you have a baseline from your own data")
    ap.add_argument("--json", action="store_true", help="emit machine-readable output")
    ap.add_argument("--out", default="", help="also write the full JSON result "
                    "(same payload as --json) to this file path, regardless of "
                    "--json — so a normal human-readable run can still archive a "
                    "machine-readable record")
    args = ap.parse_args(argv)

    if not (args.probes or args.dedup or args.coverage):
        args.probes = args.dedup = True     # cheap, offline sections by default

    reports, failures = [], []
    if args.probes:
        r = run_probes()
        reports.append(r)
        if r["score"] is not None and r["score"] < args.min_probes:
            failures.append(f"probes {r['score']} < {args.min_probes}")
    if args.dedup:
        r = run_dedup()
        reports.append(r)
        if r["score"] is not None and r["score"] < args.min_dedup:
            failures.append(f"dedup {r['score']} < {args.min_dedup}")
    if args.coverage:
        from llm import LLM
        llm = LLM(provider=args.provider, model=args.model, api_key=args.api_key,
                  ollama_url=args.ollama_url)
        r = run_coverage(llm, samples=args.samples)
        reports.append(r)
        if r["score"] is not None and r["score"] < args.min_coverage:
            failures.append(f"coverage {r['score']} < {args.min_coverage}")

    meta = _run_metadata(args, reports)
    payload = {"meta": meta, "reports": reports, "failures": failures}

    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"dataset fingerprint: {meta['dataset_fingerprint']}  |  {meta['timestamp']}")
        for r in reports:
            _print(r)
        if failures:
            print("\nFAILED thresholds:")
            for f in failures:
                print(f"  - {f}")
        else:
            print("\nall scored sections met their thresholds")

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        print(f"\nresults written to {args.out}")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
