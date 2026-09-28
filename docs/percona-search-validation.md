# Percona Search for MongoDB — validation results (issue #41)

Validation-phase results for [#41](https://github.com/adlerqa/wardeniq/issues/41). This
document is evidence for a later maintainer decision — **it does not make Percona the
bundled default, and does not declare it officially supported.** The bundled default
remains MongoDB Community + mongot (`docker-compose.mongodb.yml`).

An alternative compose configuration, `docker-compose.mongodb-percona.yml`, lets an
operator run wardenIQ against Percona Server for MongoDB + Percona Search instead, for
further evaluation. It is never included automatically.

## What was actually run

Real containers, real queries, on this machine (Docker Desktop, macOS, Apple Silicon,
`docker info` kernel `6.12.76-linuxkit`):

- `percona/percona-server-mongodb:8.3` (resolved to `8.3.11-3`, confirmed via
  `docker pull` and container logs) — single-node replica set (`rs0`), not the bundled
  stack's 3-node HA set. mongot only requires replica-set membership for oplog
  tailing, not a specific member count, so a single node is sufficient to validate
  search behavior without the extra time/resource cost of three nodes.
- `percona/percona-search-mongodb:1.70.4` — Percona's mongot fork.
- The real, unmodified application `Store` class (`app/store/`) and its actual
  `ensure_indexes()` / `_ensure_vector()` / `_ensure_text()` code — not a
  reimplementation.
- The real `pytest -m dbintegration` suite, and the four tests #41 specifically names.

## Image names — a correction to Percona's own docs

Percona's published docs
([install-mongot.html](https://docs.percona.com/percona-search-for-mongodb/install-mongot.html))
name the mongot image as `percona/percona-server-mongodb-mongot:<TAG>`. That repository
exists on Docker Hub but **has zero published tags** — `docker pull
percona/percona-server-mongodb-mongot:8.3` fails with "not found". The actually-published
image, confirmed by a real `docker pull` and by reading its `docker inspect` labels
(`org.opencontainers.image.title: "Percona Search for MongoDB"`,
`org.opencontainers.image.source: https://github.com/percona/percona-mongot`), is
**`percona/percona-search-mongodb`**. The compose file in this PR uses the working name.

The config schema also differs from what Percona's docs describe: the docs say mongot
reads its password file path from `/passwordFile`; the image's actual shipped default
config (read directly from the image via `docker run --entrypoint cat ... /etc/mongot/mongot.yml`)
uses `/etc/mongot/secrets/passwordFile`, and nests auth under
`syncSource.replicaSet.scramAuth.*` — MongoDB Community mongot's config
(`config/mongot.conf`) puts `username`/`passwordFile` directly under
`syncSource.replicaSet` with no `scramAuth` wrapper. This is a real, confirmed
config-shape difference between the two backends, not a copy-paste of the Community
file. `config/mongot-percona.yml` in this PR matches the image's actual schema.

## Six search indexes — confirmed working

The app creates exactly 6 search indexes (confirmed by reading `app/store/base.py`):
5 `vectorSearch` (on `features`, `feature_chunks`, `code_chunks`, `test_steps`,
`test_cases`) + 1 `search` text index (on `test_cases`).

Ran the real `Store(uri, db, dim=768).ensure_indexes()` against the Percona stack:

| Step | Result |
|---|---|
| `ensure_indexes()` call returns | 0.44s |
| All 6 indexes report `status: READY, queryable: true` | within 18s (polled) |
| Index definitions | byte-identical to what the app sends for MongoDB Community — no code change |

Confirmed **working**, not just "started successfully" — see search validation below.

## Search behavior — confirmed working

Inserted 10 real documents (2 semantic clusters: 5 "password reset" cases, 5 unrelated
"billing" cases) and ran the app's actual aggregation pipeline shapes:

- **`$vectorSearch`**: querying near the "password reset" cluster returned exactly those
  5 documents, correctly ranked by score (0.9725 → 0.9695), zero cross-cluster leakage.
- **`$search` (text)**: querying `"billing"` on the `title` field returned exactly the 5
  billing-titled documents, zero false matches.

Both **confirmed working**, not assumed.

## Embedding / vector-dimension compatibility

- The app's default dimension (768, `nomic-embed-text`) — confirmed working above.
- 1536 dimensions (e.g. OpenAI `text-embedding-3-small`) — tested in isolation (a fresh
  collection, one seeded document, a real `$vectorSearch` query): index reached
  `queryable: true` and returned the seeded document. **Confirmed working**, no
  application change required — the app already treats `dim` as a runtime parameter
  (`Store.__init__(uri, db_name, dim)`), so this needed no code change to validate.

## Query latency (small dataset — sanity check, not a load test)

20 runs each, 10 documents in the collection:

| Query | min | p50 | max |
|---|---|---|---|
| `$vectorSearch` | 4.1ms | 6.7ms | 49.4ms |
| `$search` (text) | 4.4ms | 5.1ms | 7.8ms |

This confirms search responds correctly and quickly at small scale. It is **not** a
production-scale or concurrent-load benchmark — that would need a corpus and harness
this validation pass didn't build.

## Memory footprint — live snapshot, not a controlled benchmark

Captured via `docker stats --no-stream` while both stacks happened to be running
side by side on this machine (the already-running MongoDB Community stack was not
restarted or disrupted for this comparison):

| Container | CPU % | Memory |
|---|---|---|
| `mongod-percona` (1 node) | 3.09% | 360.5MiB |
| `mongot-percona` | 4.82% | 862.3MiB |
| `mongod1`/`mongod2`/`mongod3` (Community, 3 nodes) | 2.68% / 2.15% / 1.90% | 311.8 / 295.3 / 282.9 MiB |
| `mongot` (Community) | 18.46% | 635.5MiB |

Not apples-to-apples (1 Percona node vs. 3 Community nodes; the Community stack was
live and may have had other activity at the moment of capture) — reported as-is rather
than adjusted into a false equivalence. Per-node `mongod` memory is in the same
ballpark; `mongot-percona` used more memory than Community's `mongot` in this snapshot.

## Existing test suite

- The four tests #41 names by file — `test_embeddings.py`, `test_feature_chunk_retrieval.py`,
  `test_rag_evidence_sufficiency.py`, `test_index_fingerprint.py` — **do not exercise a
  live database at all**, on either backend. `test_embeddings.py` is a pure unit test
  (network mocked). `test_index_fingerprint.py` tests subprocess-stable hashing, no DB.
  `test_rag_evidence_sufficiency.py` and `test_feature_chunk_retrieval.py` are built on
  `mongomock` (an in-memory fake with no `$vectorSearch` support), specifically so they
  run without a real backend. Ran as-is: 46 passed, 1 skipped
  (`test_feature_chunk_retrieval.py` — `mongomock` isn't installed in this environment
  and isn't listed in `app/requirements-dev.txt`; this is a **pre-existing gap on
  `main`, unrelated to Percona**, confirmed by checking `requirements-dev.txt`, not
  something this PR introduces or should silently fix).
- Broader `pytest -m dbintegration` suite, pointed at the Percona stack via
  `MONGO_TEST_URI=mongodb://localhost:27019/?directConnection=true`: **9 passed, 6
  skipped** (same pre-existing `mongomock` gap, confirmed by the skip reasons — nothing
  Percona-specific). `test_ensure_indexes_creates_core_collections` is written to
  *tolerate* the search-index step failing, because CI's own `db-integration-tests` job
  runs against a plain `mongo:7` service with no mongot at all (see that test file's
  module docstring). Against Percona, `ensure_indexes()` completed **fully**, including
  all 6 search indexes — a strictly stronger result than what CI's own dbintegration
  job exercises for either backend today.
- Full suite, unmodified, excluding `dbintegration`: `pytest -m "not dbintegration"` →
  **671 passed, 55 skipped** — confirms adding the Percona compose/config files caused
  no regressions anywhere else in the repo.

## #27 kernel ≥ 6.19 — NOT confirmed avoided (this is the most important finding)

**This directly contradicts one of #41's expected benefits, and the previous
investigation's framing needs correcting.**

This machine's kernel (`6.12.76-linuxkit`) is below the 6.19 threshold, so the guard
does not fire here for *either* backend — a live trigger comparison isn't possible in
this environment. But the guard's presence doesn't require live triggering to check:
it's a static string check in the binary itself.

```
docker run --rm --entrypoint sh percona/percona-server-mongodb:8.3 -c \
  "LC_ALL=C grep -a -o '.\{0,60\}SERVER-121912.\{0,120\}' /usr/bin/mongod"
```

Output, verbatim, from the actual Percona 8.3 `mongod` binary:

> `...his version of MongoDB. See https://jira.mongodb.org/browse/SERVER-121912 for more information.`

And:

> `MongoDB cannot start: Linux kernel versions 6.19 and newer has a known incompatibility with this version of MongoDB. See https:/...`

This is the **exact same guard message and the exact same MongoDB JIRA ticket**
(SERVER-121912) that #27 documents for MongoDB Community. Percona Server for MongoDB is
built from MongoDB's own source and has evidently inherited this guard rather than
patching around it. Percona also has no `8.1`/`8.2` release line (only `8.0.x` then a
jump to `8.3.x`, confirmed via the Docker Hub tags API) — mirroring MongoDB's own
version gap around the `useGrpcForSearch` floor — so an operator forced onto Percona
8.3 for gRPC search support would very likely hit the **same circular constraint #27
describes**, not a different one.

**Conclusion: Percona Search should NOT be assumed to unblock #27.** This is a static
binary-level finding (the guard code and message are present), not a live trigger test
on an affected kernel (not available in this environment) — but it is strong, direct
evidence against the "no tcmalloc kernel guard" benefit #41 lists as a hypothesis to
confirm. If someone has access to a real kernel ≥ 6.19 host, live-triggering this would
be worth doing to convert "very likely" into "confirmed."

## Confirmed / partial / failed / not tested

- **Confirmed working:** compose stack starts cleanly; replica-set init and
  `searchCoordinator` user creation via the existing `mongosh`-based setup pattern;
  all 6 search indexes build and become queryable using the app's real, unmodified
  index-creation code; `$vectorSearch` and `$search` both return correct, precisely
  scoped results; 768-dim (the app's default) and 1536-dim vectors both work; the full
  non-dbintegration test suite (671 tests) is unaffected; the dbintegration suite runs
  further to completion against Percona than it does against CI's plain `mongo:7`.
- **Confirmed NOT working as hoped:** the kernel ≥ 6.19 guard is very likely still
  present (static evidence above) — Percona should not be assumed to unblock #27.
- **Not tested:** production-scale/concurrent-load query performance; the 3-node HA
  topology (this validation used a single node, by design, for speed); auth-enabled
  mode (`MONGO_AUTH_ENABLED=true`); upgrade/migration path from an existing MongoDB
  Community deployment; long-running stability.
- **Vendor-specific differences found:** `setParameter` set differs
  (`skipAuthenticationToSearchIndexManagementServer` and `searchTLSMode` are
  Percona-specific, matching what #29 already documented); mongot config schema differs
  (`scramAuth` nesting); mongot image name differs from Percona's own published docs.

## Follow-up decision

Whether Percona should become the recommended or bundled default remains **a maintainer
decision**, to be made after reviewing these results — not decided by this validation
work. Given the kernel-guard finding above, the strongest #41-listed rationale for
adopting Percona (avoiding #27) does not currently hold up; the other two rationales
(Atlas index-tier cost, embedding-model vendor coupling) are unaffected by this finding
and remain intact.
