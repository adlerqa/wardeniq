"""Minimal Jira Cloud REST client (email + API token basic auth)."""
import base64
import httpx


class Jira:
    def __init__(self, base_url: str, email: str, token: str):
        self.base = (base_url or "").strip().rstrip("/")
        self.email = (email or "").strip()
        self.token = (token or "").strip()

    def ok(self) -> bool:
        return bool(self.base and self.email and self.token)

    def _headers(self):
        raw = f"{self.email}:{self.token}".encode()
        return {"Authorization": "Basic " + base64.b64encode(raw).decode(),
                "Accept": "application/json", "Content-Type": "application/json"}

    def myself(self):
        r = httpx.get(f"{self.base}/rest/api/2/myself", headers=self._headers(), timeout=20.0)
        r.raise_for_status()
        return r.json()

    def get_issue(self, key):
        r = httpx.get(f"{self.base}/rest/api/2/issue/{key}", headers=self._headers(), timeout=20.0)
        r.raise_for_status()
        return r.json()

    def add_comment(self, key, body_text):
        r = httpx.post(f"{self.base}/rest/api/2/issue/{key}/comment",
                       headers=self._headers(), json={"body": body_text}, timeout=20.0)
        r.raise_for_status()
        return r.json()

    def list_projects(self, query=""):
        params = {"maxResults": 50, "orderBy": "name"}
        if query:
            params["query"] = query
        r = httpx.get(f"{self.base}/rest/api/3/project/search",
                      headers=self._headers(), params=params, timeout=20.0)
        r.raise_for_status()
        data = r.json() or {}
        return [{"key": p.get("key"), "name": p.get("name")} for p in (data.get("values") or [])]

    def list_project_issues(self, project_key: str, epics_only: bool = False):
        jql = f'project = "{project_key}"'
        if epics_only:
            jql += ' AND issuetype = Epic'
        jql += ' ORDER BY updated DESC'
        fields = "summary,issuetype,parent"
        r = httpx.get(
            f"{self.base}/rest/api/3/search/jql",
            headers=self._headers(),
            params={"jql": jql, "maxResults": 100, "fields": fields},
            timeout=20.0,
        )
        r.raise_for_status()
        data = r.json() or {}
        items = []
        for issue in (data.get("issues") or []):
            fields_data = issue.get("fields") or {}
            issue_type = (fields_data.get("issuetype") or {}).get("name") or ""
            parent = fields_data.get("parent") or {}
            parent_key = parent.get("key") or ""
            parent_summary = (parent.get("fields") or {}).get("summary") or ""
            items.append({
                "key": issue.get("key"),
                "summary": fields_data.get("summary") or issue.get("key") or "",
                "issue_type": issue_type,
                "parent_key": parent_key,
                "parent_summary": parent_summary,
            })
        return items

    def get_confluence_page(self, page_id):
        """Fetch a Confluence page's storage-format body. Returns {id, title, html}."""
        r = httpx.get(f"{self.base}/wiki/rest/api/content/{page_id}",
                      headers=self._headers(), params={"expand": "body.storage"}, timeout=20.0)
        r.raise_for_status()
        d = r.json() or {}
        return {"id": d.get("id"), "title": d.get("title"),
                "html": ((d.get("body") or {}).get("storage") or {}).get("value") or ""}

    def get_confluence_children(self, page_id, limit=25):
        """Direct child pages of a Confluence page (the 'sublinks')."""
        r = httpx.get(f"{self.base}/wiki/rest/api/content/{page_id}/child/page",
                      headers=self._headers(), params={"limit": limit}, timeout=20.0)
        r.raise_for_status()
        return [{"id": c.get("id"), "title": c.get("title")}
                for c in ((r.json() or {}).get("results") or [])]

    def list_project_epics(self, project_key: str):
        """Only Epics — used to populate the feature-association dropdown."""
        return self.list_project_issues(project_key, epics_only=True)

    def parent_epic(self, issue_key: str) -> str:
        """Resolve the Epic an issue belongs to (walks the parent chain a few
        levels). Returns the Epic key, or '' if none is found. If the issue
        itself IS an Epic, returns its own key."""
        if not issue_key:
            return ""
        try:
            key = issue_key
            seen = set()
            for _ in range(4):  # guard against parent cycles / deep hierarchies
                if not key or key in seen:
                    break
                seen.add(key)
                issue = self.get_issue(key)
                fields = issue.get("fields") or {}
                itype = ((fields.get("issuetype") or {}).get("name") or "").lower()
                if itype == "epic":
                    return issue.get("key") or key
                parent = fields.get("parent") or {}
                pkey = parent.get("key") or ""
                ptype = ((parent.get("fields") or {}).get("issuetype") or {}).get("name", "").lower()
                if pkey and ptype == "epic":
                    return pkey
                key = pkey
            return ""
        except Exception:  # noqa: BLE001
            return ""

    def list_confluence_spaces(self):
        """Confluence shares the Atlassian Cloud auth — base_url typically points to
        the Jira site. We use the wiki path on the same site."""
        if not self.ok():
            return []
        try:
            r = httpx.get(f"{self.base}/wiki/rest/api/space",
                          headers=self._headers(),
                          params={"limit": 50, "type": "global"}, timeout=20.0)
            r.raise_for_status()
            data = r.json() or {}
            return [{"key": s.get("key"), "name": s.get("name")}
                    for s in (data.get("results") or [])]
        except Exception:  # noqa: BLE001
            return []
