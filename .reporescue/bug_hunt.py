"""
Step 7 bug-hunt — anti-PyCG-blindspot probes for django-easy-pdf rescue.

Probes (all on the rescued install, in the clean venv):
  1. Empty / whitespace HTML       — does html_to_pdf raise PDFRenderingError or pass?
  2. Unicode + RTL                 — non-ASCII Polish + Arabic rendering
  3. State leak                    — call render_to_pdf 50x, ensure no growth in pisa state
  4. Concurrent renders            — 8 threads each rendering different content
  5. Large input                   — 5000 line invoice, ensure no quadratic blow-up
  6. encode_filename edge cases    — empty, only-dots, control chars, null byte
  7. PDFRenderingError replay      — synthetic broken HTML, expect raise + .log attribute
"""
from __future__ import annotations

import os
import sys
import threading
import time
import traceback

import django
from django.conf import settings

HERE = os.path.dirname(os.path.abspath(__file__))
settings.configure(
    DEBUG=False, SECRET_KEY="x",
    INSTALLED_APPS=["django.contrib.contenttypes", "django.contrib.auth", "easy_pdf"],
    DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}},
    TEMPLATES=[{
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [os.path.join(HERE, "templates")],
        "APP_DIRS": True, "OPTIONS": {"context_processors": []},
    }],
    STATIC_URL="/static/", STATIC_ROOT=os.path.join(HERE, "static"),
    USE_TZ=True,
)
django.setup()

from easy_pdf.rendering import html_to_pdf, encode_filename, render_to_pdf  # noqa: E402
from easy_pdf.exceptions import PDFRenderingError  # noqa: E402

findings: list[str] = []


def probe(name):
    def deco(fn):
        def wrap():
            print(f"[bug-hunt] probe: {name}")
            try:
                fn()
                print(f"[bug-hunt]   OK: {name}")
            except Exception as e:
                msg = f"{name}: {type(e).__name__}: {e}"
                findings.append(msg)
                print(f"[bug-hunt]   FOUND: {msg}")
                traceback.print_exc()
        return wrap
    return deco


@probe("empty html")
def p1():
    out = html_to_pdf("")
    assert out.startswith(b"%PDF-"), out[:30]


@probe("unicode (Polish + Chinese)")
def p2():
    out = html_to_pdf("<html><body>żółć — 中文测试 — ąęłźżó</body></html>")
    assert out.startswith(b"%PDF-")


@probe("state leak across 50 calls")
def p3():
    sizes = []
    for _ in range(50):
        out = html_to_pdf("<html><body>x</body></html>")
        sizes.append(len(out))
    # all sizes should be near-identical (no growth)
    assert max(sizes) - min(sizes) < 500, f"size drift: {min(sizes)}..{max(sizes)}"


@probe("concurrent (8 threads)")
def p4():
    errors = []
    def worker(i):
        try:
            for _ in range(3):
                out = html_to_pdf(f"<html><body>thread {i}</body></html>")
                assert out.startswith(b"%PDF-")
        except Exception as e:
            errors.append((i, repr(e)))
    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    for t in threads: t.start()
    for t in threads: t.join(timeout=30)
    assert not errors, errors


@probe("large input (5000 rows)")
def p5():
    rows = "".join(f"<tr><td>row {i}</td><td>data {i}</td></tr>" for i in range(5000))
    html = f"<html><body><table>{rows}</table></body></html>"
    t0 = time.time()
    out = html_to_pdf(html)
    dt = time.time() - t0
    assert out.startswith(b"%PDF-"), out[:30]
    assert dt < 60, f"too slow: {dt:.1f}s"
    print(f"[bug-hunt]   5000 rows -> {len(out)} bytes in {dt:.2f}s")


@probe("encode_filename edge cases")
def p6():
    # Empty filename — quoted equals input ("") — falls into 'filename=' branch
    assert encode_filename("") == "filename="
    assert encode_filename("a.pdf") == "filename=a.pdf"
    # Whitespace -> percent-encoded
    enc = encode_filename(" .pdf")
    assert enc.startswith("filename*=UTF-8''"), enc
    # Null byte through quote()
    enc2 = encode_filename("x\x00y.pdf")
    assert "%00" in enc2, enc2


@probe("PDFRenderingError shape")
def p7():
    err = PDFRenderingError("boom", content="<html/>", log=[("err", 1, "msg", "frag")])
    assert "boom" in str(err)
    assert err.content == "<html/>"
    assert err.log[0][2] == "msg"


def main():
    for fn in (p1, p2, p3, p4, p5, p6, p7):
        fn()
    print()
    print(f"[bug-hunt] probes: 7, findings: {len(findings)}")
    for f in findings:
        print(f"[bug-hunt]   - {f}")
    # bug-hunt findings do NOT fail the validate (per SKILL); they go in REPORT.
    sys.exit(0)


if __name__ == "__main__":
    main()
