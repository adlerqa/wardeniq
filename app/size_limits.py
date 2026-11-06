"""Size limits for untrusted input: uploaded files, office archives (.docx/.xlsx are
ZIP containers) and downloaded repository archives.

- read_upload(): read an UploadFile in chunks, refusing anything over MAX_UPLOAD_MB
  with HTTP 413 instead of buffering an unbounded body.
- check_zip_container(): reject a ZIP-based document whose declared uncompressed size
  (or per-entry compression ratio, or entry count) is implausible, BEFORE a parser
  inflates it.
- download_capped(): stream an HTTP download into a temporary file (spooled to disk
  past a small threshold) with a byte cap, instead of holding it all in memory.
"""
import io
import tempfile
import zipfile

import httpx
from fastapi import HTTPException

from core.config import MAX_ARCHIVE_UNCOMPRESSED_MB, MAX_REPO_ARCHIVE_MB, MAX_UPLOAD_MB

MB = 1024 * 1024
_CHUNK = MB
# A legitimate office document compresses XML maybe 10-30x; anything wildly beyond
# that for a sizeable entry is a decompression bomb.
MAX_ZIP_RATIO = 200
MAX_ZIP_ENTRIES = 10000


class LimitExceeded(ValueError):
    """Input exceeds a configured size limit."""


async def read_upload(file, max_bytes: int | None = None) -> bytes:
    """Read an UploadFile fully, but never more than `max_bytes` (413 if larger)."""
    cap = max_bytes if max_bytes is not None else MAX_UPLOAD_MB * MB
    size = getattr(file, "size", None)
    if isinstance(size, int) and size > cap:
        raise HTTPException(413, f"File too large (limit {cap // MB} MB)")
    buf = io.BytesIO()
    while True:
        chunk = await file.read(_CHUNK)
        if not chunk:
            break
        if buf.tell() + len(chunk) > cap:
            raise HTTPException(413, f"File too large (limit {cap // MB} MB)")
        buf.write(chunk)
    return buf.getvalue()


async def read_upload_many(files, max_total: int | None = None):
    """[(UploadFile, bytes)] for every named file in `files`; each is capped at
    MAX_UPLOAD_MB and all of them together at 4x that (413 beyond)."""
    per_file = MAX_UPLOAD_MB * MB
    left = max_total if max_total is not None else 4 * per_file
    out = []
    for f in (files or []):
        if not f or not f.filename:
            continue
        if left <= 0:
            raise HTTPException(413, f"Uploads too large (limit {4 * MAX_UPLOAD_MB} MB in total)")
        try:
            data = await read_upload(f, max_bytes=min(per_file, left))
        except HTTPException as e:
            if e.status_code == 413 and left < per_file:
                raise HTTPException(
                    413, f"Uploads too large (limit {4 * MAX_UPLOAD_MB} MB in total)") from None
            raise
        left -= len(data)
        out.append((f, data))
    return out


def check_zip_container(data: bytes, max_total: int | None = None) -> None:
    """Raise LimitExceeded if a ZIP container would inflate beyond the limits. Data
    that isn't a readable ZIP is left for the real parser to reject."""
    cap = max_total if max_total is not None else MAX_ARCHIVE_UNCOMPRESSED_MB * MB
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except (zipfile.BadZipFile, OSError, ValueError):
        return
    with zf:
        infos = zf.infolist()
        if len(infos) > MAX_ZIP_ENTRIES:
            raise LimitExceeded("archive has too many entries")
        total = 0
        for info in infos:
            total += info.file_size
            if total > cap:
                raise LimitExceeded(
                    f"document expands beyond the {cap // MB} MB limit when unpacked")
            if info.file_size > MB and info.file_size > MAX_ZIP_RATIO * max(info.compress_size, 1):
                raise LimitExceeded("document has an implausible compression ratio")


def download_capped(url: str, *, headers=None, params=None, timeout: float = 180.0,
                    max_bytes: int | None = None, follow_redirects: bool = True):
    """GET `url` into a temporary file object (positioned at 0). Raises
    httpx.HTTPStatusError for HTTP errors and LimitExceeded past `max_bytes`."""
    cap = max_bytes if max_bytes is not None else MAX_REPO_ARCHIVE_MB * MB
    out = tempfile.SpooledTemporaryFile(max_size=8 * MB)
    try:
        with httpx.stream("GET", url, headers=headers, params=params, timeout=timeout,
                          follow_redirects=follow_redirects) as r:
            r.raise_for_status()
            declared = r.headers.get("content-length")
            if declared and declared.isdigit() and int(declared) > cap:
                raise LimitExceeded(f"archive larger than the {cap // MB} MB limit")
            total = 0
            for chunk in r.iter_bytes():
                total += len(chunk)
                if total > cap:
                    raise LimitExceeded(f"archive larger than the {cap // MB} MB limit")
                out.write(chunk)
        out.seek(0)
        return out
    except BaseException:
        out.close()
        raise


def as_fileobj(data):
    """bytes -> BytesIO; a file object is rewound and returned as-is."""
    if isinstance(data, (bytes, bytearray)):
        return io.BytesIO(data)
    try:
        data.seek(0)
    except Exception:  # noqa: BLE001
        pass
    return data
