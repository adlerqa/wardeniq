"""Feature and testcase export reports."""
import csv
import html
import io
from collections import OrderedDict
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

BRAND = colors.HexColor("#2347bf")
BRAND_DARK = colors.HexColor("#0c1b49")
BRAND_SOFT = colors.HexColor("#e8efff")
PAGE_BG = colors.HexColor("#f5f7fb")
PANEL = colors.white
PANEL_SOFT = colors.HexColor("#f8fbff")
BORDER = colors.HexColor("#d7dfed")
TEXT = colors.HexColor("#172033")
MUTED = colors.HexColor("#56627a")
SOFT_TEXT = colors.HexColor("#7a869e")
SUCCESS_BG = colors.HexColor("#dcfce7")
SUCCESS_TEXT = colors.HexColor("#166534")
FAIL_BG = colors.HexColor("#fee2e2")
FAIL_TEXT = colors.HexColor("#b91c1c")
BLOCK_BG = colors.HexColor("#ffedd5")
BLOCK_TEXT = colors.HexColor("#c2410c")
DEFAULT_BADGE_BG = colors.HexColor("#e2e8f0")
DEFAULT_BADGE_TEXT = colors.HexColor("#334155")

TYPE_LABELS = OrderedDict([
    ("functional", "Business / Functional"),
    ("e2e", "End-to-End"),
    ("api", "API"),
    ("ui", "UI Validations"),
    ("nfr", "Edge & Reliability"),
    ("integration", "Integration"),
])


def _e(value) -> str:
    return html.escape(str(value or ""))


def _safe(value, fallback="") -> str:
    if value is None:
        return fallback
    text = str(value).strip()
    return text or fallback


def _clean_summary(value: str) -> str:
    text = _safe(value)
    if not text:
        return ""
    prefixes = (
        "prd rule:",
        "prd suggests:",
        "prd specifies:",
        "prd states:",
        "hld rule:",
        "lld rule:",
        "doc rule:",
    )
    lowered = text.lower()
    for prefix in prefixes:
        if lowered.startswith(prefix):
            text = text[len(prefix):].strip()
            break
    return " ".join(text.replace("\n", " ").split())


def _type_label(value: str) -> str:
    return TYPE_LABELS.get((value or "").strip().lower(), _safe(value, "Other"))


def _status_label(value: str) -> str:
    raw = (value or "untested").strip().lower()
    return {
        "passed": "Passed",
        "failed": "Failed",
        "blocked": "Blocked",
        "untested": "Untested",
    }.get(raw, raw.title())


def _priority_label(value: str) -> str:
    raw = _safe(value, "P2").upper()
    return raw


_PRIO_CANON = {"P1": "High", "P2": "Medium", "P3": "Low", "1": "High", "2": "Medium",
               "3": "Low", "CRITICAL": "High", "MID": "Medium", "HIGH": "High",
               "MEDIUM": "Medium", "LOW": "Low"}


def build_cycle_pdf(cycle: dict) -> bytes:
    """Simple tabular PDF export of a test cycle (mirrors the CSV columns)."""
    base = getSampleStyleSheet()
    cell = ParagraphStyle("cyc_cell", parent=base["Normal"], fontSize=8, leading=10)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=14 * mm, rightMargin=14 * mm,
                            topMargin=16 * mm, bottomMargin=16 * mm)
    story = [Paragraph(_e(cycle.get("name") or "Test cycle"), base["Title"])]
    meta = f"Status: {_safe(cycle.get('status'), 'draft')}"
    if cycle.get("scheduled_start_at"):
        meta += f"  ·  Start: {_safe(cycle.get('scheduled_start_at'))[:10]}"
    if cycle.get("scheduled_end_at"):
        meta += f"  ·  End: {_safe(cycle.get('scheduled_end_at'))[:10]}"
    story += [Paragraph(_e(meta), base["Normal"]), Spacer(1, 8)]
    rows = [["#", "ID", "Title", "Category", "Priority", "Status"]]
    for it in cycle.get("items", []):
        prio = _PRIO_CANON.get(_safe(it.get("priority")).upper(), _safe(it.get("priority")))
        rows.append([
            str(it.get("display_order") or ""),
            Paragraph(_e(it.get("display_id") or it.get("case_id") or ""), cell),
            Paragraph(_e(it.get("title") or ""), cell),
            _e(_type_label(it.get("category") or "")),
            _e(prio),
            _e(_status_label(it.get("execution_status") or "")),
        ])
    table = Table(rows, colWidths=[9 * mm, 26 * mm, 73 * mm, 24 * mm, 20 * mm, 22 * mm], repeatRows=1)
    table.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f3f4f6")]),
    ]))
    story.append(table)
    doc.build(story)
    return buf.getvalue()


