"""Unit tests for the grounded code-understanding layer (grounding.py).

Covers the Phase 1 primitives that make coverage/commit-analysis accurate and explainable:
diff line-number recovery, endpoint & symbol extraction, the no-hardcoded-domain guard,
endpoint alignment, confidence calibration, test-only detection, and fast cosine.
"""
import grounding as g


# --------------------------------------------------------------------------- diff parsing
class TestParseAddedLines:
    def test_recovers_new_file_line_numbers(self, sample_diff_patch):
        added = g.parse_added_lines(sample_diff_patch, "app/auth/login.py")
        # first added line is line 1 (the import); the decorator is the 4th line
        assert added[0][0] == 1
        assert "from fastapi" in added[0][1]
        deco_line = next(ln for ln, t in added if "@router.post" in t)
        assert deco_line == 4
        # line numbers are monotonically increasing
        nums = [ln for ln, _ in added]
        assert nums == sorted(nums)

    def test_empty_patch(self):
        assert g.parse_added_lines("", "x.py") == []


# --------------------------------------------------------------------------- endpoint extraction
class TestExtractEndpoints:
    def test_finds_decorator_route_with_line(self, sample_diff_patch):
        eps = g.extract_endpoints(sample_diff_patch, "app/auth/login.py")
        assert {"method": "POST", "path": "/api/login"} in [
            {"method": e["method"], "path": e["path"]} for e in eps]
        ep = next(e for e in eps if e["path"] == "/api/login")
        assert ep["line"] == 4 and ep["file"] == "app/auth/login.py"

    def test_ignores_non_path_method_calls(self):
        # obj.get('config_key') must NOT be read as an endpoint (no leading slash)
        patch = "@@ -0,0 +1,1 @@\n+    val = settings.get('config_key')\n"
        assert g.extract_endpoints(patch, "app/x.py") == []

    def test_express_and_go_styles(self):
        patch = ('@@ -0,0 +1,2 @@\n'
                 '+router.get("/users/:id", handler)\n'
                 '+mux.HandleFunc("/health", ping)\n')
        paths = {e["path"] for e in g.extract_endpoints(patch, "srv.go")}
        assert "/users/:id" in paths and "/health" in paths


# --------------------------------------------------------------------------- endpoint alignment
class TestEndpointsAlign:
    def test_exact(self):
        assert g.endpoints_align({"method": "POST", "path": "/api/login"},
                                 {"method": "POST", "path": "/api/login/"}) == "exact"

    def test_param_segments_match(self):
        assert g.endpoints_align({"method": "GET", "path": "/users/123"},
                                 {"method": "GET", "path": "/users/{id}"}) == "exact"

    def test_method_mismatch_is_none(self):
        assert g.endpoints_align({"method": "GET", "path": "/x"},
                                 {"method": "POST", "path": "/x"}) == "none"

    def test_any_method_is_wildcard(self):
        assert g.endpoints_align({"method": "ANY", "path": "/x"},
                                 {"method": "POST", "path": "/x"}) == "exact"

    def test_suffix_path_match(self):
        assert g.endpoints_align({"method": "GET", "path": "/api/v1/orders"},
                                 {"method": "GET", "path": "/orders"}) == "path"


# --------------------------------------------------------------------------- case endpoints
class TestCaseEndpoints:
    def test_extracts_method_and_path_from_steps(self, feature_with_cases):
        login = feature_with_cases["cases"][0]
        eps = g.case_endpoints(login)
        assert {"method": "POST", "path": "/api/login"} in eps


# --------------------------------------------------------------------------- symbols
class TestSymbols:
    def test_extract_from_diff_skips_generic(self, sample_diff_patch):
        names = {s["name"] for s in g.extract_symbols(sample_diff_patch, "app/auth/login.py")}
        assert "login" in names and "logout" in names

    def test_extract_from_diff_has_line_numbers(self, sample_diff_patch):
        syms = g.extract_symbols(sample_diff_patch, "app/auth/login.py")
        login = next(s for s in syms if s["name"] == "login")
        assert login["line"] == 5          # def login(payload) is the 5th line in the new file

    def test_extract_from_source_python(self):
        src = "def login(p):\n    return 1\n\nclass AuthService:\n    def check(self):\n        pass\n"
        out = g.extract_symbols_from_source(src, "auth.py")
        names = {s["name"] for s in out}
        assert "login" in names and "AuthService" in names

    def test_extract_from_source_go_fallback_or_treesitter(self):
        # whether tree-sitter-go is present or not, the regex fallback finds the func
        src = "package main\n\nfunc CalculateTotal(items []int) int {\n  return 0\n}\n"
        names = {s["name"] for s in g.extract_symbols_from_source(src, "calc.go")}
        assert "CalculateTotal" in names


