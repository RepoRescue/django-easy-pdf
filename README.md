# django-easy-pdf (RepoRescue rescue)

Render PDFs from Django templates the easy way. A class-based view subclasses
`PDFTemplateView`, points at a template, and Django returns a fully-rendered PDF
as the HTTP response — invoices, tickets, regulatory exports, sales reports.

This fork is a [RepoRescue](https://github.com/RepoRescue) rescue of the
abandoned upstream
[`nigma/django-easy-pdf`](https://github.com/nigma/django-easy-pdf) (archived,
last release 0.1.0 in 2017). The original ships against Django 1.x and
Python 2/3.4-era APIs that no longer exist on **Python 3.13 / Django 6.x**.
The rescue restores it without touching the public surface
(`easy_pdf.views.PDFTemplateView`, `easy_pdf.rendering.render_to_pdf`,
`easy_pdf.exceptions`).

PDF rendering backend is unchanged: still `xhtml2pdf` + `reportlab`.

---

## Install

```bash
pip install svglib==1.5.1   # see Caveat below — pin first
pip install git+https://github.com/RepoRescue/django-easy-pdf.git
```

Tested on:

- Python 3.13
- Django 6.x
- xhtml2pdf (latest)
- pypdf (replacing the abandoned PyPDF2)

## Quick start

`settings.py`:

```python
INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "easy_pdf",
    # ...
]
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [BASE_DIR / "templates"],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": []},
}]
```

`urls.py`:

```python
from django.urls import re_path
from myapp.views import InvoiceView

urlpatterns = [
    re_path(r"^invoice/$", InvoiceView.as_view(), name="invoice"),
]
```

`views.py`:

```python
from easy_pdf.views import PDFTemplateView

class InvoiceView(PDFTemplateView):
    template_name = "invoice.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update({
            "invoice_no": "INV-2026-0418",
            "customer":   "Acme Coffee Roasters",
            "lines": [
                {"sku": "CB-001", "desc": "Coffee Beans", "qty": 5, "price": 18.50},
                {"sku": "MK-220", "desc": "Milk Frother", "qty": 1, "price": 24.00},
            ],
            "total": 116.25,
        })
        return ctx
```

`templates/invoice.html`:

```django
{% extends "easy_pdf/base.html" %}
{% block content %}
<h1>Invoice {{ invoice_no }}</h1>
<p>Bill to: {{ customer }}</p>
<table>
  <thead><tr><th>SKU</th><th>Description</th><th>Qty</th><th>Price</th><th>Subtotal</th></tr></thead>
  <tbody>
    {% for line in lines %}
    <tr>
      <td>{{ line.sku }}</td>
      <td>{{ line.desc }}</td>
      <td>{{ line.qty }}</td>
      <td>{{ line.price }}</td>
      <td>{{ line.qty|floatformat:2 }} x {{ line.price|floatformat:2 }}</td>
    </tr>
    {% endfor %}
  </tbody>
</table>
<p><strong>Total:</strong> {{ total|floatformat:2 }}</p>
{% endblock %}
```

`GET /invoice/` returns `Content-Type: application/pdf` with a `%PDF-` body —
no JSON-to-PDF round-trip, no headless browser.

---

## What was fixed

Five concrete Django/Py3.13 incompat surfaces, each tied to a real removal:

| # | Surface | Fix | Why |
|---|---------|-----|-----|
| 1 | `from django.utils.six import BytesIO` | `from io import BytesIO` | `django.utils.six` removed in Django 3.0 |
| 2 | `from django.utils.http import urlquote` | `from urllib.parse import quote` | `urlquote` removed in Django 4.0 |
| 3 | `from django.conf.urls import url` | `from django.urls import re_path` | `url()` removed in Django 4.0 |
| 4 | `import PyPDF2` (in test stack) | `import pypdf` | PyPDF2 imports `imp`, removed in Python 3.12 |
| 5 | `nose` / `django_nose` test runner | dropped, plain Django runner | `nose` pulls `imp`, broken on 3.12+ |

Patch is small and surgical — `easy_pdf/rendering.py` (lines 10–11),
`tests/urls.py:3`, `tests/test_settings.py`, `requirements.txt`. No behavioural
changes to public APIs.

## Validation evidence

This fork is published only after passing the RepoRescue **usability gate**
(install on a clean venv, exercise the marquee feature over a real socket,
hit at least three submodules, run a downstream-style scenario, run a bug-hunt
probe set). Verdict: **USABLE**.

- **Marquee feature, real HTTP**: `werkzeug.serving.make_server` binds
  `127.0.0.1:<random>`, `requests.get("/invoice/")` returns
  `Content-Type: application/pdf`, body is a valid PDF (2318 bytes,
  `%PDF-` magic). `pypdf.PdfReader` extracts text and finds
  `Acme Coffee Roasters`, `INV-2026-0418`, `Coffee Beans`, total `116.25`.
- **Submodules exercised**: `easy_pdf.views.PDFTemplateView`,
  `easy_pdf.rendering.{render_to_pdf, html_to_pdf, encode_filename, make_response}`,
  `easy_pdf.exceptions.PDFRenderingError`.
- **Downstream scenario** (`scenario_validate.py`): batch-generate three
  regional sales reports (APAC / EMEA / AMER), then re-open each PDF with
  `pypdf` and assert the business markers and totals
  (APAC=26400.00, EMEA=35950.00, AMER=32350.00). All three pass.
- **Bug-hunt** (`bug_hunt.py`): 7 probes — empty HTML, Polish + Chinese
  Unicode, 50-call state-leak, 8-thread concurrency, 5000-row table,
  `encode_filename` edge cases (empty / null byte / whitespace),
  `PDFRenderingError` shape. **0 findings**, no latent regressions.

Reproduce locally:

```bash
python -m artifacts.django-easy-pdf.usability_validate
python -m artifacts.django-easy-pdf.scenario_validate
python -m artifacts.django-easy-pdf.bug_hunt
```

## Caveat — install-time friction (honest)

`pip install -e .` requires **pinning `svglib==1.5.1` first**.

Newer `svglib` releases pull `rlPyCairo → pycairo`, and `pycairo` is a C
extension that needs `libcairo2-dev` system-installed at build time. On a
fresh container without that header, the install fails. This is a packaging
problem in the upstream `svglib` chain, not in `django-easy-pdf` — it would
hit any xhtml2pdf-based project. Pinning to `1.5.1` (the version known to
work in our T2 environment) sidesteps the C build entirely. If you already
have `libcairo2-dev`, the pin is unnecessary.

## What this rescue does **not** include

- No new features, no rewrite to WeasyPrint, no API additions.
- The original `develop` branch's WeasyPrint backend
  (upstream PR #34) is **not** merged here — that's a separate concern.
- The Sphinx docs site is not republished; refer to upstream
  [docs](https://django-easy-pdf.readthedocs.io/) for tutorial-style content.
  The semantics described there still match this fork.

## Disclaimer

This is an **independent compatibility rescue** of an archived project. It is
not endorsed by the original author (`nigma`) nor by `en.ig.ma software shop`.
The patch was generated by an AI agent (Claude Sonnet) under the RepoRescue
benchmark, then validated by the usability protocol summarised above. Use at
your own risk; review the diff before deploying to production.

## License

BSD 3-Clause, identical to upstream. See `LICENSE`.
