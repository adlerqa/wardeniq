"""PR coverage verdicts must cite numbered diff hunks that show the behaviour (#249 follow-up).

Found by running PR coverage on a real feature (e-commerce Product Search, seven generated
test cases written for the v2 search: `GET /api/v2/search`, `GET /api/v2/suggest`, a brand
filter, a sort control). Against PR #11, which implements the v1 search (`GET /v1/search`, a
text and category filter, nothing else), qwen2.5:3b marked five and llama3.2:3b marked all
seven cases covered. Against PR #12, the real v2 code, three models marked an invented
validation covered. Causes:

  * the model was shown only the first 6,000 characters of the diff (about 12% of PR #12; the
    route file was never in front of it)
  * "covered" was the model's word; its citation was checked only as "a file in the diff"
  * a case for `/api/v2/search` was matched to a PR that defines `/v1/search` by function name
  * a route written over several lines (`router.get(` then the path on the next line) was
    not recognised as a route at all

What is pinned here: the diff is split into numbered hunks, a batch is shown the hunks that
match ITS cases (a route hunk first), a verdict is held to the hunks it cites, and a case for
an endpoint the PR only defines under another API version is not implemented by that PR.
"""
import os
import sys

import pytest

APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../app"))
sys.path.insert(0, APP_DIR)

import coverage as cov  # noqa: E402
import grounding  # noqa: E402
import hunk_evidence as he  # noqa: E402
from conftest import FakeLLM  # noqa: E402

# Real hunks of the two route files (trimmed).
V2_ROUTES = """@@ -0,0 +1,26 @@
+import { Router, Request, Response } from "express";
+import { searchV2, suggest } from "../services/searchV2Service";
+
+const router = Router();
+
+router.get(
+  "/v2/search",
+  async (req: Request, res: Response): Promise<void> => {
+    const q = (req.query.q as string) || "";
+    const brandsParam = req.query.brands as string | string[] | undefined;
+    const sort = (req.query.sort as string) || "relevance";
+    const result = await searchV2(q, brands, sort, page);
+    res.status(200).json(result);
+  }
+);
+
+router.get(
+  "/v2/suggest",
+  async (req: Request, res: Response): Promise<void> => {
+    const q = (req.query.q as string) || "";
+    const result = await suggest(q);
+    res.status(200).json(result);
+  }
+);
+
+export default router;"""

V1_ROUTES = """@@ -0,0 +1,18 @@
+import { Router, Request, Response } from "express";
+import { search, listCategories } from "../services/searchService";
+
+const router = Router();
+
+router.get("/v1/search", async (req: Request, res: Response): Promise<void> => {
+  const q = (req.query.q as string) || "";
+  const category = req.query.category as string;
+  const result = await search(q, category, page);
+  res.status(200).json(result);
+});
+
+router.get("/v1/search/categories", async (_req: Request, res: Response): Promise<void> => {
+  const categories = await listCategories();
+  res.status(200).json(categories);
+});
+
+export default router;"""

ES_CONFIG = """@@ -0,0 +1,5 @@
+import { Client } from "@elastic/elasticsearch";
+export const getEsClient = () => new Client({ node: process.env.ES_URL });
+export const ensureIndex = async () => {
+  await getEsClient().indices.create({ index: "products" });
+};"""

SEED = """@@ -0,0 +1,2 @@
+export const brands = ["Apple", "Samsung", "Google"];
+export const seedProducts = [{ name: "iPhone", brand: "Apple" }, { name: "Galaxy", brand: "Samsung" }];"""


def pr_file(name, patch):
    return {"filename": name, "status": "added", "additions": patch.count("\n"), "deletions": 0, "patch": patch}


V2_FILES = [pr_file("backend/src/config/elasticsearch.ts", ES_CONFIG),
            pr_file("backend/src/routes/searchV2.ts", V2_ROUTES)]
V1_FILES = [pr_file("backend/src/routes/search.ts", V1_ROUTES)]


def case(cid, title, steps=()):
    return {"id": cid, "title": title, "type": "api", "steps": list(steps)}