def _group_cases(cases: list) -> OrderedDict:
    grouped = OrderedDict((key, []) for key in TYPE_LABELS)
    for case in cases:
        key = (case.get("category") or case.get("type") or "").strip().lower()
        grouped.setdefault(key, [])
        grouped[key].append(case)
    return grouped


def _styles():
    base = getSampleStyleSheet()
    return {
        "hero_brand": ParagraphStyle(
            "hero_brand",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=9,
            leading=11,
            textColor=colors.white,
        ),
        "hero_title": ParagraphStyle(
            "hero_title",
            parent=base["Title"],
            fontName="Helvetica-Bold",
            fontSize=20,
            leading=23,
            textColor=colors.white,
        ),
        "hero_body": ParagraphStyle(
            "hero_body",
            parent=base["Normal"],
            fontSize=9.4,
            leading=13,
            textColor=colors.HexColor("#dbe7ff"),
        ),
        "hero_meta_label": ParagraphStyle(
            "hero_meta_label",
            parent=base["Normal"],
            fontSize=7.4,
            leading=9,
            textColor=colors.HexColor("#c5d4ff"),
        ),
        "hero_meta_value": ParagraphStyle(
            "hero_meta_value",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=9.2,
            leading=11,
            textColor=colors.white,
        ),
        "section": ParagraphStyle(
            "section",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=12.6,
            leading=15,
            textColor=BRAND_DARK,
        ),
        "section_hint": ParagraphStyle(
            "section_hint",
            parent=base["Normal"],
            fontSize=8.2,
            leading=11,
            textColor=SOFT_TEXT,
        ),
        "body": ParagraphStyle(
            "body",
            parent=base["Normal"],
            fontSize=8.9,
            leading=13,
            textColor=TEXT,
        ),
        "body_muted": ParagraphStyle(
            "body_muted",
            parent=base["Normal"],
            fontSize=8.4,
            leading=12,
            textColor=MUTED,
        ),
        "card_label": ParagraphStyle(
            "card_label",
            parent=base["Normal"],
            fontSize=7.8,
            leading=9,
            textColor=SOFT_TEXT,
        ),
        "card_value": ParagraphStyle(
            "card_value",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=16,
            leading=18,
            textColor=BRAND,
        ),
        "case_title": ParagraphStyle(
            "case_title",
            parent=base["Heading3"],
            fontName="Helvetica-Bold",
            fontSize=10.8,
            leading=14,
            textColor=BRAND_DARK,
        ),
        "meta": ParagraphStyle(
            "meta",
            parent=base["Normal"],
            fontSize=7.8,
            leading=10.4,
            textColor=MUTED,
        ),
        "small": ParagraphStyle(
            "small",
            parent=base["Normal"],
            fontSize=7.8,
            leading=10.2,
            textColor=TEXT,
        ),
        "step": ParagraphStyle(
            "step",
            parent=base["Normal"],
            fontSize=7.8,
            leading=10.8,
            textColor=TEXT,
        ),
    }


def _page(canvas, doc):
    canvas.saveState()
    width, _height = A4
    canvas.setFillColor(PAGE_BG)
    canvas.rect(0, 0, width, A4[1], fill=1, stroke=0)
    canvas.setStrokeColor(BORDER)
    canvas.line(doc.leftMargin, 11 * mm, width - doc.rightMargin, 11 * mm)
    canvas.setFillColor(SOFT_TEXT)
    canvas.setFont("Helvetica", 8)
    canvas.drawString(doc.leftMargin, 6.5 * mm, "wardenIQ export")
    canvas.drawRightString(width - doc.rightMargin, 6.5 * mm, f"Page {canvas.getPageNumber()}")
    canvas.restoreState()


