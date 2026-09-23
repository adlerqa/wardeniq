"""Issue #21: the Mind Map endpoint must explain an empty/never-succeeded result
instead of leaving the caller to infer it from a bare "not analyzed" flag.

project_mindmap() is a plain module-level function; called directly against a
fake store (the pattern CONTRIBUTING.md prefers for handler-level tests), no
FastAPI app or auth wiring needed.
"""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from api.routes.code_coverage import project_mindmap  # noqa: E402
import api.routes.code_coverage as code_coverage_module  # noqa: E402


class FakeStore:
    def __init__(self, features=None, code_coverage_docs=None, latest_job=None):
        self._features = features or []
        self._coverage = code_coverage_docs or {}
        self._latest_job = latest_job

    def list_features(self, pid):
        return self._features

    def get_code_coverage(self, fid):
        return self._coverage.get(fid)

    def latest_job(self, pid, jtype):
        return self._latest_job


class MindmapEmptyStateTests(unittest.TestCase):
    def setUp(self):
        self._real_store = code_coverage_module.store

    def tearDown(self):
        code_coverage_module.store = self._real_store

    def _use(self, fake_store):
        code_coverage_module.store = fake_store

    def test_no_job_ever_run_has_no_last_analysis(self):
        self._use(FakeStore(features=[], latest_job=None))
        out = project_mindmap("p1")
        self.assertIsNone(out["last_analysis"])

    def test_running_job_does_not_surface_stale_last_analysis(self):
        self._use(FakeStore(features=[], latest_job={
            "status": "running", "updated_at": 123.0, "result": {},
        }))
        out = project_mindmap("p1")
        self.assertIsNone(out["last_analysis"])

    def test_completed_job_with_no_files_found_surfaces_note_and_per_repo(self):
        self._use(FakeStore(features=[], latest_job={
            "status": "succeeded",
            "updated_at": 123.0,
            "result": {
                "note": "only test/spec files found — connect the implementation "
                        "repo(s) to measure code coverage",
                "features_mapped": 0,
                "per_repo": [{
                    "repo": "acme/api", "branch": "main",
                    "files_in_repo": 42, "impl_files": 0,
                    "test_files": 42, "non_impl_files": 0,
                }],
                "errors": [],
            },
        }))
        out = project_mindmap("p1")
        self.assertIsNotNone(out["last_analysis"])
        la = out["last_analysis"]
        self.assertEqual(0, la["features_mapped"])
        self.assertIn("test/spec files found", la["note"])
        self.assertEqual("main", la["per_repo"][0]["branch"])
        self.assertEqual(42, la["per_repo"][0]["files_in_repo"])
        self.assertEqual(0, la["per_repo"][0]["impl_files"])

    def test_feature_reviewed_but_all_uncovered_is_distinguishable_from_nothing_found(self):
        # "found code, judged uncovered": analyzed True, reviewed_files non-empty,
        # every case uncovered -- this must be a DIFFERENT observable shape than
        # the no-files-found case above (analyzed False / reviewed_files empty),
        # so the frontend can render distinct messages for each.
        self._use(FakeStore(
            features=[{"id": "f1", "name": "Password reset", "version": 1, "case_count": 2}],
            code_coverage_docs={"f1": {
                "repos": ["acme/api"],
                "updated_at": 123.0,
                "result": {
                    "reviewed_files": ["acme/api:src/auth/reset.py"],
                    "cases": [
                        {"status": "uncovered", "title": "A"},
                        {"status": "uncovered", "title": "B"},
                    ],
                },
            }},
            latest_job={
                "status": "succeeded", "updated_at": 123.0,
                "result": {"features_mapped": 1, "note": None, "per_repo": [], "errors": []},
            },
        ))
        out = project_mindmap("p1")
        feature = out["features"][0]
        self.assertTrue(feature["analyzed"])
        self.assertTrue(feature["reviewed_files"])
        self.assertEqual(0, feature["counts"]["covered"])
        self.assertEqual(0, feature["counts"]["partial"])
        self.assertEqual(2, feature["counts"]["uncovered"])


if __name__ == "__main__":
    unittest.main()