SEARCH = case("c1", "GET /api/v2/search?q=phone&brands accepts a valid request",
              ["When GET /api/v2/search?q=phone&brands is called -> The response status is 200."])
SUGGEST = case("c6", "Suggestions return in <100ms when querying 'pho'",
               ["Given a GET request to /api/v2/suggest with q='pho' -> The API responds within <100ms."])
SORT_REQUIRED = case("c2", "The Sort By dropdown must have at least one selected option to apply sorting.",
                     ["The Sort By dropdown must have at least one selected option -> Sort by is required is shown."])
OTHER_BRANDS = case("c3", "The multi-brand filter for other brands must be unchecked to apply the filter.")


# ------------------------------------------------------------------ the words
class TestWords:
    @pytest.mark.parametrize("english,code", [
        ("suggestions", "suggest"), ("filtering", "filter"), ("filters", "filter"), ("caching", "cache"),
        ("queries", "query"), ("brands", "brand"), ("sorting", "sort"),
    ])
    def test_english_and_code_meet(self, english, code):
        assert he.code_words(english) == he.code_words(code)

    def test_identifiers_are_split(self):
        assert he.code_words("searchProducts") == {"search", "product"}
        assert he.code_words("get_search_history") == {"search", "history"}

    def test_filler_and_numbers_are_dropped(self):
        assert he.code_words("The response status is 200 and 100ms v2") == set()


# ------------------------------------------------------------------ the hunks
class TestSplitHunks:
    def test_hunks_are_numbered_in_file_order_with_their_lines(self):
        hunks = he.split_hunks(V2_FILES)
        assert [h["id"] for h in hunks] == ["H1", "H2"]
        assert hunks[1]["file"] == "backend/src/routes/searchV2.ts"
        assert (hunks[1]["start"], hunks[1]["end"]) == (1, 26)

    def test_several_hunks_in_one_file_keep_their_own_start_lines(self):
        patch = "@@ -1,2 +1,3 @@\n a\n+b\n c\n@@ -40,2 +41,3 @@\n x\n+y\n z"
        hunks = he.split_hunks([pr_file("src/a.ts", patch)])
        assert [(h["start"], h["end"]) for h in hunks] == [(1, 3), (41, 43)]

    def test_removed_lines_are_not_the_code(self):
        patch = "@@ -1,3 +1,3 @@\n keep\n-old()\n+fresh()\n tail"
        (hunk,) = he.split_hunks([pr_file("src/a.ts", patch)])
        assert "old()" in hunk["text"] and "old()" not in hunk["code"]
        assert "fresh()" in hunk["code"] and "keep" in hunk["code"]

    def test_a_long_hunk_is_cut_at_a_line(self):
        patch = "@@ -0,0 +1,200 @@\n" + "\n".join(f"+line number {i} of a long hunk" for i in range(200))
        hunks = he.split_hunks([pr_file("src/big.ts", patch)], max_chars=500)
        assert len(hunks) > 5
        assert all(len(h["text"]) <= 600 for h in hunks)
        assert hunks[1]["start"] == hunks[0]["end"] + 1          # no line lost or repeated

    def test_files_that_cannot_implement_behaviour_are_left_out(self):
        files = [pr_file("backend/src/scripts/seed.ts", SEED), pr_file("src/types/index.d.ts", "@@ -0,0 +1 @@\n+type A = {}"),
                 pr_file("backend/src/routes/searchV2.ts", V2_ROUTES)]
        assert {h["file"] for h in he.split_hunks(files)} == {"backend/src/routes/searchV2.ts"}

    def test_a_file_without_a_patch_is_skipped(self):
        assert he.split_hunks([{"filename": "a.png", "patch": None}, {"filename": "", "patch": "@@ -1 +1 @@\n+x"}]) == []

    def test_there_is_a_ceiling_on_the_number_of_hunks(self):
        patch = "\n".join(f"@@ -{i},1 +{i},1 @@\n+line {i} here" for i in range(1, 60))
        assert len(he.split_hunks([pr_file("src/a.ts", patch)], max_hunks=10)) == 10