def _box(flowables, width, background=PANEL, border=BORDER, padding=10):
    table = Table([[flowables]], colWidths=[width])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), background),
        ("BOX", (0, 0), (-1, -1), 0.7, border),
        ("LEFTPADDING", (0, 0), (-1, -1), padding),
        ("RIGHTPADDING", (0, 0), (-1, -1), padding),
        ("TOPPADDING", (0, 0), (-1, -1), padding),
        ("BOTTOMPADDING", (0, 0), (-1, -1), padding),
    ]))
    return table


def _hero(feature: dict, title: str, subtitle: str, styles: dict):
    generated = datetime.now().strftime("%d %b %Y, %I:%M %p")
    meta_cards = [
        [Paragraph("PROJECT", styles["hero_meta_label"]), Paragraph(_e(feature.get("project_name") or feature.get("project") or "Current project"), styles["hero_meta_value"])],
        [Paragraph("FEATURE", styles["hero_meta_label"]), Paragraph(_e(feature.get("name") or "Feature"), styles["hero_meta_value"])],
        [Paragraph("VERSION", styles["hero_meta_label"]), Paragraph(_e(feature.get("version") or 1), styles["hero_meta_value"])],
    ]
    meta_table = Table(meta_cards, colWidths=[54 * mm, 62 * mm])
    meta_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#2c4ebf")),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#5c7ce1")),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#5c7ce1")),
        ("LEFTPADDING", (0, 0), (-1, -1), 9),
        ("RIGHTPADDING", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    generated_box = _box(
        [
            Paragraph("GENERATED", styles["hero_meta_label"]),
            Spacer(1, 2),
            Paragraph(_e(generated), styles["hero_meta_value"]),
        ],
        44 * mm,
        background=colors.HexColor("#2948a8"),
        border=colors.HexColor("#6f8ef3"),
        padding=8,
    )
    top = Table(
        [[
            [
                Paragraph("wardenIQ", styles["hero_brand"]),
                Spacer(1, 3),
                Paragraph(_e(title), styles["hero_title"]),
                Spacer(1, 3),
                Paragraph(_e(subtitle), styles["hero_body"]),
            ],
            generated_box,
        ]],
        colWidths=[132 * mm, 44 * mm],
    )
    top.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    hero = Table([[top], [Spacer(1, 6)], [meta_table]], colWidths=[176 * mm])
    hero.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), BRAND_DARK),
        ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#365bcf")),
        ("LEFTPADDING", (0, 0), (-1, -1), 14),
        ("RIGHTPADDING", (0, 0), (-1, -1), 14),
        ("TOPPADDING", (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
    ]))
    return hero


def _metric_cell(label: str, value: str, styles: dict):
    return _box(
        [
            Paragraph(_e(value), styles["card_value"]),
            Spacer(1, 2),
            Paragraph(_e(label), styles["card_label"]),
        ],
        56 * mm,
        background=PANEL,
        border=BORDER,
        padding=10,
    )


def _summary_cards(cases: list, styles: dict):
    grouped = _group_cases(cases)
    metrics = [
        ("Total cases", str(len(cases))),
        ("Business / Functional", str(len(grouped.get("functional", [])))),
        ("End-to-End", str(len(grouped.get("e2e", [])))),
        ("API", str(len(grouped.get("api", [])))),
        ("UI Validations", str(len(grouped.get("ui", [])))),
        ("Edge & Reliability", str(len(grouped.get("nfr", [])))),
    ]
    rows = []
    current = []
    for label, value in metrics:
        current.append(_metric_cell(label, value, styles))
        if len(current) == 3:
            rows.append(current)
            current = []
    if current:
        while len(current) < 3:
            current.append("")
        rows.append(current)
    grid = Table(rows, colWidths=[58 * mm, 58 * mm, 58 * mm], hAlign="LEFT")
    grid.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    return grid


