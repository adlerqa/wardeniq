from pathlib import Path

import pytest

from coverage_reports import (
    CoverageParseError,
    CoverageReport,
    FileCoverage,
    _normalise_path,
    parse,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "coverage"


def _assert_project_totals(report: CoverageReport):
    assert report.total_lines == 8
    assert report.total_lines_covered == 7
    assert report.total_branches == 4
    assert report.total_branches_covered == 3


def _assert_per_file_metrics(report: CoverageReport):
    assert "src/math_utils.py" in report.files_by_path
    assert "src/greet.py" in report.files_by_path

    math_file = report.files_by_path["src/math_utils.py"]
    assert math_file.lines_valid == 4
    assert math_file.lines_covered == 3
    assert math_file.branches_valid == 2
    assert math_file.branches_covered == 1

    greet_file = report.files_by_path["src/greet.py"]
    assert greet_file.lines_valid == 4
    assert greet_file.lines_covered == 4
    assert greet_file.branches_valid == 2
    assert greet_file.branches_covered == 2


@pytest.mark.parametrize("fixture", ["lcov.info", "cobertura.xml", "jacoco.xml", "coveragepy.xml"])
def test_parse_coverage_reports(fixture):
    report = parse(FIXTURE_DIR / fixture)
    _assert_project_totals(report)
    _assert_per_file_metrics(report)


def test_lcov_per_file_counts():
    report = parse(FIXTURE_DIR / "lcov.info")
    _assert_per_file_metrics(report)


def test_cobertura_per_file_counts():
    report = parse(FIXTURE_DIR / "cobertura.xml")
    _assert_per_file_metrics(report)


def test_jacoco_per_file_counts():
    report = parse(FIXTURE_DIR / "jacoco.xml")
    _assert_per_file_metrics(report)


def test_coveragepy_per_file_counts():
    report = parse(FIXTURE_DIR / "coveragepy.xml")
    _assert_per_file_metrics(report)


def test_cross_format_consistency():
    formats = ["lcov.info", "cobertura.xml", "jacoco.xml", "coveragepy.xml"]
    reports = {fmt: parse(FIXTURE_DIR / fmt) for fmt in formats}

    reference = reports["lcov.info"]
    ref_paths = sorted(reference.files_by_path.keys())

    for fmt, report in reports.items():
        assert sorted(report.files_by_path.keys()) == ref_paths, f"File paths mismatch in {fmt}"
        assert report.total_lines == reference.total_lines, f"Total lines mismatch in {fmt}"
        assert report.total_lines_covered == reference.total_lines_covered, f"Total lines covered mismatch in {fmt}"
        assert report.total_branches == reference.total_branches, f"Total branches mismatch in {fmt}"
        assert report.total_branches_covered == reference.total_branches_covered, f"Total branches covered mismatch in {fmt}"

        for path in ref_paths:
            ref_file = reference.files_by_path[path]
            file_entry = report.files_by_path[path]
            assert file_entry.lines_valid == ref_file.lines_valid, f"{fmt} {path} lines_valid mismatch"
            assert file_entry.lines_covered == ref_file.lines_covered, f"{fmt} {path} lines_covered mismatch"
            assert file_entry.branches_valid == ref_file.branches_valid, f"{fmt} {path} branches_valid mismatch"
            assert file_entry.branches_covered == ref_file.branches_covered, f"{fmt} {path} branches_covered mismatch"

        # Also assert the entire as_dict() structure matches the reference
        assert report.as_dict() == reference.as_dict(), f"{fmt} as_dict() mismatch"


def test_lcov_branch_dash_taken_count(tmp_path):
    lcov_content = (
        "TN:\n"
        "SF:src/example.py\n"
        "DA:1,1\n"
        "DA:2,0\n"
        "BRDA:1,0,0,1\n"
        "BRDA:1,0,1,-\n"
        "end_of_record\n"
    )
    p = tmp_path / "dash.info"
    p.write_text(lcov_content, encoding="utf-8")
    report = parse(p)
    file_entry = report.files_by_path["src/example.py"]
    assert file_entry.branches_valid == 2
    assert file_entry.branches_covered == 1


def test_lcov_da_checksum_field(tmp_path):
    lcov_content = (
        "TN:\n"
        "SF:src/example.py\n"
        "DA:1,1,3a5e1cf\n"
        "DA:2,0,98ef12a\n"
        "end_of_record\n"
    )
    p = tmp_path / "checksum.info"
    p.write_text(lcov_content, encoding="utf-8")
    report = parse(p)
    file_entry = report.files_by_path["src/example.py"]
    assert file_entry.lines_valid == 2
    assert file_entry.lines_covered == 1
    assert file_entry.line_hits[1] == 1
    assert file_entry.line_hits[2] == 0


def test_lcov_non_numeric_raises_coverage_parse_error(tmp_path):
    p = tmp_path / "bad_numeric.info"
    p.write_text("SF:src/foo.py\nDA:one,two\nend_of_record\n", encoding="utf-8")
    with pytest.raises(CoverageParseError):
        parse(p)

    p2 = tmp_path / "bad_branch_numeric.info"
    p2.write_text("SF:src/foo.py\nDA:1,1\nBRDA:1,0,0,notanumber\nend_of_record\n", encoding="utf-8")
    with pytest.raises(CoverageParseError):
        parse(p2)


def test_xml_non_numeric_raises_coverage_parse_error(tmp_path):
    bad_xml = (
        '<coverage line-rate="0.5" lines-valid="abc" lines-covered="1">'
        '  <packages><package name="p"><classes>'
        '    <class name="c" filename="foo.py"><lines><line number="1" hits="1"/></lines></class>'
        '  </classes></package></packages>'
        '</coverage>'
    )
    p = tmp_path / "bad_xml.xml"
    p.write_text(bad_xml, encoding="utf-8")
    with pytest.raises(CoverageParseError):
        parse(p)


def test_jacoco_non_numeric_raises_coverage_parse_error(tmp_path):
    bad_xml = (
        '<report name="r">'
        '  <package name="pkg">'
        '    <sourcefile name="foo.py">'
        '      <line nr="1" ci="bad" cb="0" mb="0"/>'
        '    </sourcefile>'
        '  </package>'
        '</report>'
    )
    p = tmp_path / "bad_jacoco.xml"
    p.write_text(bad_xml, encoding="utf-8")
    with pytest.raises(CoverageParseError):
        parse(p)


def test_non_utf8_input_raises_coverage_parse_error(tmp_path):
    bad_utf8 = tmp_path / "bad_encoding.info"
    bad_utf8.write_bytes(b"\xff\xfe\x00\x00\x80\x81")
    with pytest.raises(CoverageParseError, match="UTF-8"):
        parse(bad_utf8)


def test_parse_unknown_reports_raises_coverage_parse_error(tmp_path):
    bad = tmp_path / "bad.txt"
    bad.write_text("not-a-coverage-report", encoding="utf-8")
    with pytest.raises(CoverageParseError, match="coverage"):
        parse(bad)


def test_empty_coverage_file_raises_coverage_parse_error(tmp_path):
    empty = tmp_path / "empty.xml"
    empty.write_text("   \n  ", encoding="utf-8")
    with pytest.raises(CoverageParseError, match="empty"):
        parse(empty)


def test_missing_coverage_file_raises_coverage_parse_error(tmp_path):
    missing = tmp_path / "does_not_exist.xml"
    with pytest.raises(CoverageParseError, match="not found"):
        parse(missing)


def test_cobertura_partial_condition_not_fully_covered(tmp_path):
    xml_content = (
        '<coverage>'
        '  <packages><package name="src"><classes>'
        '    <class name="mod" filename="src/mod.py">'
        '      <lines>'
        '        <line number="1" hits="1" branch="true">'
        '          <conditions>'
        '            <condition number="0" type="jump" coverage="50%"/>'
        '            <condition number="1" type="jump" coverage="0%"/>'
        '          </conditions>'
        '        </line>'
        '      </lines>'
        '    </class>'
        '  </classes></package></packages>'
        '</coverage>'
    )
    p = tmp_path / "partial_cob.xml"
    p.write_text(xml_content, encoding="utf-8")
    report = parse(p)
    file_entry = report.files_by_path["src/mod.py"]
    assert file_entry.branches_valid == 2
    # 50% + 0% = 50% across 2 conditions -> 0 covered branches (not fully covered)
    assert file_entry.branches_covered == 0


def test_jacoco_branch_counts(tmp_path):
    xml_content = (
        '<report name="test">'
        '  <package name="src">'
        '    <sourcefile name="example.py">'
        '      <line nr="1" ci="1" mi="0" mb="1" cb="1"/>'
        '      <line nr="2" ci="1" mi="0" mb="0" cb="2"/>'
        '    </sourcefile>'
        '  </package>'
        '</report>'
    )
    p = tmp_path / "jacoco_test.xml"
    p.write_text(xml_content, encoding="utf-8")
    report = parse(p)
    file_entry = report.files_by_path["src/example.py"]
    assert file_entry.branches_valid == 4  # (1+1) + (0+2)
    assert file_entry.branches_covered == 3  # 1 + 2


def test_normalise_path():
    assert _normalise_path("./src/math_utils.py") == "src/math_utils.py"
    assert _normalise_path(".github/workflows/ci.yml") == ".github/workflows/ci.yml"
    assert _normalise_path("../parent/file.py") == "../parent/file.py"
    assert _normalise_path(".env") == ".env"
    assert _normalise_path("src\\math_utils.py") == "src/math_utils.py"
    assert _normalise_path("/abs/path/file.py") == "abs/path/file.py"
    assert _normalise_path("C:/dev/proj/file.py") == "dev/proj/file.py"
    assert _normalise_path("D:\\dev\\proj\\file.py") == "dev/proj/file.py"

    with pytest.raises(CoverageParseError):
        _normalise_path("")
    with pytest.raises(CoverageParseError):
        _normalise_path("   ")
    with pytest.raises(CoverageParseError):
        _normalise_path("/")


def test_as_dict_and_rates():
    f = FileCoverage(path="src/a.py")
    assert f.line_rate == 0.0
    assert f.branch_rate == 0.0

    f.record_line(1, 2)
    f.record_branch(1, hits=1, valid=2, covered=1)
    assert f.line_rate == 1.0
    assert f.branch_rate == 0.5

    rep = CoverageReport(files=[f])
    d = rep.as_dict()
    assert d["total_lines"] == 1
    assert d["total_lines_covered"] == 1
    assert d["total_branches"] == 2
    assert d["total_branches_covered"] == 1
    assert d["line_rate"] == 1.0
    assert d["branch_rate"] == 0.5
    assert len(d["files"]) == 1
