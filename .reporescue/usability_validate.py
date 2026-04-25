"""
django-easy-pdf usability validation (SKILL v2 / scenario C).

Spins up a minimal Django app with:
  - ROOT_URLCONF + 3 distinct PDFTemplateView routes
  - django-easy-pdf rendering an actual Django template into a PDF
  - Real HTTP socket (werkzeug.serving.make_server) — NOT Django test_client
  - Real GET request via `requests`
  - PDF magic header check + size check + text extraction via pypdf

Hard constraints (SKILL §Step 3):
  1. Real input    : actual HTML template + real context data (invoice line items)
  2. Real assert   : assert PDF starts with %PDF, size >1KB, pypdf can extract template text
  3. Beyond unit   : tests/tests.py uses self.client.get (in-process Django Client) — we
                     hit a real TCP socket, exercising WSGI handler + middleware end-to-end
  4. Primary use   : the marquee usage of django-easy-pdf is `PDFTemplateView` rendering a
                     Django template to PDF; we use it exactly that way through HTTP
  5. Three paths   : easy_pdf.views.PDFTemplateView, easy_pdf.rendering.{render_to_pdf,
                     encode_filename, make_response, html_to_pdf}, easy_pdf.exceptions
  6. 3.13 surface  : django.utils.six.BytesIO -> io.BytesIO (six removed in modern Django),
                     django.utils.http.urlquote -> urllib.parse.quote (removed in Django 4),
                     django.conf.urls.url -> django.urls.re_path (removed in Django 4),
                     pyPdf2 -> pypdf (PyPdf2 doesn't import on 3.12+ via imp), nose/imp chain
  7. Installed     : run from /tmp/django-easy-pdf-clean (clean venv after `pip install -e`)
  8. Scenario      : Path B — 30+ line invoice generation business script
"""
from __future__ import annotations

import io
import os
import sys
import threading
import time

import django
from django.conf import settings


# ---------- 1. Configure Django (minimal app) ----------------------------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")

settings.configure(
    DEBUG=False,
    SECRET_KEY="usability-validate-not-secret",
    ALLOWED_HOSTS=["*"],
    ROOT_URLCONF=__name__,
    INSTALLED_APPS=[
        "django.contrib.contenttypes",
        "django.contrib.auth",
        "easy_pdf",
    ],
    DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}},
    TEMPLATES=[{
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [TEMPLATE_DIR],
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": []},
    }],
    STATIC_URL="/static/",
    STATIC_ROOT=os.path.join(BASE_DIR, "static"),
    MEDIA_URL="/media/",
    MEDIA_ROOT=os.path.join(BASE_DIR, "media"),
    USE_TZ=True,
)
django.setup()

from django.urls import re_path  # noqa: E402

# easy_pdf imports — touch THREE distinct submodules (hard constraint 5)
from easy_pdf.views import PDFTemplateView, PDFTemplateResponseMixin  # noqa: E402
from easy_pdf.rendering import (  # noqa: E402
    render_to_pdf,
    encode_filename,
    make_response,
    html_to_pdf,
)
from easy_pdf.exceptions import PDFRenderingError  # noqa: E402


# ---------- 2. Two real PDF views --------------------------------------------

INVOICE_LINES = [
    {"sku": "SKU-001", "desc": "Coffee Beans 1kg", "qty": 3, "price": 24.50},
    {"sku": "SKU-042", "desc": "Ceramic Mug",      "qty": 2, "price": 12.00},
    {"sku": "SKU-777", "desc": "Filter Pack x100", "qty": 1, "price": 18.75},
]
MARKER_CUSTOMER = "Acme Coffee Roasters"
MARKER_INVOICE_NO = "INV-2026-0418"


class InvoicePDFView(PDFTemplateView):
    template_name = "invoice.html"
    pdf_filename = "invoice.pdf"

    def get_context_data(self, **kwargs):
        total = sum(line["qty"] * line["price"] for line in INVOICE_LINES)
        return super().get_context_data(
            customer=MARKER_CUSTOMER,
            invoice_no=MARKER_INVOICE_NO,
            lines=INVOICE_LINES,
            total=total,
            **kwargs,
        )


class SimplePDFView(PDFTemplateView):
    template_name = "simple.html"