def _section_header(title: str, count: int | None, styles: dict, subtitle: str | None = None):
    title_html = f"{_e(title)}"
    if count is not None:
        title_html += f" <font color='#2347bf'><b>{_e(count)}</b></font>"
    flow = [Paragraph(title_html, styles["section"])]
    if subtitle:
        flow += [Spacer(1, 2), Paragraph(_e(subtitle), styles["section_hint"])]
    return flow


def _badge(text: str, bg, fg, width=None):
    pill = Table([[Paragraph(f"<b>{_e(text)}</b>", ParagraphStyle("badge", fontName="Helvetica-Bold", fontSize=7.2, textColor=fg, leading=9))]], colWidths=[width] if width else None)
    pill.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), bg),
        ("BOX", (0, 0), (-1, -1), 0.45, bg),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return pill


def _status_badge(status: str):
    label = _status_label(status)
    raw = (status or "").strip().lower()
    if raw == "passed":
        return _badge(label, SUCCESS_BG, SUCCESS_TEXT)
    if raw == "failed":
        return _badge(label, FAIL_BG, FAIL_TEXT)
    if raw == "blocked":
        return _badge(label, BLOCK_BG, BLOCK_TEXT)
    return _badge(label, DEFAULT_BADGE_BG, DEFAULT_BADGE_TEXT)


def _priority_badge(priority: str):
    raw = _priority_label(priority)
    mapping = {
        "P1": (FAIL_BG, FAIL_TEXT),
        "P2": (colors.HexColor("#ffedd5"), BLOCK_TEXT),
        "P3": (SUCCESS_BG, SUCCESS_TEXT),
    }
    bg, fg = mapping.get(raw, (DEFAULT_BADGE_BG, DEFAULT_BADGE_TEXT))
    return _badge(raw, bg, fg)


def _case_steps_table(steps: list, styles: dict):
    rows = [[
        Paragraph("<b>#</b>", styles["small"]),
        Paragraph("<b>Step</b>", styles["small"]),
        Paragraph("<b>Expected result</b>", styles["small"]),
    ]]
    for idx, step in enumerate(steps, 1):
        action = _clean_summary(step.get("action", "")) or "Not specified"
        expected = _clean_summary(step.get("expected", "")) or "Not specified"
        rows.append([
            Paragraph(str(idx), styles["small"]),
            Paragraph(_e(action), styles["step"]),
            Paragraph(_e(expected), styles["step"]),
        ])
    table = Table(rows, colWidths=[10 * mm, 82 * mm, 84 * mm], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BRAND_SOFT),
        ("TEXTCOLOR", (0, 0), (-1, 0), BRAND_DARK),
        ("BACKGROUND", (0, 1), (-1, -1), PANEL_SOFT),
        ("BOX", (0, 0), (-1, -1), 0.45, BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.35, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return table


def _case_card(case: dict, styles: dict):
    case_id = case.get("display_id") or case.get("id", "")
    case_title = _clean_summary(case.get("title", "")) or "Untitled testcase"
    steps = case.get("steps") or []
    header = Table(
        [[
            Paragraph(f"<b>{_e(case_id)}</b>", styles["meta"]),
            Paragraph(_e(case_title), styles["case_title"]),
        ]],
        colWidths=[28 * mm, 136 * mm],
    )
    header.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    badges = Table([[
        _badge(_type_label(case.get("type", "")), BRAND_SOFT, BRAND),
        _priority_badge(case.get("priority", "P2")),
        _status_badge(case.get("execution_status", "untested")),
        Paragraph(f"{len(steps)} step(s)", styles["meta"]),
    ]], colWidths=[42 * mm, 18 * mm, 22 * mm, 24 * mm])
    badges.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    description = _clean_summary(case.get("description", ""))
    expected_result = _clean_summary(case.get("expected_result", ""))
    header_panel = _box([header, Spacer(1, 6), badges], 176 * mm, background=PANEL, border=BORDER, padding=10)
    flow = [header_panel]
    if description or expected_result:
        kv_rows = []
        if description:
            kv_rows.append([Paragraph("<b>Description</b>", styles["meta"]), Paragraph(_e(description), styles["body"])])
        if expected_result:
            kv_rows.append([Paragraph("<b>Expected result</b>", styles["meta"]), Paragraph(_e(expected_result), styles["body"])])
        kv = Table(kv_rows, colWidths=[28 * mm, 136 * mm])
        kv.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), PANEL_SOFT),
            ("BOX", (0, 0), (-1, -1), 0.45, BORDER),
            ("INNERGRID", (0, 0), (-1, -1), 0.35, BORDER),
            ("LEFTPADDING", (0, 0), (-1, -1), 7),
            ("RIGHTPADDING", (0, 0), (-1, -1), 7),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        flow += [Spacer(1, 6), kv]
    flow += [Spacer(1, 6)]
    if steps:
        flow.append(_case_steps_table(steps, styles))
    else:
        flow.append(Paragraph("No detailed steps saved for this testcase.", styles["body_muted"]))
    return flow


