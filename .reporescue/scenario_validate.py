"""
Path B scenario: 'Monthly sales report' batch generator.

Imagine a CFO wants a stack of per-region monthly sales PDFs to email.
This script — written purely from the README's "Quick Start" — drives
django-easy-pdf as a downstream consumer would in production. No Django
project on disk, no manage.py: a single-process batch job that produces
PDFs to a directory.

The flow:
  1. Configure Django in-process
  2. Build per-region context dicts from a fictional sales source
  3. Use easy_pdf.rendering.render_to_pdf (template path) to generate PDFs
  4. Write to disk + verify each PDF with pypdf, asserting per-region totals
"""
from __future__ import annotations

import io
import os
import sys
import tempfile

import django
from django.conf import settings


HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(HERE, "templates")

settings.configure(
    DEBUG=False,
    SECRET_KEY="scenario-not-secret",
    INSTALLED_APPS=["django.contrib.contenttypes", "django.contrib.auth", "easy_pdf"],
    DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}},
    TEMPLATES=[{
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [TEMPLATES_DIR],
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": []},
    }],
    STATIC_URL="/static/",
    STATIC_ROOT=os.path.join(HERE, "static"),
    USE_TZ=True,
)
django.setup()

from easy_pdf.rendering import render_to_pdf, encode_filename, html_to_pdf  # noqa: E402

# Real "business" data
SALES = {
    "APAC": [("Tokyo", 12_400.00), ("Singapore", 8_700.00), ("Sydney", 5_300.00)],
    "EMEA": [("Berlin", 9_800.00), ("Paris", 11_250.00), ("London", 14_900.00)],
    "AMER": [("New York", 21_000.00), ("Toronto", 7_400.00), ("Sao Paulo", 3_950.00)],
}


def build_context(region: str, rows: list[tuple[str, float]]) -> dict:
    total = sum(rev for _, rev in rows)
    lines = [{"sku": city, "desc": f"{city} branch revenue",
              "qty": 1, "price": rev} for city, rev in rows]
    return {
        "customer": f"Region: {region}",
        "invoice_no": f"REPORT-{region}-2026-04",
        "lines": lines,
        "total": total,
    }


def main() -> None:
    out_dir = tempfile.mkdtemp(prefix="sales-pdfs-")
    print(f"[scenario] writing to {out_dir}")
    written = []
    for region, rows in SALES.items():
        ctx = build_context(region, rows)
        pdf_bytes = render_to_pdf("invoice.html", ctx)
        assert pdf_bytes.startswith(b"%PDF-")
        path = os.path.join(out_dir, f"{region}.pdf")
        with open(path, "wb") as fh:
            fh.write(pdf_bytes)
        written.append((region, path, ctx["total"]))
        print(f"[scenario] {region}: {len(pdf_bytes)} bytes -> {path}")

    # Verify each PDF: open, extract text, assert region marker + total are present
    import pypdf
    for region, path, total in written:
        reader = pypdf.PdfReader(path)
        text = "\n".join(p.extract_text() or "" for p in reader.pages)
        assert region in text, f"{region} marker missing in {path}: {text!r}"
        # total may be rendered with comma-separated floatformat, allow either
        total_str = f"{total:.2f}"
        assert total_str in text or f"{total:,.2f}" in text, (
            f"total {total_str} not in {path}; got: {text!r}")
        print(f"[scenario] verified {region}: total {total_str} in PDF text")

    # Use encode_filename + html_to_pdf with a non-ASCII filename
    enc = encode_filename("ventas-españa.pdf")
    assert enc.startswith("filename*=UTF-8''"), enc
    pdf2 = html_to_pdf("<html><body>EOM Report</body></html>")
    assert pdf2.startswith(b"%PDF-")
    print(f"[scenario] non-ASCII filename: {enc}")

    print("[scenario] all 3 regional reports generated and verified")


if __name__ == "__main__":
    main()
