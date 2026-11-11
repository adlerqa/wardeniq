from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
import re
from typing import Any
import xml.etree.ElementTree as ET


class CoverageParseError(ValueError):
    """Raised when a coverage report is missing, malformed, or unsupported."""


@dataclass
class FileCoverage:
    path: str
    line_hits: dict[int, int] = field(default_factory=dict)
    branch_hits: dict[int, int] = field(default_factory=dict)
    lines_valid: int = 0
    lines_covered: int = 0
    branches_valid: int = 0
    branches_covered: int = 0

    def record_line(self, line_number: int, hits: int) -> None:
        try:
            line_number = int(line_number)
            hits = max(int(hits), 0)
        except (ValueError, TypeError) as exc:
            raise CoverageParseError(
                f"Invalid numeric line values: line={line_number!r}, hits={hits!r}"
            ) from exc

        if line_number not in self.line_hits:
            self.lines_valid += 1
            if hits > 0:
                self.lines_covered += 1
        elif hits > 0 and self.line_hits[line_number] <= 0:
            self.lines_covered += 1
        self.line_hits[line_number] = hits

    def record_branch(
        self,
        line_number: int,
        hits: int = 0,
        *,
        valid: int = 1,
        covered: int | None = None,
    ) -> None:
        try:
            line_number = int(line_number)
            hits = max(int(hits), 0)
            valid = max(int(valid), 0)
            if covered is None:
                cov = 1 if hits > 0 else 0
            else:
                cov = max(int(covered), 0)
        except (ValueError, TypeError) as exc:
            raise CoverageParseError(
                f"Invalid numeric branch values: line={line_number!r}, hits={hits!r}, valid={valid!r}, covered={covered!r}"
            ) from exc

        self.branches_valid += valid
        self.branches_covered += min(cov, valid)
        self.branch_hits[line_number] = max(self.branch_hits.get(line_number, 0), hits)

    @property
    def line_rate(self) -> float:
        return (self.lines_covered / self.lines_valid) if self.lines_valid else 0.0

    @property
    def branch_rate(self) -> float:
        return (self.branches_covered / self.branches_valid) if self.branches_valid else 0.0


@dataclass
class CoverageReport:
    files: list[FileCoverage]
    total_lines_override: int | None = field(default=None, repr=False)
    total_lines_covered_override: int | None = field(default=None, repr=False)
    total_branches_override: int | None = field(default=None, repr=False)
    total_branches_covered_override: int | None = field(default=None, repr=False)

    @property
    def files_by_path(self) -> dict[str, FileCoverage]:
        return {file_entry.path: file_entry for file_entry in self.files}

    @property
    def total_lines(self) -> int:
        if self.total_lines_override is not None:
            return self.total_lines_override
        return sum(file_entry.lines_valid for file_entry in self.files)

    @property
    def total_lines_covered(self) -> int:
        if self.total_lines_covered_override is not None:
            return self.total_lines_covered_override
        return sum(file_entry.lines_covered for file_entry in self.files)

    @property
    def total_branches(self) -> int:
        if self.total_branches_override is not None:
            return self.total_branches_override
        return sum(file_entry.branches_valid for file_entry in self.files)

    @property
    def total_branches_covered(self) -> int:
        if self.total_branches_covered_override is not None:
            return self.total_branches_covered_override
        return sum(file_entry.branches_covered for file_entry in self.files)

    @property
    def line_rate(self) -> float:
        return (self.total_lines_covered / self.total_lines) if self.total_lines else 0.0

    @property
    def branch_rate(self) -> float:
        return (self.total_branches_covered / self.total_branches) if self.total_branches else 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "files": [
                {
                    "path": file_entry.path,
                    "lines": file_entry.line_hits,
                    "branches": file_entry.branch_hits,
                    "lines_valid": file_entry.lines_valid,
                    "lines_covered": file_entry.lines_covered,
                    "branches_valid": file_entry.branches_valid,
                    "branches_covered": file_entry.branches_covered,
                }
                for file_entry in self.files
            ],
            "total_lines": self.total_lines,
            "total_lines_covered": self.total_lines_covered,
            "total_branches": self.total_branches,
            "total_branches_covered": self.total_branches_covered,
            "line_rate": self.line_rate,
            "branch_rate": self.branch_rate,
        }