def _feature_report_story(feature: dict, cov: dict, cases: list, prs: list, styles: dict):
    summary = _clean_summary(feature.get("summary") or feature.get("source") or "No summary available.")
    coverage = [
        ("Pull requests", str(cov.get("prs_count", len(prs) if prs else 0))),
        ("Code coverage", f"{cov.get('code_pct', 0)}%"),
        ("Automation Test Coverage", f"{cov.get('automation_pct', 0)}%"),
    ]
    coverage_cards = Table(
        [[_metric_cell(label, value, styles) for label, value in coverage]],
        colWidths=[58 * mm, 58 * mm, 58 * mm],
    )
    coverage_cards.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story = [
        _hero(feature, "Feature Report", "Coverage summary and exported testcase overview.", styles),
        Spacer(1, 10),
        *_section_header("Coverage overview", None, styles, "Snapshot of linked PR activity and current execution coverage."),
        Spacer(1, 6),
        coverage_cards,
        Spacer(1, 10),
        *_section_header("Feature summary", None, styles, "Condensed context for what this version covers."),
        Spacer(1, 5),
        _box([Paragraph(_e(summary), styles["body"])], 176 * mm, background=PANEL, border=BORDER, padding=11),
        Spacer(1, 10),
        *_section_header("Test mix", len(cases), styles, "Distribution of generated test coverage across categories."),
        Spacer(1, 6),
        _summary_cards(cases, styles),
    ]
    if prs:
        rows = [[
            Paragraph("<b>#</b>", styles["small"]),
            Paragraph("<b>Title</b>", styles["small"]),
            Paragraph("<b>Repository</b>", styles["small"]),
            Paragraph("<b>Status</b>", styles["small"]),
        ]]
        for pr in prs:
            rows.append([
                Paragraph(_e(pr.get("number", "")), styles["small"]),
                Paragraph(_e(pr.get("title", "")), styles["small"]),
                Paragraph(_e(pr.get("repo_full_name", "")), styles["small"]),
                Paragraph(_e(pr.get("state", "")), styles["small"]),
            ])
        table = Table(rows, colWidths=[12 * mm, 88 * mm, 52 * mm, 24 * mm], repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), BRAND_SOFT),
            ("TEXTCOLOR", (0, 0), (-1, 0), BRAND_DARK),
            ("BACKGROUND", (0, 1), (-1, -1), PANEL),
            ("BOX", (0, 0), (-1, -1), 0.45, BORDER),
            ("INNERGRID", (0, 0), (-1, -1), 0.35, BORDER),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 7),
            ("RIGHTPADDING", (0, 0), (-1, -1), 7),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        story += [Spacer(1, 10), *_section_header("Linked pull requests", len(prs), styles, None), Spacer(1, 6), table]
    return story


def build_feature_pdf(feature: dict, cov: dict, cases: list, prs: list) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        topMargin=14 * mm,
        bottomMargin=16 * mm,
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        title=f"Feature report — {feature.get('name', '')}",
    )
    styles = _styles()
    doc.build(_feature_report_story(feature, cov, cases, prs, styles), onFirstPage=_page, onLaterPages=_page)
    return buf.getvalue()