# ------------------------------------------------------------------ which hunks are shown
class TestSelectHunks:
    def test_each_case_gets_the_hunks_that_match_it(self):
        hunks = he.split_hunks([*V2_FILES, pr_file("backend/src/models/Other.ts", "@@ -0,0 +1,3 @@\n+export const invoice = 1;\n+export const tax = 2;")])
        shown = he.select_hunks(hunks, [SEARCH], endpoints=he.diff_endpoints(V2_FILES))
        assert shown and shown[0]["file"] == "backend/src/routes/searchV2.ts"
        assert all(h["file"] != "backend/src/models/Other.ts" for h in shown)

    def test_the_route_a_case_names_is_always_shown_in_a_big_pr(self):
        # 40 files that sort before the route file, each with words the case shares ("search")
        noise = [pr_file(f"backend/src/a{i:02d}.ts", f"@@ -0,0 +1,12 @@\n" + "\n".join(
            f"+const searchOption{j}{i} = searchBox.search(query, brand);" for j in range(12))) for i in range(40)]
        hunks = he.split_hunks([*noise, *V2_FILES])
        endpoints = he.diff_endpoints(V2_FILES)
        shown = he.select_hunks(hunks, [SEARCH], endpoints=endpoints)
        assert any(h["file"] == "backend/src/routes/searchV2.ts" for h in shown)
        # the old behaviour: the first 6,000 characters of the diff never reached the route file
        first_6000 = "\n".join(f["patch"] for f in [*noise, *V2_FILES])[:6000]
        assert "/v2/search" not in first_6000

    def test_the_character_budget_is_respected(self):
        hunks = he.split_hunks([pr_file(f"src/f{i}.ts", "@@ -0,0 +1,20 @@\n" + "\n".join(
            f"+const searchBrand{j} = brand{i};" for j in range(20))) for i in range(30)])
        shown = he.select_hunks(hunks, [SEARCH, SORT_REQUIRED, OTHER_BRANDS], budget=2500)
        assert 0 < sum(len(h["text"]) for h in shown) <= 2500 + 400

    def test_a_word_rare_among_the_hunks_counts_for_more(self):
        common = pr_file("src/common.ts", "@@ -0,0 +1,3 @@\n+search search search\n+search query\n+search")
        rare = pr_file("src/rare.ts", "@@ -0,0 +1,2 @@\n+const samsung = apple;\n+search")
        hunks = he.split_hunks([common, rare])
        shown = he.select_hunks(hunks, [case("x", "Samsung and Apple search")], per_case=1)
        assert [h["file"] for h in shown] == ["src/rare.ts"]

    def test_nothing_related_shows_nothing(self):
        hunks = he.split_hunks([pr_file("src/a.ts", "@@ -0,0 +1,2 @@\n+const invoice = tax;")])
        assert he.select_hunks(hunks, [case("x", "Photographs of kittens")]) == []
        assert he.select_hunks([], [SEARCH]) == [] and he.select_hunks(hunks, []) == []
        assert "no changed code looks related" in he.render_hunks([])

    def test_the_block_numbers_the_hunks(self):
        block = he.render_hunks(he.split_hunks(V2_FILES))
        assert "[H2] backend/src/routes/searchV2.ts (new lines 1-26)" in block
        assert "cite these numbers" in block