def parse(path: str | Path) -> CoverageReport:
    report_path = Path(path)
    if not report_path.exists():
        raise CoverageParseError(f"Coverage report not found: {report_path}")

    try:
        text = report_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise CoverageParseError(f"Coverage report encoding error: {report_path} is not valid UTF-8") from exc
    except OSError as exc:
        raise CoverageParseError(f"Could not read coverage report: {report_path}") from exc

    if not text.strip():
        raise CoverageParseError(f"Coverage report is empty: {report_path}")

    trimmed = text.strip()
    if trimmed.startswith("TN:") or "end_of_record" in trimmed or "SF:" in trimmed:
        return _parse_lcov(trimmed)

    try:
        root = ET.fromstring(trimmed)
    except ET.ParseError as exc:
        raise CoverageParseError(f"Malformed coverage report: {report_path}") from exc

    tag = root.tag.lower()
    if tag == "coverage":
        return _parse_coverage_xml(root)
    if tag == "report":
        return _parse_jacoco_xml(root)
    if "cobertura" in tag or tag.endswith("coverage") or "line-rate" in trimmed.lower():
        return _parse_coverage_xml(root)
    if "jacoco" in trimmed.lower() or "sourcefile" in trimmed.lower():
        return _parse_jacoco_xml(root)

    raise CoverageParseError(f"Unsupported or malformed coverage report: {report_path}")


def _parse_condition_coverage(value: str) -> tuple[int, int] | None:
    match = re.search(r"\((\d+)\s*/\s*(\d+)\)", value)
    if match:
        cov = _to_int(match.group(1))
        val = _to_int(match.group(2))
        return cov, val
    pct_match = re.search(r"(\d+(?:\.\d+)?)%", value)
    if pct_match:
        pct = float(pct_match.group(1))
        val = 2
        cov = int(round(val * (pct / 100.0)))
        return cov, val
    return None


def _parse_lcov(text: str) -> CoverageReport:
    files: dict[str, FileCoverage] = {}
    current: FileCoverage | None = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("SF:"):
            path = _normalise_path(line[3:])
            current = files.setdefault(path, FileCoverage(path=path))
            continue
        if line == "end_of_record":
            current = None
            continue
        if current is None:
            continue
        if line.startswith("DA:"):
            data = line[3:]
            parts = [p.strip() for p in data.split(",")]
            if len(parts) < 2:
                raise CoverageParseError(f"Malformed LCOV line: {line}")
            try:
                line_no = _to_int(parts[0])
                hits = _to_int(parts[1])
            except CoverageParseError as exc:
                raise CoverageParseError(f"Malformed numeric value in LCOV line: {line}") from exc
            current.record_line(line_no, hits)
            continue
        if line.startswith("BRDA:"):
            data = line[5:]
            parts = [p.strip() for p in data.split(",")]
            if len(parts) < 4:
                raise CoverageParseError(f"Malformed LCOV branch line: {line}")
            try:
                line_no = _to_int(parts[0])
                hits_str = parts[3]
                if hits_str == "-":
                    hits = 0
                else:
                    hits = _to_int(hits_str)
            except CoverageParseError as exc:
                raise CoverageParseError(f"Malformed numeric value in LCOV branch line: {line}") from exc
            current.record_branch(line_no, hits)

    if not files:
        raise CoverageParseError("Coverage report contains no source files.")

    return CoverageReport(list(files.values()))


def _parse_coverage_xml(root: ET.Element) -> CoverageReport:
    files: dict[str, FileCoverage] = {}
    line_total = _to_int(root.get("lines-valid"), default=None)
    line_covered = _to_int(root.get("lines-covered"), default=None)
    branch_total = _to_int(root.get("branches-valid"), default=None)
    branch_covered = _to_int(root.get("branches-covered"), default=None)

    for class_node in root.findall(".//class"):
        raw_path = class_node.get("filename") or class_node.get("name")
        if not raw_path:
            continue
        file_path = _normalise_path(raw_path)
        file_entry = files.setdefault(file_path, FileCoverage(path=file_path))
        for line_node in class_node.findall("./lines/line"):
            line_no_raw = line_node.get("number")
            if line_no_raw is None:
                continue
            line_no = _to_int(line_no_raw)
            hits = _to_int(line_node.get("hits"), default=0)
            file_entry.record_line(line_no, hits)

            cond_cov = line_node.get("condition-coverage")
            conditions = line_node.findall("./conditions/condition")
            is_branch = line_node.get("branch") == "true" or conditions or cond_cov is not None

            if is_branch:
                if cond_cov:
                    parsed_cond = _parse_condition_coverage(cond_cov)
                    if parsed_cond is not None:
                        cov_branches, val_branches = parsed_cond
                        file_entry.record_branch(line_no, hits=hits, valid=val_branches, covered=cov_branches)
                    else:
                        file_entry.record_branch(line_no, hits=hits, valid=1, covered=1 if hits > 0 else 0)
                elif conditions:
                    valid_count = len(conditions)
                    total_pct = 0.0
                    for cond in conditions:
                        cov_attr = cond.get("coverage", "0%")
                        try:
                            pct_val = float(cov_attr.rstrip("%"))
                        except (ValueError, TypeError) as exc:
                            raise CoverageParseError(f"Invalid condition coverage value: {cov_attr!r}") from exc
                        total_pct += pct_val
                    cov_branches = int(total_pct / 100.0)
                    file_entry.record_branch(line_no, hits=hits, valid=valid_count, covered=cov_branches)
                else:
                    cov_branches = 1 if hits > 0 else 0
                    file_entry.record_branch(line_no, hits=hits, valid=1, covered=cov_branches)

    if not files:
        for package_node in root.findall(".//package"):
            for source_node in package_node.findall("./classes/class"):
                raw_path = source_node.get("filename") or source_node.get("name")
                if raw_path:
                    file_path = _normalise_path(raw_path)
                    files[file_path] = FileCoverage(path=file_path)

    if not files:
        raise CoverageParseError("Coverage XML contains no class entries.")

    for file_entry in files.values():
        if file_entry.lines_valid == 0 and file_entry.line_hits:
            file_entry.lines_valid = len(file_entry.line_hits)
            file_entry.lines_covered = sum(1 for hits in file_entry.line_hits.values() if hits > 0)

    return CoverageReport(
        list(files.values()),
        total_lines_override=line_total,
        total_lines_covered_override=line_covered,
        total_branches_override=branch_total,
        total_branches_covered_override=branch_covered,
    )