def _case_rows(cases: list) -> list[list[str]]:
    rows = [["ID", "Title", "Category", "Priority", "Status", "Steps"]]
    for case in cases:
        steps = case.get("steps") or []
        step_text = "\n".join(
            f"{idx + 1}. {_clean_summary(step.get('action', ''))} -> {_clean_summary(step.get('expected', ''))}"
            for idx, step in enumerate(steps)
        )
        rows.append([
            case.get("display_id") or case.get("id", ""),
            _clean_summary(case.get("title", "")),
            _type_label(case.get("category") or case.get("type", "")),
            _priority_label(case.get("priority", "")),
            _status_label(case.get("execution_status", "untested")),
            step_text,
        ])
    return rows


def build_testcase_csv(feature: dict, cases: list) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Feature", feature.get("name", "")])
    writer.writerow(["Version", feature.get("version", 1)])
    writer.writerow(["Summary", _clean_summary(feature.get("summary", ""))])
    writer.writerow([])
    writer.writerows(_case_rows(cases))
    return buf.getvalue().encode("utf-8")


def build_testcase_pdf(feature: dict, cases: list) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        topMargin=14 * mm,
        bottomMargin=16 * mm,
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        title=f"Test cases — {feature.get('name', '')}",
    )
    styles = _styles()
    summary = _clean_summary(feature.get("summary", ""))
    grouped = _group_cases(cases)
    metric_rows = [
        [
            Paragraph("<b>Total cases</b>", styles["small"]),
            Paragraph(str(len(cases)), styles["body"]),
            Paragraph("<b>Business / Functional</b>", styles["small"]),
            Paragraph(str(len(grouped.get("functional", []))), styles["body"]),
            Paragraph("<b>End-to-End</b>", styles["small"]),
            Paragraph(str(len(grouped.get("e2e", []))), styles["body"]),
        ],
        [
            Paragraph("<b>API</b>", styles["small"]),
            Paragraph(str(len(grouped.get("api", []))), styles["body"]),
            Paragraph("<b>UI Validations</b>", styles["small"]),
            Paragraph(str(len(grouped.get("ui", []))), styles["body"]),
            Paragraph("<b>Edge & Reliability</b>", styles["small"]),
            Paragraph(str(len(grouped.get("nfr", []))), styles["body"]),
        ],
    ]
    metric_table = Table(metric_rows, colWidths=[34 * mm, 22 * mm, 40 * mm, 16 * mm, 34 * mm, 18 * mm])
    metric_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PANEL),
        ("BOX", (0, 0), (-1, -1), 0.55, BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.35, BORDER),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story = [
        Paragraph(_e(feature.get("name", "Feature")), styles["section"]),
        Spacer(1, 2),
        Paragraph(
            f"Version {_e(feature.get('version', 1))} • {len(cases)} test case(s)"
            + (f" • Project {_e(feature.get('project_name'))}" if feature.get("project_name") else "")
            + (f" • Jira {_e(feature.get('key'))}" if feature.get("key") else ""),
            styles["body_muted"],
        ),
        Spacer(1, 10),
        *_section_header("Coverage summary", len(cases), styles, "Grouped by testcase category for faster review and sharing."),
        Spacer(1, 6),
        metric_table,
    ]
    if summary:
        story += [Spacer(1, 10), *_section_header("Feature summary", None, styles, None), Spacer(1, 5), Paragraph(_e(summary), styles["body"])]
    for group_key, label in TYPE_LABELS.items():
        group_cases = grouped.get(group_key, [])
        if not group_cases:
            continue
        story += [Spacer(1, 11), *_section_header(label, len(group_cases), styles, f"Included {_type_label(group_key).lower()} coverage for this feature version."), Spacer(1, 6)]
        for idx, case in enumerate(group_cases):
            case_id = case.get("display_id") or case.get("id", "")
            case_title = _clean_summary(case.get("title", "")) or "Untitled testcase"
            steps = case.get("steps") or []
            meta = f"{_type_label(case.get('type', ''))} • {_priority_label(case.get('priority', 'P2'))} • {_status_label(case.get('execution_status', 'untested'))} • {len(steps)} step(s)"
            story += [
                Paragraph(f"{_e(case_id)} — {_e(case_title)}", styles["case_title"]),
                Spacer(1, 2),
                Paragraph(_e(meta), styles["meta"]),
            ]
            description = _clean_summary(case.get("description", ""))
            expected_result = _clean_summary(case.get("expected_result", ""))
            if description:
                story += [Spacer(1, 4), Paragraph(f"<b>Description:</b> {_e(description)}", styles["body"])]
            if expected_result:
                story += [Spacer(1, 3), Paragraph(f"<b>Expected result:</b> {_e(expected_result)}", styles["body"])]
            story += [Spacer(1, 5)]
            if steps:
                story.append(_case_steps_table(steps, styles))
            else:
                story.append(Paragraph("No detailed steps saved for this testcase.", styles["body_muted"]))
            if idx != len(group_cases) - 1:
                story += [Spacer(1, 8), HRFlowable(color=BORDER, thickness=0.35, width="100%"), Spacer(1, 8)]
        story += [Spacer(1, 8), HRFlowable(color=BORDER, thickness=0.55, width="100%")]
    doc.build(story, onFirstPage=_page, onLaterPages=_page)
    return buf.getvalue()


