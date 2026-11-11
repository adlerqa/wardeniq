"""Top-level re-export of coverage_reports for flat import resolution."""
from app.coverage_reports import (
    CoverageParseError,
    CoverageReport,
    FileCoverage,
    _normalise_path,
    parse,
)

__all__ = [
    "CoverageParseError",
    "CoverageReport",
    "FileCoverage",
    "_normalise_path",
    "parse",
]

