# Your first run

## Your first run: a guided tour

Here's the whole journey, then each step in detail:

```
  Sign in ─► Create a Project ─► Connect repos ─► Add a Feature (upload docs)
     │
     └─► Generate test cases ─► Review & edit ─► Analyze code ─► Mind Map
            │
            └─► Track in a Cycle ─► Export a report
```

The left sidebar has everything: **Dashboard · Projects & Repos · Test Cases ·
Code Analysis & Cycles · Mind Map · Step Library · Usage & Cost · Configuration**.

**Step 1 — Create a project.** Go to **Projects & Repos** and add a project. A project
is a product or team space that holds its features, repos, and results.

**Step 2 — Connect your repos (optional but recommended).** Add your GitHub (or GitLab)
repositories to the project and pick the **branch per repo** (leave blank for the
default). This is what powers code analysis and the Mind Map later. Private repos need
a token — paste it under **Configuration → Integrations**, or set `GITHUB_TOKEN` in `.env`.

**Step 3 — Add a feature = upload your docs.** Create a feature and upload one or more
requirement documents (PRD / HLD / LLD, as PDF / DOCX / Markdown). A "feature" is one
unit of behavior you want tested.

**Step 4 — Generate the test cases.** Choose a **coverage depth** (how thorough) and use
the **focus sliders** to weight Functional / E2E / API / Non-functional. Hit generate —
it runs as a background **job** you can watch live or come back to.

**Step 5 — Review & refine.** Open **Test Cases** to read, edit, filter, and organize the
generated cases. Cases are made of reusable **steps** (see **Step Library**) — edit a step
once and every case using it updates.

**Step 6 — Analyze your code.** In **Code Analysis & Cycles**, run analysis to map recent
commits/PRs to the **test cases they impact** and to see the **coverage** a merged PR
delivers (including developer-written automated tests), with linked-commit evidence.

**Step 7 — Run the Mind Map.** For the deepest check, open **Mind Map**. It reads your
actual production code and rates every feature **covered / partial / uncovered**, citing
the files it read. An empty result is explainable (wrong branch? logic only in tests?),
never a black box. Tip: a hosted LLM gives noticeably sharper verdicts than the small
local model.

**Step 8 — Track a release & report.** Assemble a regression **cycle** from the cases you
care about and track status per case. Export a per-feature **PDF report** to share.

**Step 9 (optional) — Start Developing.** Ask wardenIQ to generate implementation code
that satisfies a feature's requirements, push it to a feature-named branch, and open a
**pull request** (needs a write-scoped token). Then analyze that PR for coverage.

---