# ---- Gap Analysis exports (feature-level) -----------------------------------
def _gap_table_pdf(title: str, subtitle: str, header: list, rows: list) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=14 * mm, bottomMargin=16 * mm,
                            leftMargin=12 * mm, rightMargin=12 * mm, title=title)
    styles = _styles()
    story = [Paragraph(_e(title), styles["section"]), Spacer(1, 2)]
    if subtitle:
        story += [Paragraph(_e(subtitle), styles["body_muted"]), Spacer(1, 8)]
    data = [[Paragraph(f"<b>{_e(h)}</b>", styles["small"]) for h in header]]
    for r in rows:
        data.append([Paragraph(_e("" if c is None else str(c)), styles["small"]) for c in r])
    table = Table(data, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), PANEL),
        ("BOX", (0, 0), (-1, -1), 0.55, BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.35, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(table)
    doc.build(story, onFirstPage=_page, onLaterPages=_page)
    return buf.getvalue()


def _gap_csv(preamble: list, header: list, rows: list) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    for line in preamble:
        w.writerow(line)
    if preamble:
        w.writerow([])
    w.writerow(header)
    w.writerows(rows)
    return buf.getvalue().encode("utf-8")


def _pr_covmap(run: dict) -> dict:
    """Map test_case_id -> status (covered/partial) for one PR coverage run."""
    m = {}
    for cc in ((run.get("result") or {}).get("covered") or []):
        cid = cc.get("test_case_id") or cc.get("id")
        if cid:
            m[cid] = cc.get("status", "covered")
    return m


def _pr_detail_rows(runs: list, cases: list) -> list:
    """One row per (PR x test case): covered/partial/missing, with commit + repo."""
    rows = []
    for r in runs or []:
        covmap = _pr_covmap(r)
        commit = (r.get("head_sha", "") or "")[:7]
        branch = r.get("pr_branch", "") or r.get("head_ref", "")
        for c in cases or []:
            cid = c.get("id")
            rows.append([r.get("pr_number", ""), r.get("repo_full_name", ""), branch, commit,
                         c.get("display_id") or cid or "",
                         _clean_summary(c.get("title", "")),
                         _type_label(c.get("type", "")),
                         covmap.get(cid, "missing")])
    return rows


def build_gap_pr_csv(feature: dict, runs: list, cases: list) -> bytes:
    return _gap_csv(
        [["Feature", feature.get("name", "")], ["Version", feature.get("version", 1)],
         ["Report", "PR Code Coverage (per PR x test case)"],
         ["PRs", len(runs or [])], ["Test cases", len(cases or [])]],
        ["PR #", "Repo", "Branch", "Commit", "Case ID", "Case Title", "Category", "Status"],
        _pr_detail_rows(runs, cases))


def build_gap_pr_pdf(feature: dict, runs: list, cases: list) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=14 * mm, bottomMargin=16 * mm,
                            leftMargin=12 * mm, rightMargin=12 * mm,
                            title="PR Code Coverage - " + feature.get("name", ""))
    styles = _styles()
    story = [Paragraph(_e("PR Code Coverage - " + feature.get("name", "")), styles["section"]),
             Spacer(1, 2),
             Paragraph(_e("Version %s  |  %d PR(s)  |  %d test case(s)" % (
                 feature.get("version", 1), len(runs or []), len(cases or []))), styles["body_muted"]),
             Spacer(1, 8)]
    if not runs:
        story.append(Paragraph("No PR coverage runs yet.", styles["body_muted"]))
    cell = TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), PANEL),
        ("BOX", (0, 0), (-1, -1), 0.55, BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.35, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ])
    for r in runs or []:
        covmap = _pr_covmap(r)
        total = len(cases or [])
        covered_n = sum(1 for c in (cases or []) if covmap.get(c.get("id")))
        commit = (r.get("head_sha", "") or "")[:7]
        head = "PR #%s  |  %s  |  %s  -  %d/%d covered" % (
            r.get("pr_number", ""), r.get("repo_full_name", ""), commit, covered_n, total)
        story += [Spacer(1, 8), Paragraph(_e(head), styles["case_title"]), Spacer(1, 4)]
        data = [[Paragraph("<b>%s</b>" % _e(h), styles["small"])
                 for h in ["Case ID", "Title", "Category", "Status"]]]
        for c in cases or []:
            data.append([
                Paragraph(_e(c.get("display_id") or c.get("id", "")), styles["small"]),
                Paragraph(_e(_clean_summary(c.get("title", ""))), styles["small"]),
                Paragraph(_e(_type_label(c.get("type", ""))), styles["small"]),
                Paragraph(_e(covmap.get(c.get("id"), "missing")), styles["small"]),
            ])
        table = Table(data, repeatRows=1, colWidths=[26 * mm, 96 * mm, 28 * mm, 22 * mm])
        table.setStyle(cell)
        story.append(table)
    doc.build(story, onFirstPage=_page, onLaterPages=_page)
    return buf.getvalue()


