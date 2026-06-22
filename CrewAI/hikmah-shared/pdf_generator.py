"""
hikmah-shared/pdf_generator.py
HTML->PDF via Playwright (headless Chromium) — shared by all 5 HIKMAH projects.

Chromium needs no GTK/Pango/Cairo native libraries, so PDFs work the same on
Windows, macOS, Linux and WSL2. The HTML's own `@media print` rules hide the
ticker / nav / canvas, so no extra stylesheet injection is needed.

Two page geometries:
    desktop -> A4 portrait        (print / archive)
    mobile  -> 90mm-wide roll     (phone-readable single column)

Setup (once):
    pip install playwright
    python -m playwright install chromium

If Playwright or its Chromium build is missing, the function logs a clear
warning and returns None instead of crashing — the HTML output is still made.
"""
import logging
from pathlib import Path

logger = logging.getLogger("hikmah.pdf")

# Chromium page.pdf() options per variant.
PAGE_OPTS = {
    "desktop": {
        "format": "A4",
        "print_background": True,
        "margin": {"top": "12mm", "bottom": "12mm", "left": "14mm", "right": "14mm"},
    },
    "mobile": {
        "width": "90mm",
        "height": "320mm",
        "print_background": True,
        "margin": {"top": "6mm", "bottom": "6mm", "left": "6mm", "right": "6mm"},
    },
}


def generate_pdf(html_path: str, variant: str = "desktop",
                 pdf_path: str = None) -> str | None:
    """Convert one HTML file to a PDF sized for `variant`. Returns path or None."""
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        logger.warning(
            "Playwright unavailable (%s) — skipping PDF for %s. "
            "Run `pip install playwright && python -m playwright install chromium`.",
            e, html_path,
        )
        return None

    src = Path(html_path).resolve()
    pdf_path = Path(pdf_path) if pdf_path else src.with_suffix(".pdf")
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    opts = PAGE_OPTS.get(variant, PAGE_OPTS["desktop"])

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page()
            page.goto(src.as_uri(), wait_until="networkidle")
            page.pdf(path=str(pdf_path), **opts)
            browser.close()
    except Exception as e:
        logger.warning(
            "Chromium PDF render failed (%s) — skipping PDF for %s. "
            "If this is the first run, do `python -m playwright install chromium`.",
            e, html_path,
        )
        return None

    logger.info(f"PDF[{variant}] -> {pdf_path}  ({pdf_path.stat().st_size // 1024} KB)")
    return str(pdf_path)
