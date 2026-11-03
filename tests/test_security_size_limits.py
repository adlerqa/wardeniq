"""Size limits: capped upload reads (413), ZIP-bomb guard for .docx/.xlsx, and capped
streaming of repository archives."""
import asyncio
import io
import tarfile
import zipfile

import pytest
from fastapi import HTTPException

import extract
import size_limits
import sheet_import


class _Upload:
    def __init__(self, data, size=None):
        self._buf = io.BytesIO(data)
        self.size = size
        self.filename = "f.txt"

    async def read(self, n=-1):
        return self._buf.read(n)


def test_read_upload_within_limit():
    assert asyncio.run(size_limits.read_upload(_Upload(b"x" * 100), max_bytes=100)) == b"x" * 100


def test_read_upload_over_limit_is_413_even_without_declared_size():
    with pytest.raises(HTTPException) as e:
        asyncio.run(size_limits.read_upload(_Upload(b"x" * (3 * size_limits.MB)),
                                            max_bytes=2 * size_limits.MB))
    assert e.value.status_code == 413


def test_read_upload_rejects_declared_oversize_without_reading():
    up = _Upload(b"", size=10 ** 12)
    with pytest.raises(HTTPException) as e:
        asyncio.run(size_limits.read_upload(up, max_bytes=1000))
    assert e.value.status_code == 413


def test_read_upload_many_enforces_total(monkeypatch):
    monkeypatch.setattr(size_limits, "MAX_UPLOAD_MB", 1)
    files = [_Upload(b"x" * (size_limits.MB - 10)) for _ in range(5)]
    with pytest.raises(HTTPException) as e:
        asyncio.run(size_limits.read_upload_many(files))
    assert e.value.status_code == 413


def _bomb(size):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("word/document.xml", b"\0" * size)
    return buf.getvalue()


def test_zip_bomb_docx_rejected_before_parsing(monkeypatch):
    monkeypatch.setattr(size_limits, "MAX_ARCHIVE_UNCOMPRESSED_MB", 4)
    with pytest.raises(extract.UnsupportedDocumentError):
        extract.extract_text("prd.docx", _bomb(8 * size_limits.MB))


def test_high_ratio_entry_rejected():
    with pytest.raises(size_limits.LimitExceeded):
        size_limits.check_zip_container(_bomb(4 * size_limits.MB), max_total=10 ** 9)


def _many_small_entries(n, size):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for i in range(n):
            z.writestr(f"word/part{i}.xml", b"\0" * size)      # each stays under the ratio check
    return buf.getvalue()


def test_too_many_entries_rejected(monkeypatch):
    monkeypatch.setattr(size_limits, "MAX_ZIP_ENTRIES", 3)
    with pytest.raises(size_limits.LimitExceeded, match="too many entries"):
        size_limits.check_zip_container(_many_small_entries(5, 10))
    size_limits.check_zip_container(_many_small_entries(3, 10))


def test_total_unpacked_size_cap_rejected():
    data = _many_small_entries(5, 100_000)                        # 500 KB unpacked in total
    with pytest.raises(size_limits.LimitExceeded, match="expands beyond"):
        size_limits.check_zip_container(data, max_total=300_000)
    size_limits.check_zip_container(data, max_total=600_000)


def test_zip_bomb_xlsx_rejected(monkeypatch):
    monkeypatch.setattr(size_limits, "MAX_ARCHIVE_UNCOMPRESSED_MB", 4)
    with pytest.raises(ValueError):
        sheet_import._parse_xlsx(_bomb(8 * size_limits.MB))
    with pytest.raises(ValueError):
        sheet_import.raw_tables(_bomb(8 * size_limits.MB), "x.xlsx")


def test_normal_xlsx_still_parses():
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Title", "Steps", "Expected"])
    ws.append(["Login works", "open page", "page shown"])
    buf = io.BytesIO()
    wb.save(buf)
    assert sheet_import.raw_tables(buf.getvalue(), "x.xlsx")


class _StreamResp:
    def __init__(self, chunks, headers=None, status=200):
        self._chunks = chunks
        self.headers = headers or {}
        self.status_code = status

    def raise_for_status(self):
        pass

    def iter_bytes(self):
        yield from self._chunks

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_download_capped_streams_to_file(monkeypatch):
    monkeypatch.setattr(size_limits.httpx, "stream",
                        lambda *a, **k: _StreamResp([b"ab", b"cd"]))
    f = size_limits.download_capped("https://x", max_bytes=10)
    assert f.read() == b"abcd"


def test_download_capped_aborts_past_cap(monkeypatch):
    monkeypatch.setattr(size_limits.httpx, "stream",
                        lambda *a, **k: _StreamResp([b"x" * 6, b"x" * 6]))
    with pytest.raises(size_limits.LimitExceeded):
        size_limits.download_capped("https://x", max_bytes=10)
    monkeypatch.setattr(size_limits.httpx, "stream",
                        lambda *a, **k: _StreamResp([], {"content-length": "999"}))
    with pytest.raises(size_limits.LimitExceeded):
        size_limits.download_capped("https://x", max_bytes=10)


def test_tar_readers_accept_file_objects():
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        data = b"def f():\n    return 1\n"
        info = tarfile.TarInfo("o-r-sha/src/app.py")
        info.size = len(data)
        tf.addfile(info, io.BytesIO(data))
    buf.seek(0)
    files = extract.source_files_from_tar(buf)
    assert files and files[0][0] == "src/app.py"


def test_github_get_archive_is_capped(monkeypatch):
    import github
    seen = {}

    def fake(url, **kw):
        seen["url"] = url
        return io.BytesIO(b"t")
    monkeypatch.setattr(github.size_limits, "download_capped", fake)
    assert github.GitHub("t").get_archive("o", "n", "main").read() == b"t"
    assert seen["url"].endswith("/repos/o/n/tarball/main")


def test_sheet_upload_over_limit_returns_413(monkeypatch):
    import auth
    import main
    from fastapi.testclient import TestClient
    main.store.add_audit = lambda *a, **kw: True
    user = {"id": "u1", "email": "u1@example.com", "role": "admin", "active": True,
            "session_version": 0, "all_projects": True}
    monkeypatch.setattr(main.store, "get_user", lambda uid: user)
    monkeypatch.setattr(main.store, "get_feature", lambda fid: {"id": fid, "project_id": "p1"})
    monkeypatch.setattr(size_limits, "MAX_UPLOAD_MB", 1)
    r = TestClient(main.app).post(
        "/api/projects/p1/features/f1/tests/import",
        cookies={auth.SESSION_COOKIE: auth.sign_session("u1", 0)},
        files={"file": ("big.csv", b"a," * size_limits.MB, "text/csv")})
    assert r.status_code == 413