def _automation_rows(items: list) -> list:
    rows = []
    for it in items or []:
        mt = it.get("match") or {}
        loc = mt.get("repo_full_name", "")
        if mt.get("file_path"):
            loc = (loc + ":" if loc else "") + mt.get("file_path", "")
        rows.append([it.get("display_id") or it.get("generated_id", "") or "",
                     _clean_summary(it.get("generated_title", "")),
                     _type_label(it.get("generated_type", "")),
                     "Covered" if it.get("status") == "covered" else "Missing",
                     loc, _clean_summary(mt.get("title", ""))])
    return rows


def build_gap_automation_csv(feature: dict, snapshot: dict) -> bytes:
    snap = snapshot or {}
    return _gap_csv(
        [["Feature", feature.get("name", "")], ["Version", feature.get("version", 1)],
         ["Report", "Automation Test Coverage"], ["Coverage %", snap.get("coverage_pct", 0)],
         ["Covered", snap.get("covered_count", 0)], ["Missing", snap.get("missing_count", 0)],
         ["Scanned repo", snap.get("scanned_repo_full_name", "")]],
        ["Case ID", "Title", "Category", "Automation", "Test location", "Matched test"],
        _automation_rows(snap.get("items", [])))


def build_gap_automation_pdf(feature: dict, snapshot: dict) -> bytes:
    snap = snapshot or {}
    sub = (f"Version {feature.get('version', 1)} • {snap.get('coverage_pct', 0)}% covered"
           f" • {snap.get('covered_count', 0)} covered / {snap.get('missing_count', 0)} missing")
    rows = [[r[0], r[1], r[2], r[3], r[5]] for r in _automation_rows(snap.get("items", []))]
    return _gap_table_pdf(f"Automation Test Coverage — {feature.get('name', '')}", sub,
                          ["Case ID", "Title", "Category", "Automation", "Matched test"], rows)
