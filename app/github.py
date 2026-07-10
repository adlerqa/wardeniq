"""Minimal GitHub client (PAT auth) for watching PRs and opening PRs."""
import base64
import re
import httpx

_URL_RE = re.compile(r"github\.com[:/]+([^/]+)/([^/.]+)")


def parse_repo_url(url: str):
    """Accept https/ssh/owner-name forms → (owner, name)."""
    url = (url or "").strip()
    m = _URL_RE.search(url)
    if m:
        return m.group(1), m.group(2)
    if "/" in url and " " not in url:        # "owner/name"
        owner, name = url.split("/", 1)
        return owner.strip(), name.strip().removesuffix(".git")
    raise ValueError(f"could not parse repo URL: {url!r}")


class GitHub:
    def __init__(self, token: str, api_base: str = "https://api.github.com"):
        self.token = token
        self.api = api_base.rstrip("/")

    def _headers(self):
        h = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    def _get(self, path, params=None):
        r = httpx.get(f"{self.api}{path}", headers=self._headers(), params=params, timeout=30.0)
        r.raise_for_status()
        return r.json()

    def _post(self, path, body):
        r = httpx.post(f"{self.api}{path}", headers=self._headers(), json=body, timeout=30.0)
        r.raise_for_status()
        return r.json()

    def _put(self, path, body):
        r = httpx.put(f"{self.api}{path}", headers=self._headers(), json=body, timeout=30.0)
        r.raise_for_status()
        return r.json()

    # ---- write (Start Developing: branch + commit + PR) ----------------------
    def branch_sha(self, owner, name, branch):
        return self._get(f"/repos/{owner}/{name}/git/ref/heads/{branch}")["object"]["sha"]

    def create_branch(self, owner, name, new_branch, from_sha):
        return self._post(f"/repos/{owner}/{name}/git/refs",
                          {"ref": f"refs/heads/{new_branch}", "sha": from_sha})

    def put_file(self, owner, name, path, content_text, message, branch):
        b64 = base64.b64encode(content_text.encode()).decode()
        return self._put(f"/repos/{owner}/{name}/contents/{path}",
                         {"message": message, "content": b64, "branch": branch})

    def create_pull(self, owner, name, title, head, base, body):
        return self._post(f"/repos/{owner}/{name}/pulls",
                          {"title": title, "head": head, "base": base, "body": body})

    def list_pulls(self, owner, name, state="all", per_page=30):
        return self._get(f"/repos/{owner}/{name}/pulls",
                         {"state": state, "sort": "updated", "direction": "desc",
                          "per_page": per_page})

    def get_pull(self, owner, name, number):
        return self._get(f"/repos/{owner}/{name}/pulls/{number}")

    def list_branches(self, owner, name, per_page=100, pages=3):
        """Branch names for a repo (newest API order), paginated."""
        out = []
        for page in range(1, pages + 1):
            batch = self._get(f"/repos/{owner}/{name}/branches",
                              {"per_page": per_page, "page": page})
            if not batch:
                break
            out.extend(b.get("name") for b in batch if b.get("name"))
            if len(batch) < per_page:
                break
        return out

    def get_pull_files(self, owner, name, number, max_files=50):
        files = self._get(f"/repos/{owner}/{name}/pulls/{number}/files",
                          {"per_page": max_files})
        return [{"filename": f.get("filename"), "status": f.get("status"),
                 "additions": f.get("additions", 0), "deletions": f.get("deletions", 0),
                 "patch": (f.get("patch") or "")[:1500]} for f in files]

    def get_archive(self, owner, name, ref=""):
        """Download the repo branch tarball (follows GitHub's redirect to codeload)."""
        path = f"/repos/{owner}/{name}/tarball" + (f"/{ref}" if ref else "")
        r = httpx.get(f"{self.api}{path}", headers=self._headers(), timeout=180.0,
                      follow_redirects=True)
        r.raise_for_status()
        return r.content

    def list_commits(self, owner, name, since_iso, per_page=50, ref=""):
        params = {"since": since_iso, "per_page": per_page}
        if ref:
            params["sha"] = ref          # branch / tag / sha to list commits from
        return self._get(f"/repos/{owner}/{name}/commits", params)

    def get_commit(self, owner, name, sha, max_files=40):
        c = self._get(f"/repos/{owner}/{name}/commits/{sha}")
        files = c.get("files", [])[:max_files]
        return [{"filename": f.get("filename"), "status": f.get("status"),
                 "additions": f.get("additions", 0), "deletions": f.get("deletions", 0),
                 "patch": (f.get("patch") or "")[:1200]} for f in files]

    def list_user_repos(self, per_page=100, pages=3):
        """Repos the token can see (owner + collaborator + org member), newest first."""
        out = []
        for page in range(1, pages + 1):
            batch = self._get("/user/repos", {"per_page": per_page, "page": page,
                                              "sort": "updated", "affiliation":
                                              "owner,collaborator,organization_member"})
            if not batch:
                break
            for r in batch:
                out.append({"full_name": r.get("full_name"), "url": r.get("html_url"),
                            "private": r.get("private"), "default_branch": r.get("default_branch"),
                            "language": r.get("language")})
            if len(batch) < per_page:
                break
        return out

    def list_accessible_repos_page(self, page=1, per_page=30):
        """Paginated, one page per call — matches the Node UX (Tab → load page)."""
        batch = self._get("/user/repos", {"per_page": per_page, "page": page,
                                          "sort": "updated", "affiliation":
                                          "owner,collaborator,organization_member"})
        return [{"full_name": r.get("full_name"), "name": r.get("name"),
                 "owner": (r.get("owner") or {}).get("login"),
                 "private": r.get("private"),
                 "default_branch": r.get("default_branch"),
                 "language": r.get("language"),
                 "html_url": r.get("html_url")} for r in (batch or [])]

    def me(self):
        return self._get("/user")

    def rate_limit(self):
        try:
            return self._get("/rate_limit").get("resources", {}).get("core", {})
        except Exception as e:  # noqa: BLE001
            return {"error": str(e)}

    # ---- webhooks ------------------------------------------------------------
    def list_webhooks(self, owner, name):
        return self._get(f"/repos/{owner}/{name}/hooks") or []

    def register_pr_webhook(self, owner, name, webhook_url, secret):
        body = {"name": "web", "active": True, "events": ["pull_request"],
                "config": {"url": webhook_url, "content_type": "json",
                           "secret": secret, "insecure_ssl": "0"}}
        return self._post(f"/repos/{owner}/{name}/hooks", body)

    def update_pr_webhook(self, owner, name, hook_id, webhook_url, secret):
        body = {"active": True, "events": ["pull_request"],
                "config": {"url": webhook_url, "content_type": "json",
                           "secret": secret, "insecure_ssl": "0"}}
        r = httpx.patch(f"{self.api}/repos/{owner}/{name}/hooks/{hook_id}",
                        headers=self._headers(), json=body, timeout=30.0)
        r.raise_for_status()
        return r.json()

    def delete_webhook(self, owner, name, hook_id):
        r = httpx.delete(f"{self.api}/repos/{owner}/{name}/hooks/{hook_id}",
                         headers=self._headers(), timeout=30.0)
        # 404 is fine — already gone
        if r.status_code not in (200, 204, 404):
            r.raise_for_status()
        return True
