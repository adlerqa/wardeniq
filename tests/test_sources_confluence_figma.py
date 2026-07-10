"""Unit tests for the Confluence + Figma ingestion helpers (pure logic, no network)."""
import extract as extractmod
import figma as figma_mod


# --------------------------------------------------------------------------- Confluence helpers
class TestConfluenceHelpers:
    def test_page_id_from_wiki_url(self):
        url = "https://acme.atlassian.net/wiki/spaces/ENG/pages/123456789/Checkout+Spec"
        assert extractmod.confluence_page_id_from_url(url) == "123456789"

    def test_page_id_from_pageid_query(self):
        url = "https://acme.atlassian.net/wiki/pages/viewpage.action?pageId=987654"
        assert extractmod.confluence_page_id_from_url(url) == "987654"

    def test_bare_numeric_id(self):
        assert extractmod.confluence_page_id_from_url("55512") == "55512"

    def test_no_id(self):
        assert extractmod.confluence_page_id_from_url("https://acme.atlassian.net/wiki/spaces/ENG") is None
        assert extractmod.confluence_page_id_from_url("") is None

    def test_html_to_text_strips_tags_and_keeps_lines(self):
        html = ("<h1>Checkout</h1><p>User can <b>pay</b> with a card.</p>"
                "<ul><li>Decline shows error</li><li>Success returns order_id</li></ul>"
                "<script>ignore()</script>")
        txt = extractmod.html_to_text(html)
        assert "Checkout" in txt
        assert "User can pay with a card." in txt
        assert "Decline shows error" in txt
        assert "ignore()" not in txt          # script content dropped

    def test_html_to_text_unescapes_entities(self):
        assert "A & B < C" in extractmod.html_to_text("<p>A &amp; B &lt; C</p>")

    def test_html_to_text_empty(self):
        assert extractmod.html_to_text("") == ""


# --------------------------------------------------------------------------- Figma client
class TestFigmaClient:
    def test_file_key_from_url_variants(self):
        assert figma_mod.Figma.file_key_from_url(
            "https://www.figma.com/file/abc123DEF/Checkout") == "abc123DEF"
        assert figma_mod.Figma.file_key_from_url(
            "https://figma.com/design/KEY9876/My-Flow?node-id=1-2") == "KEY9876"
        assert figma_mod.Figma.file_key_from_url("https://example.com/x") is None
        assert figma_mod.Figma.file_key_from_url("") is None

    def test_ok_requires_token(self):
        assert figma_mod.Figma("").ok() is False
        assert figma_mod.Figma("tok").ok() is True

    def test_extract_summary_flattens_screens_and_text(self):
        file_json = {
            "name": "Checkout Design",
            "document": {"children": [
                {"type": "CANVAS", "children": [
                    {"type": "FRAME", "name": "Login", "children": [
                        {"type": "TEXT", "characters": "Email"},
                        {"type": "TEXT", "characters": "Password"},
                        {"type": "GROUP", "children": [
                            {"type": "TEXT", "characters": "Sign in"}]},
                    ]},
                    {"type": "FRAME", "name": "Cart", "children": [
                        {"type": "TEXT", "characters": "Checkout"}]},
                    {"type": "RECTANGLE", "name": "bg"},   # not a screen, ignored
                ]},
            ]},
        }
        out = figma_mod.Figma("tok").extract_summary(file_json)
        assert out["fileName"] == "Checkout Design"
        assert out["totalScreens"] == 2
        names = {s["name"] for s in out["sampleScreens"]}
        assert names == {"Login", "Cart"}
        login = next(s for s in out["sampleScreens"] if s["name"] == "Login")
        assert login["textBlocks"] == ["Email", "Password", "Sign in"]   # nested TEXT found
        assert "Checkout" in out["textBlocks"]

    def test_extract_summary_empty_file(self):
        out = figma_mod.Figma("tok").extract_summary({})
        assert out["totalScreens"] == 0 and out["sampleScreens"] == []