# --------------------------------------------------------------------------- domain guard
class TestDomainGuard:
    def test_domain_tokens_from_title_and_steps(self):
        case = {"title": "Login with valid credentials",
                "steps": [{"action": "submit email and password", "expected": "session token"}]}
        toks = g.domain_tokens(case)
        assert "login" in toks and "credentials" in toks
        assert "with" not in toks       # stop-word removed

    def test_cross_domain_is_rejected(self):
        otp_case = {"title": "OTP code expires after 5 minutes", "steps": []}
        cart_signal = g.signal_tokens("addToCart", "/api/cart/items")
        assert g.tokens_overlap(g.domain_tokens(otp_case), cart_signal) is False

    def test_same_domain_overlaps(self):
        login_case = {"title": "Login issues a session", "steps": []}
        login_signal = g.signal_tokens("login", "/api/login")
        assert g.tokens_overlap(g.domain_tokens(login_case), login_signal) is True


# --------------------------------------------------------------------------- calibration
class TestCalibrate:
    def test_thresholds(self):
        assert g.calibrate(0.95) == "matched"
        assert g.calibrate(0.70) == "matched"
        assert g.calibrate(0.69) == "review_needed"
        assert g.calibrate(0.50) == "review_needed"
        assert g.calibrate(0.49) == "dropped"

    def test_bad_input_dropped(self):
        assert g.calibrate(None) == "dropped"
        assert g.calibrate("nan-ish") == "dropped"


# --------------------------------------------------------------------------- file classification
class TestFileClassification:
    def test_pr_with_impl_and_test_is_not_test_only(self, sample_pr_files):
        prod, test, infra = g.classify_diff_files(sample_pr_files)
        assert "app/auth/login.py" in prod
        assert "tests/test_login.py" in test
        assert g.is_test_only(sample_pr_files) is False

    def test_test_only_pr_detected(self):
        files = [{"filename": "tests/test_x.py"}, {"filename": "jest.config.js"}]
        assert g.is_test_only(files) is True

    def test_docs_only_change_is_not_test_only(self):
        assert g.is_test_only([{"filename": "README.md"}]) is False


# --------------------------------------------------------------------------- cosine
class TestStepFormatTolerance:
    """cases_brief() yields steps as 'action -> expected' strings; grounding must cope."""

    def test_string_steps_endpoints_and_tokens(self):
        case = {"id": "s1", "title": "Login", "steps": ["POST /api/login -> 200 and session token"]}
        assert {"method": "POST", "path": "/api/login"} in g.case_endpoints(case)
        assert "login" in g.domain_tokens(case)


class TestMatchCommitChanges:
    def _commit(self, patch, filename="app/auth/login.py", sha="abc123def456"):
        return [{"repo": "o/r", "sha": sha, "url": f"https://github.com/o/r/commit/{sha}",
                 "message": "add auth",
                 "files": [{"filename": filename, "status": "added",
                            "additions": 9, "deletions": 0, "patch": patch}]}]

    def test_endpoint_exact_match_with_evidence(self, sample_diff_patch, feature_with_cases):
        out = g.match_commit_changes(self._commit(sample_diff_patch), feature_with_cases["cases"])
        m = out["matches"]
        assert "c-login" in m
        assert m["c-login"]["tier"] == 1                  # endpoint exact beats symbol
        assert m["c-login"]["signal_type"] == "endpoint"
        assert m["c-login"]["status"] == "matched"
        ev = m["c-login"]["evidence"][0]
        assert ev["file"] == "app/auth/login.py" and ev["line"] == 4
        assert ev["sha"] == "abc123def456"
        assert ev["url"] == "https://github.com/o/r/commit/abc123def456"

    def test_symbol_tier_matches_logout(self, sample_diff_patch, feature_with_cases):
        # the diff adds `def logout(...)`; c-logout has no endpoint, so it matches by symbol
        m = g.match_commit_changes(self._commit(sample_diff_patch), feature_with_cases["cases"])["matches"]
        assert "c-logout" in m
        assert m["c-logout"]["signal_type"] == "symbol"
        assert m["c-logout"]["tier"] == 3

    def test_untouched_case_not_matched(self, sample_diff_patch, feature_with_cases):
        # nothing in the diff touches /api/account or a delete-account symbol
        m = g.match_commit_changes(self._commit(sample_diff_patch), feature_with_cases["cases"])["matches"]
        assert "c-delete" not in m

    def test_cross_domain_change_does_not_match(self):
        otp = {"id": "otp", "title": "OTP code expires after 5 minutes", "steps": []}
        patch = ('@@ -0,0 +1,2 @@\n'
                 '+@router.post("/api/cart/items")\n'
                 '+def add_to_cart(item):\n')
        out = g.match_commit_changes(self._commit(patch, "app/cart.py"), [otp])
        assert out["matched_ids"] == set()      # cart change must not flag an OTP case

    def test_test_files_are_not_evidence(self, sample_diff_patch, feature_with_cases):
        # same change but in a test file -> no grounded match
        commit = self._commit(sample_diff_patch, "tests/test_login.py")
        assert g.match_commit_changes(commit, feature_with_cases["cases"])["matched_ids"] == set()

    def test_generic_symbol_does_not_flood_the_suite(self):
        # 15 auth cases that all share the feature-wide word "session", plus 2 cart
        # cases. A changed `createSession` must NOT match all 15 (session is generic);
        # a changed `computeCartTotal` SHOULD match the 2 distinctive cart cases.
        cases = [{"id": f"a{i}", "title": f"Session token refresh scenario {i}",
                  "type": "api", "steps": []} for i in range(15)]
        cases += [{"id": "cart1", "title": "Cart total recalculated after removing item",
                   "type": "api", "steps": []},
                  {"id": "cart2", "title": "Cart total includes tax", "type": "api", "steps": []}]
        patch = ("@@ -0,0 +1,2 @@\n"
                 "+function createSession(user) { return db.sessions.insert(user); }\n"
                 "+function computeCartTotal(items) { return items.reduce((a,b)=>a+b,0); }\n")
        out = g.match_commit_changes(self._commit(patch, "src/app.js"), cases)
        m = out["matches"]
        # generic session symbol must not flood the 15 auth cases
        session_matches = [cid for cid, v in m.items() if v["signal"] == "createSession"]
        assert len(session_matches) <= 6, session_matches
        # distinctive cart symbol still catches the cart cases
        assert m.get("cart1", {}).get("signal") == "computeCartTotal"
        assert m.get("cart2", {}).get("signal") == "computeCartTotal"


