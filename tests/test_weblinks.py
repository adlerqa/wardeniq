"""Tests for link extraction + the SSRF-guarded crawler (pure logic, no network calls)."""
import extract as extractmod
import weblinks


class TestUrlAndHtmlExtraction:
    def test_urls_in_text(self):
        t = "See https://docs.example.com/a and (http://x.io/b). end."
        urls = extractmod.urls_in_text(t)
        assert "https://docs.example.com/a" in urls
        assert any(u.startswith("http://x.io/b") for u in urls)

    def test_extract_html_links_absolute_and_relative(self):
        html = ('<a href="https://a.com/x">x</a>'
                '<a href="/rel/y">y</a>'
                '<a href="mailto:z@a.com">z</a>')
        links = extractmod.extract_html_links(html, base_url="https://a.com/page")
        assert "https://a.com/x" in links
        assert "https://a.com/rel/y" in links      # resolved against base
        assert all(not l.startswith("mailto") for l in links)  # non-http dropped


class TestSsrfGuard:
    def test_blocks_private_and_loopback_ip_literals(self):
        for bad in ("http://127.0.0.1/x", "http://10.0.0.5/x",
                    "http://192.168.1.10", "http://169.254.169.254/latest/meta-data",
                    "http://[::1]/x", "http://0.0.0.0"):
            assert weblinks.is_safe_url(bad) is False, bad

    def test_blocks_non_http_schemes(self):
        assert weblinks.is_safe_url("ftp://example.com") is False
        assert weblinks.is_safe_url("file:///etc/passwd") is False
        assert weblinks.is_safe_url("not a url") is False

    def test_is_blocked_ip_helper(self):
        assert weblinks._is_blocked_ip("127.0.0.1") is True
        assert weblinks._is_blocked_ip("10.1.2.3") is True
        assert weblinks._is_blocked_ip("169.254.1.1") is True
        assert weblinks._is_blocked_ip("8.8.8.8") is False      # public
        assert weblinks._is_blocked_ip("not-an-ip") is True     # unparseable -> blocked


class TestCrawlGuards:
    def test_crawl_skips_unsafe_seeds_without_fetching(self, monkeypatch):
        # if a fetch were attempted it would raise; guard must prevent it
        def _boom(url):
            raise AssertionError("must not fetch unsafe url")
        monkeypatch.setattr(weblinks, "fetch_text", _boom)
        assert weblinks.crawl(["http://127.0.0.1/secret", "file:///etc/passwd"]) == []

    def test_crawl_respects_max_pages(self, monkeypatch):
        monkeypatch.setattr(weblinks, "is_safe_url", lambda u: True)
        monkeypatch.setattr(weblinks, "fetch_text",
                            lambda u: '<a href="https://x.io/next">n</a> hello world')
        out = weblinks.crawl(["https://x.io/a", "https://x.io/b", "https://x.io/c"],
                             depth=1, max_pages=2)
        assert len(out) == 2                       # capped
        assert all("text" in r and r["url"] for r in out)
