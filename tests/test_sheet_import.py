import csv
import io

import sheet_import as si


def _csv_bytes(rows):
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerows(rows)
    return buf.getvalue().encode("utf-8")


def test_document_catalog_rows_become_clean_project_memory():
    rows = [
        ["Feature", "Version", "Document Type", "Document Path", "Endpoints", "Edge Cases"],
        [
            "Create Event Flow",
            "Version 1",
            "PRD",
            "/docs/create-event/prd.pdf",
            "POST /events | GET /events/{id}",
            "Reject missing title and invalid date range",
        ],
        ["Create Event Flow", "Version 1", "HLD", "/docs/create-event/hld.pdf", "", ""],
    ]

    parsed = si.parse_sheet(_csv_bytes(rows), "catalog.csv")

    assert len(parsed) == 1
    row = parsed[0]
    assert row.title == "Validate Create Event Flow PRD behavior"
    assert row.steps == ["Validate documented API behavior"]
    assert "Version 1" not in " ".join(row.steps)
    assert "POST /events" not in " ".join(row.steps)
    assert row.expected_result == "Reject missing title and invalid date range"


def test_legacy_route_heavy_payload_is_repaired_for_display():
    repaired = si.normalize_imported_payload_shape({
        "title": "Create event endpoint coverage",
        "steps": [
            "Steps: CREATE EVENT FLOW · Version 1",
            "POST /events | GET /events/{id} | DELETE /events/{id}",
        ],
        "expected_result": "POST /events | GET /events/{id}",
    })

    rendered_steps = " ".join(
        step["content"] if isinstance(step, dict) else step
        for step in repaired["steps"]
    )
    assert "Version 1" not in rendered_steps
    assert "POST /events" not in rendered_steps
    assert "Validate documented API behavior" in rendered_steps
    assert "POST /events" not in repaired["expected_result"]


def test_identity_and_content_signature_are_stable_for_duplicate_uploads():
    rows = [
        ["Title", "Steps", "Expected Result", "Priority"],
        ["Login happy path", "Open login; Submit valid OTP", "Dashboard opens", "High"],
    ]
    first = si.parse_sheet(_csv_bytes(rows), "login.csv")
    second = si.parse_sheet(_csv_bytes(rows), "login-copy.csv")

    assert [si.identity_hash(r) for r in first] == [si.identity_hash(r) for r in second]
    assert si.content_signature(first) == si.content_signature(second)
