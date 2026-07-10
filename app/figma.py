"""Minimal Figma REST client (personal access token).

Figma's API requires a token — there is no supported way to read a design's content from a
bare public link. Given a token we fetch the file and flatten its screens/text into the compact
`summaries.figma` shape the prompt builder + validator already consume.
"""
import re

import httpx

_KEY_RE = re.compile(r"figma\.com/(?:file|design|proto)/([A-Za-z0-9]+)")


class Figma:
    API = "https://api.figma.com"

    def __init__(self, token: str):
        self.token = (token or "").strip()

    def ok(self) -> bool:
        return bool(self.token)

    @staticmethod
    def file_key_from_url(url: str):
        """Pull the file key from figma.com/file|design|proto/<KEY>/... or accept a bare key."""
        if not url:
            return None
        m = _KEY_RE.search(url)
        if m:
            return m.group(1)
        u = url.strip()
        return u if re.fullmatch(r"[A-Za-z0-9]{10,}", u) else None

    def _headers(self) -> dict:
        return {"X-Figma-Token": self.token}

    def get_file(self, key: str, depth: int | None = None) -> dict:
        """Fetch a file's node tree. `depth` limits how many levels are returned
        (depth=2 → pages + their top-level frames only), keeping the payload small
        for large designs; omit it to fetch the full tree."""
        params = {"depth": depth} if depth is not None else None
        r = httpx.get(f"{self.API}/v1/files/{key}", params=params,
                      headers=self._headers(), timeout=60.0)
        r.raise_for_status()
        return r.json()

    def get_nodes(self, key: str, ids: list) -> dict:
        """Fetch full subtrees for specific node ids: GET /v1/files/{key}/nodes?ids=…
        Returns {"nodes": {id: {"document": <node>}}}. Lets us pull only the screens
        we care about instead of the whole file."""
        r = httpx.get(f"{self.API}/v1/files/{key}/nodes",
                      params={"ids": ",".join(ids)},
                      headers=self._headers(), timeout=60.0)
        r.raise_for_status()
        return r.json()

    # top-level node types we treat as a "screen"
    SCREEN_TYPES = ("FRAME", "COMPONENT", "COMPONENT_SET", "INSTANCE")

    @classmethod
    def _screens_from_doc(cls, doc: dict) -> list:
        """Enumerate (id, name) for every top-level screen across all canvases."""
        out = []
        for canvas in (doc or {}).get("children") or []:
            for node in canvas.get("children") or []:
                if node.get("type") in cls.SCREEN_TYPES:
                    out.append((node.get("id"), node.get("name") or "screen"))
        return out

    def read_design(self, key: str, max_screens: int = 40, batch: int = 25) -> dict:
        """Efficient two-phase read that scales to many-screen files:

          1. GET the file at depth=2 → cheaply enumerate every screen (id + name)
             and the true total, without downloading the whole tree.
          2. GET /nodes for only the first `max_screens` screens (in batches) to
             pull their TEXT content.

        Falls back to a single full get_file if enumeration finds nothing.
        Returns the same {sampleScreens, textBlocks, totalScreens, …} shape as
        extract_summary so downstream consumers are unchanged."""
        shallow = self.get_file(key, depth=2)
        screens = self._screens_from_doc((shallow or {}).get("document") or {})
        total = len(screens)
        if not total:
            return self.extract_summary(self.get_file(key))
        picked = [(sid, name) for sid, name in screens[:max_screens] if sid]
        texts_by_id = {}
        ids = [sid for sid, _ in picked]
        for i in range(0, len(ids), batch):
            chunk = ids[i:i + batch]
            try:
                resp = self.get_nodes(key, chunk)
            except Exception:  # noqa: BLE001 — best effort per batch
                continue
            for nid, wrap in (resp.get("nodes") or {}).items():
                texts_by_id[nid] = self._texts_in((wrap or {}).get("document") or {})[:40]
        sample = [{"name": name, "textBlocks": texts_by_id.get(sid, []), "actions": []}
                  for sid, name in picked]
        all_text = [t for s in sample for t in s["textBlocks"]]
        return {
            "sampleScreens": sample[:30],
            "flows": [],
            "textBlocks": all_text[:200],
            "actions": [],
            "totalScreens": total,
            "fileName": (shallow or {}).get("name") or "",
        }

    @staticmethod
    def merge_summaries(summaries: list) -> dict | None:
        """Combine several design summaries (e.g. an explicit link + Figma links
        found inside a PDF) into one, keeping the same caps as a single design."""
        summaries = [s for s in summaries if s]
        if not summaries:
            return None
        if len(summaries) == 1:
            return summaries[0]
        screens, names = [], []
        for s in summaries:
            screens.extend(s.get("sampleScreens") or [])
            if s.get("fileName"):
                names.append(s["fileName"])
        all_text = [t for sc in screens for t in (sc.get("textBlocks") or [])]
        return {
            "sampleScreens": screens[:30],
            "flows": [],
            "textBlocks": all_text[:200],
            "actions": [],
            "totalScreens": sum(int(s.get("totalScreens") or 0) for s in summaries),
            "fileName": " + ".join(names) or "design",
        }

    @staticmethod
    def _texts_in(node) -> list:
        out = []

        def walk(n):
            if n.get("type") == "TEXT":
                s = " ".join((n.get("characters") or "").split())
                if s:
                    out.append(s)
            for c in n.get("children") or []:
                walk(c)

        walk(node)
        return out

    def extract_summary(self, file_json: dict) -> dict:
        """Flatten a Figma file into {sampleScreens, flows, textBlocks, actions, totalScreens}.

        Top-level frames/components on each canvas are treated as "screens"; their TEXT nodes
        become that screen's textBlocks. Matches what testgen/prompt_builder expects.
        """
        doc = (file_json or {}).get("document") or {}
        screens = []
        for canvas in doc.get("children") or []:
            for node in canvas.get("children") or []:
                if node.get("type") in ("FRAME", "COMPONENT", "COMPONENT_SET", "INSTANCE"):
                    tb = self._texts_in(node)
                    screens.append({"name": node.get("name") or "screen",
                                    "textBlocks": tb[:40], "actions": []})
        all_text = [t for s in screens for t in s["textBlocks"]]
        return {
            "sampleScreens": screens[:30],
            "flows": [],
            "textBlocks": all_text[:200],
            "actions": [],
            "totalScreens": len(screens),
            "fileName": (file_json or {}).get("name") or "",
        }
