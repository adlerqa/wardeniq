import os
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_OLD_CWD = Path.cwd()
try:
    os.chdir(_ROOT / "app")
    import main
finally:
    os.chdir(_OLD_CWD)


class FakeStoreForPromotion:
    def __init__(self):
        self.associated = []
        self.linked = []
        self.recorded = []
        self.created = []

    def get_row_promotion(self, row_id, feature_id=None):
        if feature_id:
            return None
        return {"promoted_testcase_id": "64f000000000000000000001",
                "feature_id": "source-feature"}

    def case_exists(self, case_id):
        return case_id == "64f000000000000000000001"

    def associate(self, feature_id, case_id, origin, score=None):
        self.associated.append((feature_id, case_id, origin, score))

    def link_row_to_feature(self, row_id, feature_id):
        self.linked.append((row_id, feature_id))

    def record_row_promotion(self, row_id, project_id, feature_id, version, case_id, score):
        self.recorded.append((row_id, project_id, feature_id, version, case_id, score))

    def get_feature(self, feature_id):
        return {"id": feature_id, "project_id": "p1", "version": 1}

    def find_case_by_identity(self, project_id, identity_hash=None, test_slug=None):
        return None

    def get_or_create_step(self, action, expected, emb, threshold):
        return {"step_id": f"step-{len(action)}"}

    def create_case(self, *args, **kwargs):
        self.created.append((args, kwargs))
        return "new-case"


class FakeStoreForImportDelete:
    def __init__(self):
        self.deleted = []

    def get_feature(self, feature_id):
        return {"id": feature_id, "project_id": "p1", "version": 1}

    def get_project_imported_row_by_hash(self, project_id, identity_hash):
        return None

    def get_project_imported_row(self, row_id):
        rows = {
            "row-1": {"id": "row-1", "project_id": "p1"},
            "row-2": {"id": "row-2", "project_id": "p1"},
            "row-other": {"id": "row-other", "project_id": "p2"},
        }
        return rows.get(row_id)

    def list_project_imported_row_ids_for_source(
        self, project_id, feature_import_id=None, original_filename=None,
        sheet_name=None
    ):
        assert project_id == "p1"
        assert feature_import_id == "import-1"
        assert original_filename == "suite.xlsx"
        assert sheet_name == "Login"
        return ["row-1", "row-2", "row-other"]

    def delete_imported_row_from_project(self, project_id, row_id):
        self.deleted.append((project_id, row_id))
        return {
            "deleted_testcase_ids": [f"case-{row_id}"],
            "removed_testcase_links": 1,
            "deleted_feature_import_ids": ["import-1"] if row_id == "row-2" else [],
            "affected_feature_ids": ["f1", "f2"],
        }

    def unlink_imported_row_from_feature(self, row_id, feature_id):
        raise AssertionError("permanent sheet delete must hard-delete rows")


def test_promote_imported_row_reuses_prior_promoted_case(monkeypatch):
    fake_store = FakeStoreForPromotion()
    monkeypatch.setattr(main, "store", fake_store)

    case_id = main._promote_imported_row_to_feature(
        "row-1",
        {"id": "target-feature", "project_id": "p1", "version": 3},
        {"title": "Imported login", "steps": ["Do it"], "identity_hash": "h1"},
        origin="inherited",
        score=0.91,
    )

    assert case_id == "64f000000000000000000001"
    assert fake_store.created == []
    assert fake_store.associated == [
        ("target-feature", "64f000000000000000000001", "inherited", 0.91)
    ]
    assert fake_store.linked == [("row-1", "target-feature")]
    assert fake_store.recorded == [
        ("row-1", "p1", "target-feature", 3, "64f000000000000000000001", 0.91)
    ]


def test_remove_imported_sheet_rows_expands_source_group_for_permanent_delete(monkeypatch):
    fake_store = FakeStoreForImportDelete()
    monkeypatch.setattr(main, "store", fake_store)

    result = main.remove_imported_sheet_rows(
        "f1",
        main.LibraryHashesIn(
            delete_from_system=True,
            feature_import_id="import-1",
            original_filename="suite.xlsx",
            sheet_name="Login",
        ),
    )

    assert fake_store.deleted == [("p1", "row-1"), ("p1", "row-2")]
    assert result["data"]["removed_count"] == 2
    assert result["data"]["removed_testcases"] == 2
    assert result["data"]["deleted_feature_imports"] == ["import-1"]
    assert result["data"]["affected_features"] == ["f1", "f2"]