def _parse_jacoco_xml(root: ET.Element) -> CoverageReport:
    files: dict[str, FileCoverage] = {}
    line_total = None
    line_covered = None
    branch_total = None
    branch_covered = None

    for counter in root.findall("./counter"):
        kind = counter.get("type")
        missed = _to_int(counter.get("missed"), default=0)
        covered = _to_int(counter.get("covered"), default=0)
        if kind == "LINE":
            line_total = missed + covered
            line_covered = covered
        elif kind == "BRANCH":
            branch_total = missed + covered
            branch_covered = covered

    for package_node in root.findall(".//package"):
        package_name = package_node.get("name") or ""
        for source in package_node.findall("./sourcefile"):
            raw_path = source.get("name") or source.get("path")
            if not raw_path:
                continue
            if package_name and not raw_path.startswith(f"{package_name}/") and not raw_path.startswith(f"{package_name}\\"):
                file_path = _normalise_path(f"{package_name}/{raw_path}")
            else:
                file_path = _normalise_path(raw_path)
            file_entry = files.setdefault(file_path, FileCoverage(path=file_path))
            for line_node in source.findall("./line"):
                line_no_raw = line_node.get("nr")
                if line_no_raw is None:
                    continue
                line_no = _to_int(line_no_raw)
                hits = _to_int(line_node.get("ci"), default=0)
                file_entry.record_line(line_no, hits)
                cb = _to_int(line_node.get("cb"), default=0)
                mb = _to_int(line_node.get("mb"), default=0)
                branch_count = cb + mb
                if branch_count > 0:
                    file_entry.record_branch(line_no, hits=hits, valid=branch_count, covered=cb)

    if not files:
        raise CoverageParseError("JaCoCo XML contains no sourcefile entries.")

    return CoverageReport(
        list(files.values()),
        total_lines_override=line_total,
        total_lines_covered_override=line_covered,
        total_branches_override=branch_total,
        total_branches_covered_override=branch_covered,
    )


def _normalise_path(value: str) -> str:
    clean = value.strip().replace("\\", "/")
    if not clean:
        raise CoverageParseError("Coverage report contains an empty file path.")
    if len(clean) >= 2 and clean[1] == ":" and clean[0].isalpha():
        clean = clean[2:]
        if clean.startswith("/"):
            clean = clean[1:]
    pure = PurePosixPath(clean)
    if pure.is_absolute():
        segments = list(pure.parts)
        if segments and segments[0] in {"/", "\\"}:
            segments = segments[1:]
        clean = "/".join(segments)
    while clean.startswith("./"):
        clean = clean.removeprefix("./")
    clean = clean.strip("/")
    if not clean:
        raise CoverageParseError("Coverage report contains an empty file path.")
    return clean


def _to_int(value: str | None, default: int | None = 0) -> int | None:
    if value is None or value == "":
        return default
    try:
        return int(float(value)) if "%" not in value else int(float(value.rstrip("%")))
    except (TypeError, ValueError) as exc:
        raise CoverageParseError(f"Invalid numeric coverage value: {value!r}") from exc


__all__ = ["CoverageParseError", "CoverageReport", "FileCoverage", "parse"]
