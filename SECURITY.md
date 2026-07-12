# Security Policy

Thank you for helping keep wardenIQ and its users safe.

## Please do not report security issues publicly

If you believe you have found a security vulnerability in wardenIQ, **do not
open a public GitHub issue, discussion, or pull request** describing it. Public
disclosure before a fix is available puts existing users at risk.

## Reporting a vulnerability

Contact the AdlerQA team privately at:

- **Email:** info@adlerdev.in
- Alternatively, use GitHub's **"Report a vulnerability"** button on the
  repository's *Security* tab (private vulnerability reporting).

Please include, to the extent you can:

- A description of the issue and its impact
- Steps to reproduce (a minimal proof-of-concept is ideal)
- The affected version, commit SHA, or Docker image tag
- Any suggested mitigation

You do **not** need to have a fix ready. A clear reproduction is enough.

## What to expect

- We will acknowledge your report within **3 business days**.
- We aim to provide an initial assessment (severity, likely fix path) within
  **10 business days**.
- We will keep you updated as we work on a fix, and credit you in the release
  notes if you would like to be named.
- Please give us a reasonable window (typically 90 days, sooner for critical
  issues) to release a fix before publicly disclosing details.

## Scope

In scope:

- The wardenIQ FastAPI service (`app/`) and its frontend
- The default Docker Compose stack (`docker-compose.yml`, `config/`)
- Authentication, session handling, secret storage (`app/auth.py`,
  `app/crypto.py`), and the `auth_gateway` middleware
- Integrations that ship in this repo (GitHub, GitLab, Jira, SMTP, LLM
  providers)

Out of scope:

- Vulnerabilities in third-party services (report those upstream)
- Issues that require an attacker to already have host-level or database-level
  access
- Findings against a deployment that runs with the shipped placeholder
  `APP_SECRET` (rotate it — this is documented behavior, not a vulnerability)
- Missing best-practice HTTP headers on the dev server when
  `COOKIE_SECURE=false` (this is the local-dev default)

## Supported versions

wardenIQ is `v0.1.0-beta`. Security fixes are made against the `main` branch
and shipped in the next release. Please upgrade to the latest release before
reporting an issue if you can.

## Handling secrets in reports

Do **not** include real credentials, PATs, API keys, or customer data in your
report. If a reproduction requires a token, generate a throwaway one and
revoke it after sending.

Thank you.