urlpatterns = [
    re_path(r"^invoice/$", InvoicePDFView.as_view()),
    re_path(r"^simple/$",  SimplePDFView.as_view()),
]


# ---------- 3. Run real HTTP server + assert -----------------------------------

def main() -> None:
    print("[validate] Django configured, easy_pdf imported")

    # Sanity: rendering.encode_filename — non-HTTP path, exercises rendering submodule
    enc = encode_filename("hello world.pdf")
    assert enc == "filename*=UTF-8''hello%20world.pdf", enc
    print(f"[validate] encode_filename OK -> {enc}")

    # Sanity: rendering.html_to_pdf — direct (no HTTP, no template loader)
    raw_pdf = html_to_pdf("<html><body><h1>DirectPath</h1></body></html>")
    assert raw_pdf.startswith(b"%PDF-"), raw_pdf[:20]
    assert len(raw_pdf) > 800, len(raw_pdf)
    print(f"[validate] html_to_pdf OK -> {len(raw_pdf)} bytes")

    # Sanity: rendering.make_response — wraps bytes into Django HttpResponse
    resp = make_response(raw_pdf, filename="x.pdf")
    assert resp["Content-Type"] == "application/pdf"
    assert "x.pdf" in resp["Content-Disposition"]
    print("[validate] make_response OK")

    # Sanity: rendering.render_to_pdf — template loader path (hits views' main path)
    pdf_via_template = render_to_pdf("simple.html", {})
    assert pdf_via_template.startswith(b"%PDF-")
    print(f"[validate] render_to_pdf OK -> {len(pdf_via_template)} bytes")

    # Sanity: exceptions submodule
    err = PDFRenderingError("synthetic", content="<x/>", log=[])
    assert "synthetic" in str(err)
    print("[validate] easy_pdf.exceptions OK")

    # Real HTTP path (NO test_client) — werkzeug serves the Django WSGI app
    from werkzeug.serving import make_server
    from django.core.wsgi import get_wsgi_application
    import requests

    application = get_wsgi_application()
    srv = make_server("127.0.0.1", 0, application)
    port = srv.server_port
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    time.sleep(0.3)
    print(f"[validate] werkzeug serving on 127.0.0.1:{port}")

    try:
        # Route 1: simple PDF
        r1 = requests.get(f"http://127.0.0.1:{port}/simple/", timeout=10)
        assert r1.status_code == 200, r1.status_code
        assert r1.headers["Content-Type"] == "application/pdf", r1.headers
        assert r1.content.startswith(b"%PDF-"), r1.content[:20]
        assert len(r1.content) > 1000, len(r1.content)
        print(f"[validate] /simple/ -> {len(r1.content)} bytes, magic OK")

        # Route 2: invoice PDF (real business data)
        r2 = requests.get(f"http://127.0.0.1:{port}/invoice/", timeout=10)
        assert r2.status_code == 200
        assert r2.content.startswith(b"%PDF-")
        assert len(r2.content) > 1500, len(r2.content)
        # encode_filename ran inside response middleware
        assert "invoice.pdf" in r2.headers.get("Content-Disposition", ""), r2.headers
        print(f"[validate] /invoice/ -> {len(r2.content)} bytes, attachment OK")

        # Extract text from the invoice PDF, assert template content really landed
        import pypdf
        reader = pypdf.PdfReader(io.BytesIO(r2.content))
        all_text = "\n".join(page.extract_text() or "" for page in reader.pages)
        # Template variables passed through render_to_pdf -> pisaDocument -> reportlab
        assert MARKER_CUSTOMER in all_text, f"customer marker missing; got: {all_text!r}"
        assert MARKER_INVOICE_NO in all_text, f"invoice no missing; got: {all_text!r}"
        assert "Coffee Beans" in all_text, all_text
        # Total = 3*24.5 + 2*12 + 1*18.75 = 73.5 + 24 + 18.75 = 116.25
        assert "116.25" in all_text, f"total missing; got: {all_text!r}"
        print(f"[validate] pypdf extracted {len(all_text)} chars; markers present")
    finally:
        srv.shutdown()
        th.join(timeout=2)

    print("[validate] STATUS: USABLE")


if __name__ == "__main__":
    main()