class TestFeatureKeywords:
    def test_draws_from_name_requirement_and_titles(self):
        kws = g.feature_keywords(
            "User authentication",
            "Users sign in with email and password; logout supported.",
            ["Login issues a session", "Delete account"])
        assert "authentication" in kws        # from name
        assert "password" in kws              # from requirement
        assert "login" in kws and "account" in kws   # from case titles

    def test_name_tokens_rank_first(self):
        kws = g.feature_keywords("Checkout", "cart cart cart payment", ["pay now"])
        assert kws[0] == "checkout"           # name boost beats frequency

    def test_drops_stopwords_and_short_tokens(self):
        kws = g.feature_keywords("Reporting", "the api is up and ok", [])
        assert "the" not in kws and "api" not in kws   # stop-words
        assert "reporting" in kws


class TestDevTestedCases:
    def test_overlap_marks_case(self):
        cases = [{"id": "c-login", "title": "Login issues a session", "steps": []},
                 {"id": "c-cart", "title": "Add to cart", "steps": []}]
        assert g.dev_tested_cases(["tests/test_login.py"], cases) == {"c-login"}

    def test_no_files_is_empty(self):
        assert g.dev_tested_cases([], [{"id": "c1", "title": "Login", "steps": []}]) == set()

    def test_accepts_file_dicts(self):
        cases = [{"id": "c-login", "title": "Login flow", "steps": []}]
        assert g.dev_tested_cases([{"filename": "e2e/login.spec.ts"}], cases) == {"c-login"}


class TestHybridRetrieval:
    def test_bm25_surfaces_exact_identifier_match(self):
        # chunk 1 is the only one mentioning the endpoint/handler; with uninformative embeddings
        # (the weak-local-model case), lexical BM25 should decide and surface it first.
        texts = ["utils for formatting dates and numbers",
                 "app.post('/api/login') def login(): return issue_session()",
                 "cart totals and pricing helpers"]
        vecs = [[0, 0, 0], [0, 0, 0], [0, 0, 0]]
        order = g.hybrid_rank_indices("POST /api/login login session", texts, [0, 0, 0], vecs, top_k=3)
        assert order.index(1) < order.index(2)   # login chunk beats the irrelevant cart chunk
        assert 1 in order[:2]                     # and lands in the top results

    def test_falls_back_without_vectors(self):
        texts = ["login handler", "cart page"]
        order = g.hybrid_rank_indices("login", texts, None, None, top_k=2)
        assert order[0] == 0

    def test_empty(self):
        assert g.hybrid_rank_indices("q", [], None, None) == []


class TestFunctionChunking:
    def test_splits_python_into_function_bodies(self):
        src = ("import os\n\n"
               "@router.post('/api/login')\n"
               "def login(p):\n    return issue_session(p)\n\n"
               "def logout(s):\n    return revoke(s)\n")
        chunks = g.chunk_code_by_function(src, "auth.py")
        joined = "\n---\n".join(chunks)
        # each function body present, and the module-level route decorator/import preserved
        assert any("def login" in c and "issue_session" in c for c in chunks)
        assert any("def logout" in c for c in chunks)
        assert "import os" in joined

    def test_fallback_for_unknown_language(self):
        chunks = g.chunk_code_by_function("key: value\nother: 1\n", "config.yaml")
        assert chunks and "key: value" in "\n".join(chunks)


class TestCosine:
    def test_cosine_basic(self):
        assert g.cosine([1, 0, 0], [1, 0, 0]) == 1.0
        assert g.cosine([1, 0], [0, 1]) == 0.0
        assert g.cosine([0, 0], [1, 1]) == 0.0   # zero vector guard

    def test_rank_by_cosine_orders_results(self):
        q = [1.0, 0.0]
        vecs = [[0.0, 1.0], [0.9, 0.1], [1.0, 0.0]]
        ranked = g.rank_by_cosine(q, vecs, top_k=2)
        assert ranked[0] == 2          # identical vector ranks first
        assert ranked[1] == 1          # next-closest second
