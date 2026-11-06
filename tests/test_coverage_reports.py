from pathlib import Path

import pytest

from app.coverage_reports import CoverageParseError, CoverageReport, parse

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "coverage"


def _assert_totals(report: CoverageReport):
    assert report.total_lines == 8
    assert report.total_lines_covered == 7
    assert report.total_branches == 4
    assert report.total_branches_covered == 3
    assert report.files_by_path["src/math_utils.py"].lines_covered == 3
    assert report.files_by_path["src/greet.py"].lines_covered == 4


@pytest.mark.parametrize("fixture", ["lcov.info", "cobertura.xml", "jacoco.xml", "coveragepy.xml"])
def test_parse_coverage_reports(fixture):
    report = parse(FIXTURE_DIR / fixture)
    _assert_totals(report)


def test_parse_unknown_reports_raises_coverage_parse_error(tmp_path):
    bad = tmp_path / "bad.txt"
    bad.write_text("not-a-coverage-report", encoding="utf-8")

    with pytest.raises(CoverageParseError, match="coverage"):
        parse(bad)
