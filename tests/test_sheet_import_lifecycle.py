import time
from types import SimpleNamespace

from bson import ObjectId

from store import Store


class FakeResult(SimpleNamespace):
    pass


def _matches(doc, query):
    for key, expected in (query or {}).items():
        actual = doc.get(key)
        if isinstance(expected, dict):
            if "$ne" in expected and actual == expected["$ne"]:
                return False
            if "$in" in expected and actual not in expected["$in"]:
                return False
            continue
        if actual != expected:
            return False
    return True


def _apply_update(doc, update):
    for key, value in update.get("$set", {}).items():
        doc[key] = value
    for key, value in update.get("$setOnInsert", {}).items():
        doc.setdefault(key, value)
    for key, value in update.get("$inc", {}).items():
        doc[key] = doc.get(key, 0) + value


class FakeCursor(list):
    def sort(self, key, direction=None):
        if isinstance(key, list):
            sort_keys = key
        else:
            sort_keys = [(key, direction or 1)]
        items = list(self)
        for field, dirn in reversed(sort_keys):
            items.sort(key=lambda d: d.get(field, 0), reverse=dirn == -1)
        return FakeCursor(items)

    def limit(self, n):
        return FakeCursor(self[:n])


class FakeCollection:
    def __init__(self, docs=None):
        self.docs = []
        for doc in docs or []:
            self.insert_one(doc)

    def insert_one(self, doc):
        doc = dict(doc)
        doc.setdefault("_id", ObjectId())
        self.docs.append(doc)
        return FakeResult(inserted_id=doc["_id"])

    def find_one(self, query=None, projection=None, sort=None):
        rows = [d for d in self.docs if _matches(d, query or {})]
        if sort:
            rows = list(FakeCursor(rows).sort(sort))
        return dict(rows[0]) if rows else None

    def find(self, query=None, projection=None):
        return FakeCursor(dict(d) for d in self.docs if _matches(d, query or {}))

    def update_one(self, query, update, upsert=False):
        for doc in self.docs:
            if _matches(doc, query):
                _apply_update(doc, update)
                return FakeResult(modified_count=1, deleted_count=0)
        if upsert:
            doc = dict(query)
            doc.setdefault("_id", ObjectId())
            _apply_update(doc, update)
            self.docs.append(doc)
            return FakeResult(upserted_id=doc["_id"], modified_count=0)
        return FakeResult(modified_count=0)

    def delete_one(self, query):
        before = len(self.docs)
        self.docs = [d for d in self.docs if not _matches(d, query)]
        return FakeResult(deleted_count=before - len(self.docs))

    def delete_many(self, query):
        before = len(self.docs)
        self.docs = [d for d in self.docs if not _matches(d, query)]
        return FakeResult(deleted_count=before - len(self.docs))

    def count_documents(self, query):
        return sum(1 for d in self.docs if _matches(d, query))

    def create_index(self, *args, **kwargs):
        return "idx"


class FakeDb(dict):
    def __getitem__(self, name):
        self.setdefault(name, FakeCollection())
        return dict.__getitem__(self, name)


def fake_store():
    s = Store.__new__(Store)
    s.db = FakeDb()
    s.features = s.db["features"]
    s.steps = s.db["test_steps"]
    s.cases = s.db["test_cases"]
    s.assoc = s.db["associations"]
    return s


def test_project_imported_row_promotes_match_status_on_later_match():
    s = fake_store()
    rid = s.upsert_project_imported_row(
        "p1", "hash-1", {"title": "stored"}, match_status="unmatched_pool",
        latest_score=0.11, latest_feature_id="f-old", needs_project_analysis=True)

    same = s.upsert_project_imported_row(
        "p1", "hash-1", {"title": "matched"}, match_status="matched_feature",
        latest_score=0.9, latest_feature_id="f-new", needs_project_analysis=False)

    row = s.get_project_imported_row(rid)
    assert same == rid
    assert row["current_match_status"] == "matched_feature"
    assert row["needs_project_analysis"] is False
    assert row["latest_relevance_feature_id"] == "f-new"
    assert row["times_seen"] == 2


def test_find_feature_import_by_signature_is_project_scoped_and_excludes_current():
    s = fake_store()
    old_id = s.create_feature_import({
        "project_id": "p1", "feature_id": "f1",
        "content_signature_sha256": "sig", "created_at": time.time() - 10})
    current_id = s.create_feature_import({
        "project_id": "p1", "feature_id": "f2",
        "content_signature_sha256": "sig"})

    dup = s.find_feature_import_by_signature("p1", sig="sig", exclude_id=current_id)

    assert dup["id"] == old_id


