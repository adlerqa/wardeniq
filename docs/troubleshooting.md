# Troubleshooting

## Troubleshooting

- **I can't sign in / Forgot my password.**
  - **Via Web UI (Email or App Master Secret)**: Click **"Forgot password?"** on the sign-in screen.
    - **If SMTP is configured**: Enter your email address to receive a 6-digit reset code in your inbox.
    - **If SMTP is NOT configured (Docker image users)**: Enter username (`admin`), your container's **App Master Secret** (`APP_SECRET` from your container environment), and your new password to reset directly in your web browser.
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