# ------------------------------------------------------------------ routes
class TestEndpoints:
    def test_a_route_written_over_several_lines_is_found(self):
        eps = he.diff_endpoints(V2_FILES)
        assert {(e["method"], e["path"]) for e in eps} == {("GET", "/v2/search"), ("GET", "/v2/suggest")}

    def test_the_line_of_a_multi_line_route_is_the_line_of_the_call(self):
        eps = {e["path"]: e["line"] for e in grounding.extract_endpoints(V2_ROUTES, "searchV2.ts")}
        assert eps["/v2/search"] == 6 and eps["/v2/suggest"] == 17

    def test_single_line_routes_are_unchanged(self):
        assert {(e["method"], e["path"], e["line"]) for e in grounding.extract_endpoints(V1_ROUTES, "search.ts")} == \
            {("GET", "/v1/search", 6), ("GET", "/v1/search/categories", 13)}

    def test_a_router_mount_is_not_an_endpoint(self):
        patch = '@@ -0,0 +1,2 @@\n+app.use("/api", searchRoutes);\n+app.get("/health", ok);'
        paths = {e["path"] for e in he.diff_endpoints([pr_file("src/index.ts", patch)])}
        assert paths == {"/health"}

    @pytest.mark.parametrize("files,expected", [
        (V2_FILES, "aligned"),                   # /api/v2/search vs /v2/search
        (V1_FILES, "conflict"),                  # /api/v2/search vs /v1/search: another version
    ])
    def test_the_search_case_against_each_pr(self, files, expected):
        assert he.endpoint_status(SEARCH, he.diff_endpoints(files)) == expected

    def test_the_suggest_case_is_absent_from_the_v1_pr(self):
        # the v1 PR defines no suggest route at all (not a version difference)
        assert he.endpoint_status(SUGGEST, he.diff_endpoints(V1_FILES)) == "absent"

    def test_no_endpoint_named_or_no_routes_in_the_diff_is_unknown(self):
        assert he.endpoint_status(SORT_REQUIRED, he.diff_endpoints(V2_FILES)) == "unknown"
        assert he.endpoint_status(SEARCH, []) == "unknown"

    def test_a_different_method_is_not_a_version_conflict(self):
        post = case("p", "POST /api/v2/search creates a saved search")
        assert he.endpoint_status(post, he.diff_endpoints(V1_FILES)) == "absent"

    def test_path_parameters_still_align(self):
        patch = '@@ -0,0 +1,2 @@\n+router.get("/v2/items/:id", handler);'
        c = case("i", "GET /api/v2/items/42 returns the item")
        assert he.endpoint_status(c, he.diff_endpoints([pr_file("src/items.ts", patch)])) == "aligned"


# ------------------------------------------------------------------ citations and verdicts
HUNKS = he.split_hunks([*V2_FILES])
BY_ID = {h["id"]: h for h in HUNKS}
ROUTE = BY_ID["H2"]
CONFIG = BY_ID["H1"]
DF = he.document_frequency([SEARCH, SUGGEST, SORT_REQUIRED, OTHER_BRANDS])


class TestCitedHunks:
    @pytest.mark.parametrize("value", ["H2", "h2", 2, "2", " H 2 ", ["H2"], ["h2"], [2], "H2, H2"])
    def test_formats_models_use_are_understood(self, value):
        cited, unknown = he.cited_hunks({"hunks": value}, BY_ID)
        assert [h["id"] for h in cited] == ["H2"] and unknown == []

    def test_unknown_numbers_are_reported_not_trusted(self):
        cited, unknown = he.cited_hunks({"hunks": ["H2", "H99"]}, BY_ID)
        assert [h["id"] for h in cited] == ["H2"] and unknown == ["H99"]

    @pytest.mark.parametrize("value", [None, [], "", "none", ["nothing"]])
    def test_no_citation(self, value):
        assert he.cited_hunks({"hunks": value}, BY_ID) == ([], [])

    def test_at_most_three_count(self):
        many = {f"H{i}": {"id": f"H{i}"} for i in range(1, 7)}
        cited, _ = he.cited_hunks({"hunks": ["H1", "H2", "H3", "H4"]}, many)
        assert [h["id"] for h in cited] == ["H1", "H2", "H3"]


def verify(c, status, cited, files=V2_FILES, route=False):
    endpoints = he.diff_endpoints(files)
    return he.verify_verdict(c, status, cited, he.endpoint_status(c, endpoints), DF, 4,
                             route_hit=he.cites_route(c, endpoints, cited) or route)