def test_unlink_imported_row_from_feature_keeps_project_memory():
    s = fake_store()
    row_id = s.upsert_project_imported_row("p1", "h1", {"title": "T"})
    case_id = str(ObjectId())
    s.cases.insert_one({"_id": ObjectId(case_id), "title": "T"})
    s.assoc.insert_one({"feature_id": "f1", "test_case_id": case_id})
    s.link_row_to_feature(row_id, "f1")
    s.record_row_promotion(row_id, "p1", "f1", 1, case_id, 0.9)

    result = s.unlink_imported_row_from_feature(row_id, "f1")

    assert result["removed_testcases"] == 1
    assert s.get_project_imported_row(row_id)
    assert s.project_imported_row_feature_map.count_documents({}) == 0
    assert s.project_imported_row_promotions.count_documents({}) == 0
    assert s.assoc.count_documents({"test_case_id": case_id}) == 0


def test_project_delete_keeps_upload_until_last_source_reference():
    s = fake_store()
    import_id = s.create_feature_import({"project_id": "p1", "feature_id": "f1"})
    row1 = s.upsert_project_imported_row("p1", "h1", {"title": "One"})
    row2 = s.upsert_project_imported_row("p1", "h2", {"title": "Two"})
    s.add_imported_row_source(row1, import_id, "b1", "f1", "a.csv", "Sheet1", 2)
    s.add_imported_row_source(row2, import_id, "b1", "f1", "a.csv", "Sheet1", 3)

    first = s.delete_imported_row_from_project("p1", row1)
    second = s.delete_imported_row_from_project("p1", row2)

    assert first["deleted_feature_import_ids"] == []
    assert second["deleted_feature_import_ids"] == [import_id]
    assert s.feature_imports.count_documents({"_id": ObjectId(import_id)}) == 0


def test_project_delete_unlinks_imported_promotions_without_deleting_shared_case():
    s = fake_store()
    import_id = s.create_feature_import({"project_id": "p1", "feature_id": "f1"})
    row_id = s.upsert_project_imported_row("p1", "h1", {"title": "Shared"})
    case_id = str(ObjectId())
    s.cases.insert_one({"_id": ObjectId(case_id), "title": "Shared"})
    s.assoc.insert_one({"feature_id": "f1", "test_case_id": case_id, "origin": "inherited"})
    s.assoc.insert_one({"feature_id": "f2", "test_case_id": case_id, "origin": "manual"})
    s.link_row_to_feature(row_id, "f1")
    s.record_row_promotion(row_id, "p1", "f1", 1, case_id, 0.9)
    s.add_imported_row_source(row_id, import_id, "b1", "f1", "a.csv", "Sheet1", 2)

    result = s.delete_imported_row_from_project("p1", row_id)

    assert result["removed_testcase_links"] == 1
    assert result["deleted_testcase_ids"] == []
    assert result["affected_feature_ids"] == ["f1"]
    assert s.case_exists(case_id)
    assert s.assoc.count_documents({"feature_id": "f1", "test_case_id": case_id}) == 0
    assert s.assoc.count_documents({"feature_id": "f2", "test_case_id": case_id}) == 1


def test_source_group_resolves_rows_for_permanent_sheet_delete():
    s = fake_store()
    import_id = s.create_feature_import({"project_id": "p1", "feature_id": "f1"})
    other_import_id = s.create_feature_import({"project_id": "p1", "feature_id": "f2"})
    row1 = s.upsert_project_imported_row("p1", "h1", {"title": "One"})
    row2 = s.upsert_project_imported_row("p1", "h2", {"title": "Two"})
    other_sheet_row = s.upsert_project_imported_row("p1", "h3", {"title": "Three"})
    other_project_row = s.upsert_project_imported_row("p2", "h4", {"title": "Four"})

    s.add_imported_row_source(row1, import_id, "b1", "f1", "suite.xlsx", "Login", 2)
    s.add_imported_row_source(row2, import_id, "b1", "f1", "suite.xlsx", "Login", 3)
    s.add_imported_row_source(
        other_sheet_row, other_import_id, "b2", "f2", "suite.xlsx", "Signup", 2)
    s.add_imported_row_source(
        other_project_row, import_id, "b1", "f3", "suite.xlsx", "Login", 4)

    row_ids = s.list_project_imported_row_ids_for_source(
        "p1", feature_import_id=import_id, sheet_name="Login")

    assert set(row_ids) == {row1, row2}


def test_project_library_rows_include_latest_source_metadata():
    s = fake_store()
    import_id = s.create_feature_import({"project_id": "p1", "feature_id": "f1"})
    row_id = s.upsert_project_imported_row("p1", "h1", {"title": "One"})
    s.add_imported_row_source(row_id, import_id, "b1", "f1", "suite.xlsx", "Login", 7)

    rows = s.list_project_imported_rows("p1", feature_id="f1")

    assert rows[0]["latest_source"]["feature_import_id"] == import_id
    assert rows[0]["latest_source"]["original_filename"] == "suite.xlsx"
    assert rows[0]["latest_source"]["sheet_name"] == "Login"
    assert rows[0]["latest_source"]["row_number"] == 7
