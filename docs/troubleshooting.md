# Troubleshooting

## Troubleshooting

- **The bundled local stack won't start on Docker Desktop, or `run.sh` refuses
  with a kernel error.** On a Linux kernel ≥ 6.19 (current Docker Desktop),
  MongoDB's `tcmalloc` allocator has a known startup failure, and there is
  currently no bundled MongoDB/mongot version combination that avoids it — this
  is an upstream MongoDB/mongot limitation, not something wardenIQ can fix on
  its own (tracked in [#27](https://github.com/adlerqa/wardeniq/issues/27)).
  Check your kernel with `docker info --format '{{.KernelVersion}}'`. The
  supported path if you're affected is an **external MongoDB** (Atlas M10+ or
  self-managed with `mongot`) instead of the bundled stack — see
  [Installation & deployment](installation.md#cloud--lightweight-deployment-recommended-for-real-use).
- **I can't sign in / Forgot my password.**
  - **Via Web UI (Email or App Master Secret)**: Click **"Forgot password?"** on the sign-in screen.
    - **If SMTP is configured**: Enter your email address to receive a 6-digit reset code in your inbox.
    - **If SMTP is NOT configured (Docker image users)**: Enter username (`admin`), your container's **App Master Secret** (`APP_SECRET` from your container environment), and your new password to reset directly in your web browser.
  - **Via a helper script (from the host, no `docker exec -it` needed)**: Run
    `./scripts/reset-admin-password.sh` (or
    `./scripts/reset-admin-password.sh "NewPassword123"` non-interactively). It
    works even if the app is still refusing to serve because search indexes
    failed to build — the admin account isn't gated on that.
  - **Via Docker CLI**: Run interactively inside the container:
    ```bash
    docker exec -it warden-app python reset_password.py
    ```
  - **Via Docker Environment Variable**: Set `RESET_ADMIN_PASSWORD="NewPassword123"` in your container environment to force-reset the password on container startup.
- **I'm the only admin and "Disable" doesn't show up on my own account.** That's by
  design — the sole active admin can't disable themselves (see
  [Signing in](#signing-in-the-very-first-time)). Use "Add admin to unlock" to invite
  a second admin first.
- **First start is slow or the page won't load.** Give it a few minutes — the replica set
  and model downloads take time on first run. Check progress with
  `docker compose logs -f` or the captured logs in `./logs/`.
- **Mind Map result is empty for a feature.** Usually the wrong **branch** is selected for
  a repo, or the logic lives only in test files (excluded on purpose). The Mind Map shows
  exactly which files it read, so you can tell which.
- **Test generation is slow or shallow.** The default local model is CPU-friendly, not
  powerful. Switch to a bigger local model or a hosted provider under Configuration → LLM.
- **Fresh start / wipe everything:** `./run.sh --reset` (deletes the data volumes) —
  on Windows, `powershell -ExecutionPolicy Bypass -File run.ps1 -Reset`.

---