class TestVerifyVerdict:
    def test_a_case_for_another_api_version_is_dropped_whatever_the_model_said(self):
        out = verify(SEARCH, "covered", [BY_ID["H1"]], files=V1_FILES)
        assert out["status"] is None and "another API version" in out["notes"][0]

    def test_the_route_a_case_names_backs_a_covered_verdict(self):
        assert verify(SEARCH, "covered", [ROUTE])["status"] == "covered"

    def test_covered_without_a_citation_is_partial_and_partial_stays_partial(self):
        assert verify(SEARCH, "covered", [])["status"] == "partial"
        assert verify(SEARCH, "partial", [])["status"] == "partial"
        assert verify(SEARCH, "covered", [])["notes"] == ["no changed hunk cited"]

    def test_hunks_about_something_else_drop_the_claim(self):
        # qwen2.5:3b / llama3.2:3b: "Sort by is required" credited to the elasticsearch config
        out = verify(SORT_REQUIRED, "covered", [CONFIG])
        assert out["status"] is None and out["notes"] == ["the cited hunks share almost nothing with the test case"]

    def test_too_little_in_common_caps_covered_at_partial(self):
        wordy = case("w", "Search suggestions return phone photo results quickly with brand colour pickers")
        out = he.verify_verdict(wordy, "covered", [ROUTE], "unknown", DF, 4)
        assert out["status"] == "partial" and "too little" in out["notes"][0]

    def test_a_case_whose_endpoint_the_pr_does_not_define_cannot_be_covered(self):
        orders = case("o", "GET /api/v2/orders lists the orders of a user")
        out = verify(orders, "covered", [ROUTE], route=True)
        assert out["status"] == "partial" and "does not define" in out["notes"][0]

    def test_a_verdict_is_never_stronger_than_the_models(self):
        assert verify(SEARCH, "partial", [ROUTE])["status"] == "partial"

    def test_a_case_with_no_words_is_not_judged_on_words(self):
        empty = case("e", "OK")
        assert he.verify_verdict(empty, "covered", [CONFIG], "unknown", DF, 4)["status"] == "covered"


# ------------------------------------------------------------------ verify_pr_implementation
def citing_llm(verdicts):
    """A model that answers with `verdicts`; each is (case id, status, which hunk file it cites)."""
    import re

    def handler(system, user):
        shown = {m.group(2): m.group(1) for m in re.finditer(r"\[(H\d+)\] (\S+) \(new lines", user)}
        out = []
        for cid, status, file_part in verdicts:
            ids = [hid for path, hid in shown.items() if file_part and file_part in path]
            out.append({"test_case_id": cid, "status": status, "confidence": 0.8,
                        "rationale": "`searchV2` handles it", "hunks": ids[:1]})
        return {"covered": out}
    return FakeLLM(handler=handler)


