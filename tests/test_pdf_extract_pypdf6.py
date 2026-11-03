"""PDF text and link extraction keep working on the pypdf 6 line (dependency bump)."""
import io

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

import extract


def _pdf():
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.drawString(72, 750, "Users can reset their password")
    c.linkURL("https://example.com/spec", (72, 700, 300, 720), relative=0)
    c.save()
    return buf.getvalue()


def test_pdf_text_and_links():
    data = _pdf()
    assert "reset their password" in extract.extract_text("prd.pdf", data)
    assert "https://example.com/spec" in extract.pdf_links(data)