# --------------------------------------------------------------------------- efficient read_design (#2)
class TestFigmaReadDesign:
    def test_two_phase_read_enumerates_then_fetches_nodes(self, monkeypatch):
        """depth=2 call enumerates screens; /nodes call fills in their text — no full-tree fetch."""
        fc = figma_mod.Figma("tok")
        # phase 1: shallow file (frames present, but their TEXT children are NOT returned at depth=2)
        shallow = {"name": "Checkout", "document": {"children": [
            {"type": "CANVAS", "children": [
                {"type": "FRAME", "id": "1:1", "name": "Login"},
                {"type": "FRAME", "id": "1:2", "name": "Cart"},
                {"type": "RECTANGLE", "id": "1:3", "name": "bg"},   # not a screen
            ]},
        ]}}
        # phase 2: /nodes returns the full subtree (with TEXT) for the requested ids
        node_resp = {"nodes": {
            "1:1": {"document": {"type": "FRAME", "name": "Login", "children": [
                {"type": "TEXT", "characters": "Email"},
                {"type": "TEXT", "characters": "Password"}]}},
            "1:2": {"document": {"type": "FRAME", "name": "Cart", "children": [
                {"type": "TEXT", "characters": "Checkout"}]}},
        }}
        calls = {}

        def fake_get_file(key, depth=None):
            calls["file_depth"] = depth
            return shallow

        def fake_get_nodes(key, ids):
            calls["node_ids"] = list(ids)
            return node_resp

        monkeypatch.setattr(fc, "get_file", fake_get_file)
        monkeypatch.setattr(fc, "get_nodes", fake_get_nodes)
        out = fc.read_design("KEY")
        assert calls["file_depth"] == 2                      # enumerated cheaply
        assert calls["node_ids"] == ["1:1", "1:2"]           # only real screens, not the rectangle
        assert out["totalScreens"] == 2
        login = next(s for s in out["sampleScreens"] if s["name"] == "Login")
        assert login["textBlocks"] == ["Email", "Password"]
        assert "Checkout" in out["textBlocks"]

    def test_read_design_falls_back_to_full_fetch_when_nothing_enumerated(self, monkeypatch):
        fc = figma_mod.Figma("tok")
        full = {"name": "Tiny", "document": {"children": [
            {"type": "CANVAS", "children": [
                {"type": "FRAME", "id": "9:9", "name": "Only", "children": [
                    {"type": "TEXT", "characters": "Hi"}]}]}]}}

        def fake_get_file(key, depth=None):
            return {"document": {"children": []}} if depth == 2 else full   # empty shallow → fallback

        monkeypatch.setattr(fc, "get_file", fake_get_file)
        out = fc.read_design("KEY")
        assert out["totalScreens"] == 1 and "Hi" in out["textBlocks"]


class TestFigmaMergeSummaries:
    def test_none_and_single(self):
        assert figma_mod.Figma.merge_summaries([]) is None
        one = {"sampleScreens": [{"name": "A", "textBlocks": ["x"]}], "textBlocks": ["x"],
               "totalScreens": 1, "fileName": "One"}
        assert figma_mod.Figma.merge_summaries([one, None]) is one

    def test_combines_screens_and_totals(self):
        a = {"sampleScreens": [{"name": "A", "textBlocks": ["a1"]}], "textBlocks": ["a1"],
             "totalScreens": 3, "fileName": "DesignA"}
        b = {"sampleScreens": [{"name": "B", "textBlocks": ["b1"]}], "textBlocks": ["b1"],
             "totalScreens": 5, "fileName": "DesignB"}
        out = figma_mod.Figma.merge_summaries([a, b])
        assert out["totalScreens"] == 8
        names = {s["name"] for s in out["sampleScreens"]}
        assert names == {"A", "B"}
        assert out["fileName"] == "DesignA + DesignB"
        assert "a1" in out["textBlocks"] and "b1" in out["textBlocks"]
