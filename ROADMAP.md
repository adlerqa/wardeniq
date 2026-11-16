# wardenIQ roadmap

wardenIQ is beta and moving fast. This is what we're building and, more usefully, **where
you can help**. Everything here is tracked as a GitHub issue — the roadmap is the narrative,
the issues are the work.

> **New here?** The [good first issues](https://github.com/adlerqa/wardeniq/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22)
> each carry context, acceptance criteria and pointers to the relevant files. Start there.

## How to pick something up

1. **Comment on the issue to claim it** before you start. We've already had two people
   independently solve the same issue — that's our fault for not saying this, and it wastes
   real effort. One comment avoids it.
2. Ask questions in the issue. A clarifying question is always cheaper than a rewrite.
3. Open a draft PR early if it's substantial. Direction feedback beats a surprise at review.
4. Read [CONTRIBUTING.md](CONTRIBUTING.md) for the dev loop. The whole stack runs in Docker
   Compose; you don't need Python, Node or MongoDB installed locally.

---

## Now — [v0.3.0: First run & trust](https://github.com/adlerqa/wardeniq/milestone/1)

**This milestone shipped as `v0.3.0`.** The text below is the plan as it was written for the
milestone and has not been revised since; see the [CHANGELOG](CHANGELOG.md) for what shipped
and the release notes for known limitations.

The two things that decide whether wardenIQ gets adopted: **does it work in the first five
minutes**, and **can you trust what it generates**. Everything here beats every feature below.

**Trust.** [#36](https://github.com/adlerqa/wardeniq/issues/36) is the most important open
issue in the project: generation can emit the prompt's own few-shot examples verbatim as real
test cases, attributed to your feature, with a high confidence score. Grounded output is the
entire value proposition — a hallucinated case doesn't fail loudly, it sits in the suite
looking legitimate and inflates your coverage. Fixing this matters more than any integration.

**First run.** [#27](https://github.com/adlerqa/wardeniq/issues/27) — the bundled stack can't
start on Docker Desktop with a kernel ≥ 6.19, and `run.sh` exits 0 while it fails. A new user
gets a success-looking run and a dead `localhost:8001`.

**Datastore.** [#41](https://github.com/adlerqa/wardeniq/issues/41) — validate the stack on
**Percona Server for MongoDB + Percona Search** (Percona's mongot fork). Today wardenIQ needs 6
search indexes; Atlas free M0 allows 3, so evaluating us effectively requires a paid M10+ tier.
Percona should remove that cap and avoid tying embedding choice to a single vendor — which
matters because bring-your-own-model is a stated principle. Validation found it does *not*
reliably sidestep the kernel guard in #27, and it is itself in technical preview, so for
v0.3.0 it ships as an **opt-in technical preview**, not the default (see
[docs/percona-search-validation.md](docs/percona-search-validation.md)). HA, load and the
supported-or-default decision are tracked in #222 and #223. `config/mongod.conf` notes the
project migrated *from* Percona, so this is a return with known ground, not a new bet.

**Measurement.** [#42](https://github.com/adlerqa/wardeniq/issues/42) — publish a generation
quality benchmark (groundedness, exemplar leakage, coverage recall). We assert grounded output;
we should measure it, and gate CI on it so #36 can't regress silently.
[#43](https://github.com/adlerqa/wardeniq/issues/43) revisits the bundled model default on the
back of those numbers.

Also in scope: [#44](https://github.com/adlerqa/wardeniq/issues/44) — the sign-in screen is the
one place a boot failure *isn't* shown, which is exactly where you're stuck — the boot banner
covering the header including Sign out
([#34](https://github.com/adlerqa/wardeniq/issues/34)), an example PRD so a first run needs no
document of your own ([#12](https://github.com/adlerqa/wardeniq/issues/12)), and the first
tagged release ([#18](https://github.com/adlerqa/wardeniq/issues/18)).

## Next — Integrations

Both epics needed machine authentication first, and that has shipped:
**[#37 — service accounts and API tokens](https://github.com/adlerqa/wardeniq/issues/37)**
(`app/core/token_auth.py`, `app/api/routes/api_tokens.py`). A CI job or a Jira app can now
authenticate without a session cookie, so the work below is unblocked.

### [Jira app](https://github.com/adlerqa/wardeniq/milestone/2) — [#38](https://github.com/adlerqa/wardeniq/issues/38)

Drive wardenIQ from inside Jira: open a ticket, generate a grounded test suite from what the
ticket already contains, see coverage without leaving the issue view.

We already pull *from* Jira (`app/jira.py`, plus issue/epic/Confluence access and a webhook).
What's missing is a surface *inside* Jira.

The competitor is Atlassian Rovo, and the differentiator is not "AI in Jira" — Rovo has that.
It's that our output is **grounded and traceable**: every case links back to the requirement
text it came from, and the Validator flags anything that doesn't. That transparency is the
feature, and it shouldn't be cut for scope.

### [CI/CD](https://github.com/adlerqa/wardeniq/milestone/3) — [#39](https://github.com/adlerqa/wardeniq/issues/39)

Coverage intelligence in the pipeline, where merge decisions actually get made. A GitHub
Action and a CLI that answer "what did this PR touch, and is it tested?" as a PR comment and
a Check Run.

The analysis engine already exists — Code Analysis maps commits and PRs to impacted test
cases today. What's missing is the pipeline-native surface.

The CLI is the highest-leverage piece: build it once and GitLab CI, Jenkins, CircleCI and
Bitbucket come along for free. Two constraints we're committing to up front — it must work
when wardenIQ is **not** publicly reachable (the CI job calls us, not the reverse), and it
must **never fail your build by default**.

### [Agentic PR review](https://github.com/adlerqa/wardeniq/milestone/5) — [#53](https://github.com/adlerqa/wardeniq/issues/53)

wardenIQ watches the repos it's already connected to and reviews **every pull request marked
ready for review, and again whenever new commits land on it** — incrementally, only the new
commits, and silent when nothing changed ([#247](https://github.com/adlerqa/wardeniq/issues/247)).
`/wardeniq review` re-runs it on demand. Connect a repo once; no workflow files to edit.

**The bar is CodeRabbit-level code review, and then better.** A full code reviewer — bugs,
security, error handling, performance, tests, readability — that is as good as the best tools
on code-against-code review. On top of that comes what they can't do: review the PR **against
the requirements it claims to implement**. *"This PR claims to implement FR-2, but FR-2 says the
token expires in 30 minutes and this sets 3600 seconds."* That needs requirements ingested,
embedded, versioned and traceable to the sentence, which wardenIQ already has. Requirement
conformance is what makes us better; matching them on general review is the entry ticket.

RAG is not the differentiator — every tool in this category does retrieval now. What differs is
*what* we retrieve over, and that every finding is grounded and cited.

We'll hold ourselves to that bar in public: an open, reproducible benchmark against CodeRabbit
and Qodo ([#248](https://github.com/adlerqa/wardeniq/issues/248)), reporting general defects and
requirement conformance separately, including where we lose.

Semantic PR → requirement mapping ([#54](https://github.com/adlerqa/wardeniq/issues/54)) has
shipped, so PRs reach requirements without tagged titles. Next: the agent runtime
([#55](https://github.com/adlerqa/wardeniq/issues/55)), PR write-back
([#57](https://github.com/adlerqa/wardeniq/issues/57)), the triggers
([#56](https://github.com/adlerqa/wardeniq/issues/56), with re-review on new commits from #247),
and a latency budget held throughout ([#58](https://github.com/adlerqa/wardeniq/issues/58)).

One dependency that isn't technical: **#36 has to stay fixed.** We can't sell trustworthy review
while generation could emit its own prompt examples as real output.

## Direction — [Specialist agents](https://github.com/adlerqa/wardeniq/milestone/6) — [#242](https://github.com/adlerqa/wardeniq/issues/242)

wardenIQ is becoming a **team of specialist QA agents**, each owning one part of delivery and
handing work to the others through typed, inspectable contracts — organised like a good QA team,
not one model doing everything in one prompt:

| Agent | Owns |
|---|---|
| E2E scenario validator ([#244](https://github.com/adlerqa/wardeniq/issues/244)) | Are our e2e scenarios still correct, grounded and passing? |
| Unit-coverage validator ([#245](https://github.com/adlerqa/wardeniq/issues/245)) | Is the code behind each requirement actually unit-tested? |
| E2E scenario author ([#246](https://github.com/adlerqa/wardeniq/issues/246)) | Writes new scenarios to close the gaps the validators find |
| PR reviewer ([#247](https://github.com/adlerqa/wardeniq/issues/247)) | Reviews every ready PR, and again on new commits |

An orchestrator (not an agent) schedules them on events — a PR becomes ready, new commits, a
requirement changes, a nightly run — and records every hand-off, budget and approval. The platform
design is [#243](https://github.com/adlerqa/wardeniq/issues/243), extending the hand-off schema in
[#235](https://github.com/adlerqa/wardeniq/issues/235). A2A is used for its task and artifact model
first; running agents as separate services stays opt-in
([#237](https://github.com/adlerqa/wardeniq/issues/237)).

**Tests we write, we prove.** When the author agent writes an e2e test, it isn't proposed until it
has run and passed repeatedly — through the team's own CI on a draft PR by default, or in an
isolated sandbox against a preview URL ([#251](https://github.com/adlerqa/wardeniq/issues/251)).

Measurement still decides *how* we build it. [#232](https://github.com/adlerqa/wardeniq/issues/232)
adds token, latency, cost and overclaim metrics to the eval harness and needs no agent experience;
the spikes — an independent verifier ([#233](https://github.com/adlerqa/wardeniq/issues/233)) and
parallel Mind Map workers ([#234](https://github.com/adlerqa/wardeniq/issues/234)) — and the RFC
([#231](https://github.com/adlerqa/wardeniq/issues/231)) shape the design, and the decision record
([#236](https://github.com/adlerqa/wardeniq/issues/236)) settles whether each part is adopted,
adopted in part or shelved, and which parts run as separate agents and which stay in-process.
Multi-agent setups can burn many times the tokens for little gain, so every agent ships with a
budget and an eval showing it earns its cost.

This is where we're heading, and it's still open to challenge. Tell us what you think, including
"don't build this": start at the RFC ([#231](https://github.com/adlerqa/wardeniq/issues/231)). The
poll in [#239](https://github.com/adlerqa/wardeniq/discussions/239) is the quickest way to weigh in.

Good places to start: [#250](https://github.com/adlerqa/wardeniq/issues/250) (coverage report
parser, no LLM needed), [#232](https://github.com/adlerqa/wardeniq/issues/232), and the benchmark
[#248](https://github.com/adlerqa/wardeniq/issues/248). And we want honest product feedback — the
blunter the better — in [#249](https://github.com/adlerqa/wardeniq/issues/249).

It respects the principles below: bring-your-own-model, self-hosted first, and every agent ships
with its check. It shares groundwork with the PR review runtime
([#55](https://github.com/adlerqa/wardeniq/issues/55)), so coordinate there before starting.

## Later — [Platform](https://github.com/adlerqa/wardeniq/milestone/4)

Cross-cutting work that makes the rest sustainable: structured logging
([#17](https://github.com/adlerqa/wardeniq/issues/17) — there are 24 bare `print()` calls and
no `logging` import anywhere), self-hosted GitLab support
([#14](https://github.com/adlerqa/wardeniq/issues/14) — currently hardcoded to gitlab.com),
cost estimation before a generation run
([#22](https://github.com/adlerqa/wardeniq/issues/22)), and container healthchecks
([#25](https://github.com/adlerqa/wardeniq/issues/25)).

Product work that makes wardenIQ something you're *told by* rather than somewhere you go:
coverage trends over time ([#45](https://github.com/adlerqa/wardeniq/issues/45) — the dashboard
is point-in-time, and "is this getting better?" is the question leads actually ask), requirement
drift detection ([#46](https://github.com/adlerqa/wardeniq/issues/46) — when a PRD changes, which
existing cases just went stale?), outbound notifications to Slack/Teams/webhooks
([#47](https://github.com/adlerqa/wardeniq/issues/47)), and generation latency
([#48](https://github.com/adlerqa/wardeniq/issues/48) — multi-pass generation takes minutes, and
speed decides whether people run it on every change or occasionally).

---

## Principles

These are the calls we've already made, so you don't have to re-litigate them in a PR:

- **Grounded beats comprehensive.** A suite of 40 cases that all trace to real requirements is
  worth more than 200 that might not. When in doubt, generate less.
- **Assume our own AI is unreliable.** The Validator exists because the generator will
  confidently invent things. New AI features should ship with the check, not after it.
- **Self-hosted is a first-class deployment**, not a fallback. Plenty of our users can't send
  their requirements to a third party, and features that assume public reachability exclude them.
- **Bring your own model.** No hard dependency on one provider. Ollama has to keep working.
- **Don't break the build.** Anything that plugs into someone's pipeline is advisory by
  default and opt-in to gate.
- **Tests we write, we prove.** Nothing wardenIQ writes is proposed until it has run and passed,
  and every agent has an owner, a budget and an eval.

## Not planned

Saying no is part of a roadmap:

- **Being your test runner or CI.** wardenIQ decides *what* should be tested and whether it
  *is*; it won't compete with Playwright, pytest or your pipeline. The one exception is proving
  the tests wardenIQ itself writes ([#251](https://github.com/adlerqa/wardeniq/issues/251)) —
  preferably by running them through your CI rather than its own runner.
- **Being a test-management SaaS.** Test Cycles exist so you don't have to leave for a release
  regression run — not to replace a dedicated tool.
- **A hosted multi-tenant offering**, for now. The product is self-hosted; that shapes the
  architecture and we'd rather do it well than split focus.

---

Roadmap items change. If something here is wrong, or you need something that isn't here,
open an issue and argue for it — that's a genuinely useful contribution on its own.
