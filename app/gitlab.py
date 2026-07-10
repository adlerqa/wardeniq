"""Minimal GitLab client (PAT auth) — mirrors the GitHub client surface so the
webhook + repo-picker flows look the same to callers."""
import re
import urllib.parse
import httpx

_URL_RE = re.compile(r"gitlab\.com[:/]+([^?#\s]+?)(?:\.git)?(?:[/?#]|$)")


def parse_repo_url(url: str):
    """Accept https/ssh/path/with/namespace forms → 'namespace/path' string."""
    url = (url or "").strip().rstrip("/")
    m = _URL_RE.search(url)
    if m:
        return m.group(1)
    if "/" in url and " " not in url:
        return url.removesuffix(".git")
    raise ValueError(f"could not parse GitLab project path: {url!r}")


class GitLab:
    def __init__(self, token: str, api_base: str = "https://gitlab.com/api/v4"):
        self.token = token
        self.api = api_base.rstrip("/")

    def _headers(self):
        h = {"Accept": "application/json"}
        if self.token:
            h["PRIVATE-TOKEN"] = self.token
        return h

    def _enc(self, path_with_namespace):
        return urllib.parse.quote(path_with_namespace, safe="")

    def _get(self, path, params=None):
        r = httpx.get(f"{self.api}{path}", headers=self._headers(),
                      params=params, timeout=30.0)
        r.raise_for_status()
        return r.json()

    def _post(self, path, body):
        r = httpx.post(f"{self.api}{path}", headers=self._headers(),
                       json=body, timeout=30.0)
        r.raise_for_status()
        return r.json()

    def me(self):
        return self._get("/user")

    def list_accessible_projects_page(self, page=1, per_page=30):
        params = {"membership": "true", "per_page": per_page, "page": page,
                  "order_by": "last_activity_at", "simple": "true"}
        batch = self._get("/projects", params)
        return [{"full_name": p.get("path_with_namespace"),
                 "name": p.get("name"),
                 "owner": (p.get("namespace") or {}).get("path"),
                 "private": p.get("visibility") != "public",
                 "default_branch": p.get("default_branch"),
                 "html_url": p.get("web_url")} for p in (batch or [])]

    # ---- webhooks ------------------------------------------------------------
    def list_webhooks(self, project_path):
        return self._get(f"/projects/{self._enc(project_path)}/hooks") or []

    def register_mr_webhook(self, project_path, webhook_url, secret):
        body = {"url": webhook_url, "merge_requests_events": True,
                "push_events": False, "token": secret}
        return self._post(f"/projects/{self._enc(project_path)}/hooks", body)

    def delete_webhook(self, project_path, hook_id):
        r = httpx.delete(f"{self.api}/projects/{self._enc(project_path)}/hooks/{hook_id}",
                         headers=self._headers(), timeout=30.0)
        if r.status_code not in (200, 204, 404):
            r.raise_for_status()
        return True

    # ---- MR / commits --------------------------------------------------------
    def get_mr(self, project_path, iid):
        return self._get(f"/projects/{self._enc(project_path)}/merge_requests/{iid}")

    def get_mr_changes(self, project_path, iid):
        return self._get(f"/projects/{self._enc(project_path)}/merge_requests/{iid}/changes")

    def branch_sha(self, project_path, branch):
        return self._get(
            f"/projects/{self._enc(project_path)}/repository/branches/{urllib.parse.quote(branch, safe='')}"
        )["commit"]["id"]

    def list_branches(self, project_path, per_page=100, pages=3):
        out = []
        for page in range(1, pages + 1):
            batch = self._get(
                f"/projects/{self._enc(project_path)}/repository/branches",
                {"per_page": per_page, "page": page},
            )
            if not batch:
                break
            out.extend(b.get("name") for b in batch if b.get("name"))
            if len(batch) < per_page:
                break
        return out

    def get_archive(self, project_path, ref=""):
        params = {"sha": ref} if ref else None
        r = httpx.get(
            f"{self.api}/projects/{self._enc(project_path)}/repository/archive.tar.gz",
            headers=self._headers(),
            params=params,
            timeout=180.0,
            follow_redirects=True,
        )
        r.raise_for_status()
        return r.content

    def list_commits(self, project_path, since_iso, per_page=50, ref=""):
        params = {"since": since_iso, "per_page": per_page}
        if ref:
            params["ref_name"] = ref
        commits = self._get(
            f"/projects/{self._enc(project_path)}/repository/commits",
            params,
        )
        out = []
        for c in commits or []:
            out.append({
                "sha": c.get("id"),
                "html_url": c.get("web_url"),
                "commit": {"message": c.get("title") or c.get("message") or ""},
            })
        return out

    def get_commit(self, project_path, sha, max_files=40):
        data = self._get(
            f"/projects/{self._enc(project_path)}/repository/commits/{urllib.parse.quote(sha, safe='')}/diff"
        )
        files = []
        for f in (data or [])[:max_files]:
            diff = (f.get("diff") or "")[:1200]
            adds = sum(1 for ln in diff.splitlines()
                       if ln.startswith("+") and not ln.startswith("+++"))
            dels = sum(1 for ln in diff.splitlines()
                       if ln.startswith("-") and not ln.startswith("---"))
            status = ("added" if f.get("new_file") else
                      "removed" if f.get("deleted_file") else
                      "renamed" if f.get("renamed_file") else
                      "modified")
            files.append({
                "filename": f.get("new_path") or f.get("old_path") or "",
                "status": status,
                "additions": adds,
                "deletions": dels,
                "patch": diff,
            })
        return files