class TestVerifyPrImplementation:
    def noisy(self):
        """Production files that sort BEFORE the route file and fill the old 6,000 characters."""
        return [pr_file(f"backend/src/a{i:02d}.ts", "@@ -0,0 +1,12 @@\n" + "\n".join(
            f"+const searchOption{j}{i} = searchBox.query(brand);" for j in range(12))) for i in range(40)]

    def test_the_prompt_shows_the_route_hunk_of_a_big_pr_with_numbers(self):
        llm = citing_llm([])
        cov.verify_pr_implementation(llm, {"number": 12, "title": "v2"}, [*self.noisy(), *V2_FILES], [SEARCH])
        prompt = llm.calls[0]["user"]
        assert "CHANGED CODE, as numbered hunks" in prompt
        assert "backend/src/routes/searchV2.ts" in prompt and '"/v2/search"' in prompt
        assert 'the numbers of the 1 to 3 hunks that show the behaviour' in prompt

    def test_a_covered_verdict_citing_the_route_hunk_stays_covered(self):
        llm = citing_llm([("c1", "covered", "routes/searchV2.ts")])
        out = cov.verify_pr_implementation(llm, {"number": 12}, V2_FILES, [SEARCH, SUGGEST])
        (item,) = out["covered"]
        assert item["status"] == "covered" and item["hunks"] and item["files"] == ["backend/src/routes/searchV2.ts"]

    def test_an_invented_validation_credited_to_unrelated_code_is_dropped(self):
        llm = citing_llm([("c2", "covered", "config/elasticsearch.ts")])
        out = cov.verify_pr_implementation(llm, {"number": 12}, V2_FILES, [SORT_REQUIRED, SEARCH])
        # the config hunk is not even offered for this case, so the claim cites nothing real:
        # it cannot stay covered (the relevance drop itself is pinned in TestVerifyVerdict)
        assert all(item["status"] != "covered" for item in out["covered"])

    def test_the_v1_pr_does_not_cover_the_v2_search_case(self):
        llm = citing_llm([("c1", "covered", "routes/search.ts")])
        out = cov.verify_pr_implementation(llm, {"number": 11}, V1_FILES, [SEARCH])
        assert out["covered"] == []

    def test_an_unshown_hunk_number_is_rejected_and_the_claim_cannot_be_covered(self):
        llm = FakeLLM(response={"covered": [{"test_case_id": "c1", "status": "covered", "hunks": ["H77"]}]})
        out = cov.verify_pr_implementation(llm, {"number": 12}, V2_FILES, [SEARCH])
        (item,) = out["covered"]
        assert item["status"] == "partial" and item["hunks_rejected"] == ["H77"] and item["needs_review"] is True

    def test_the_hunk_stats_are_reported(self):
        llm = citing_llm([("c1", "covered", "routes/searchV2.ts")])
        out = cov.verify_pr_implementation(llm, {"number": 12}, V2_FILES, [SEARCH])
        assert out["grounding"]["hunks"] == {"hunks_total": 2, "dropped": 0, "capped": 0}


# ------------------------------------------------------------------ the worker
class TestPrCoverageWorker:
    def run(self, monkeypatch, files, llm, cases, keep_records=False):
        from workers import code_coverage_worker as worker

        saved = {}

        class FakeStore:
            def feature_test_case_ids(self, fid):
                return [c["id"] for c in cases]

            def cases_brief(self, ids):
                return cases

            def save_coverage(self, pr_id, fid, covered, dev_test_files, overall, notice=""):
                saved["covered"] = covered

            def get_repo(self, rid):
                return None

        monkeypatch.setattr(worker, "store", FakeStore())
        monkeypatch.setattr(worker, "current_llm", lambda: llm)
        monkeypatch.setattr(worker, "_fetch_repo_snapshot_files", lambda *a, **k: [])
        worker._pr_coverage("pr", {"number": 11, "title": "t", "repo_full_name": "o/r", "url": "u"}, files, "feature")
        if keep_records:
            return saved["covered"]
        return {c["test_case_id"]: c["status"] for c in saved["covered"]}

    def test_the_v1_pr_is_not_credited_with_the_v2_endpoint_even_when_the_model_says_covered(self, monkeypatch):
        search_products = [pr_file("backend/src/models/Search.ts",
                                   "@@ -0,0 +1,3 @@\n+export const searchProducts = async (query) => query;\n+export const getCategories = 1;")]
        llm = citing_llm([("c1", "covered", "routes/search.ts")])
        statuses = self.run(monkeypatch, [*V1_FILES, *search_products], llm, [SEARCH])
        assert "c1" not in statuses

    def test_the_v2_pr_still_gets_covered_for_its_own_endpoint(self, monkeypatch):
        llm = citing_llm([("c1", "covered", "routes/searchV2.ts")])
        statuses = self.run(monkeypatch, V2_FILES, llm, [SEARCH])
        assert statuses == {"c1": "covered"}

    def test_the_saved_record_names_the_hunks_the_verdict_rests_on(self, monkeypatch):
        llm = citing_llm([("c1", "covered", "routes/searchV2.ts")])
        saved = self.run(monkeypatch, V2_FILES, llm, [SEARCH], keep_records=True)
        assert saved[0]["hunks"] == ["H2"]
