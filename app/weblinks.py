"""Opt-in, SSRF-guarded following of web links found in uploaded documents.

A PDF can embed links, and those pages link on to others. When the user opts in, the wardenIQ
server fetches those pages (depth-limited) and folds their text into the requirement corpus.

Safety (this fetches URLs from *untrusted* documents, so it is deliberately conservative):
  * http/https only; the host must resolve exclusively to PUBLIC IPs (blocks SSRF to
    localhost / 10.x / 192.168.x / 169.254.x / etc.).
  * redirects are NOT followed (a redirect could bounce to an internal address).
  * per-page size, request timeout, page-count and recursion-depth caps.
Everything is off unless the caller passes follow_links=true.
"""
import ipaddress
import os
import socket
from urllib.parse import urlparse

import httpx

from extract import extract_html_links, html_to_text

MAX_PAGES = int(os.getenv("LINK_FOLLOW_MAX_PAGES", "8"))
MAX_DEPTH = int(os.getenv("LINK_FOLLOW_DEPTH", "2"))
MAX_BYTES = int(os.getenv("LINK_FOLLOW_MAX_BYTES", "2000000"))
TIMEOUT = float(os.getenv("LINK_FOLLOW_TIMEOUT", "15"))


def _is_blocked_ip(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return True
    return (addr.is_private or addr.is_loopback or addr.is_link_local
            or addr.is_reserved or addr.is_multicast or addr.is_unspecified)


def is_safe_url(url: str) -> bool:
    """http/https + every resolved IP for the host must be public (SSRF guard)."""
    try:
        p = urlparse(url)
    except Exception:  # noqa: BLE001
        return False
    if p.scheme not in ("http", "https") or not p.hostname:
        return False
    port = p.port or (443 if p.scheme == "https" else 80)
    try:
        infos = socket.getaddrinfo(p.hostname, port, proto=socket.IPPROTO_TCP)
    except Exception:  # noqa: BLE001
        return False
    if not infos:
        return False
    return all(not _is_blocked_ip(info[4][0]) for info in infos)


def fetch_text(url: str) -> str:
    """Fetch an HTML/text page (no redirects, size-capped) and return plain text."""
    with httpx.stream("GET", url, timeout=TIMEOUT, follow_redirects=False,
                      headers={"User-Agent": "wardenIQ-link-follower"}) as r:
        r.raise_for_status()
        ctype = r.headers.get("content-type", "")
        if "html" not in ctype and "text" not in ctype:
            return ""
        chunks, total = [], 0
        for chunk in r.iter_bytes():
            chunks.append(chunk)
            total += len(chunk)
            if total > MAX_BYTES:
                break
        return b"".join(chunks).decode("utf-8", "replace")


def crawl(seed_urls, depth=None, max_pages=None) -> list:
    """Breadth-first, safety-guarded crawl. Returns [{url, html, text}] for reachable pages."""
    depth = MAX_DEPTH if depth is None else depth
    max_pages = MAX_PAGES if max_pages is None else max_pages
    seen, out = set(), []
    queue = [(u, 1) for u in (seed_urls or [])]
    while queue and len(out) < max_pages:
        url, d = queue.pop(0)
        if url in seen:
            continue
        seen.add(url)
        if not is_safe_url(url):
            continue
        try:
            html_str = fetch_text(url)
        except Exception:  # noqa: BLE001
            continue
        text = html_to_text(html_str)
        if text.strip():
            out.append({"url": url, "text": text})
        if d < depth and html_str:
            for link in extract_html_links(html_str, url):
                if link not in seen:
                    queue.append((link, d + 1))
    return out
