"""
hikmah-shared/pdf_generator.py
WeasyPrint HTML->PDF — shared by all 5 HIKMAH projects.

Two page geometries:
    desktop -> A4 portrait  (print/archive)
    mobile  -> 90mm-wide continuous roll (phone-readable, single column)

WeasyPrint needs the GTK/Pango/Cairo native libraries. On Windows those are
not bundled with pip; if WeasyPrint cannot be imported the function logs a
clear warning and returns None instead of crashing the whole pipeline, so the
HTML output is still produced.
"""
import logging
from pathlib import Path

logger = logging.getLogger("hikmah.pdf")

_COMMON_CSS = """
.ticker-bar,.section-nav,.mobile-pills { display:none !important; }
.masthead-canvas { display:none !important; }
.read-more,.hosted-links { display:none !important; }
.entry-card { break-inside:avoid; page-break-inside:avoid; }
body { background:#fff !important; }
.wrap-outer { box-shadow:none !important; max-width:none !important; }
"""

PAGE_CSS = {
    "desktop": "@page { size:A4; margin:12mm 14mm; }" + _COMMON_CSS,
    # Tall narrow page approximating a phone screen; single column already
    # comes from the mobile HTML variant's grid.
    "mobile":  "@page { size:90mm 320mm; margin:6mm 6mm; }" + _COMMON_CSS
               + ".entry-grid{grid-template-columns:1fr !important;}"
               + ".content-wrap,.masthead-inner,.site-footer{padding-left:8px;padding-right:8px;}",
}


def generate_pdf(html_path: str, variant: str = "desktop",
                 pdf_path: str = None) -> str | None:
    """Convert one HTML file to a PDF sized for `variant`. Returns path or None."""
    try:
        from weasyprint import HTML, CSS
    except Exception as e:  # ImportError or missing native libs
        logger.warning(
            "WeasyPrint unavailable (%s) — skipping PDF for %s. "
            "Install GTK + `pip install weasyprint` to enable PDF output.",
            e, html_path,
        )
        return None

    css = PAGE_CSS.get(variant, PAGE_CSS["desktop"])
    html_path = Path(html_path)
    pdf_path = Path(pdf_path) if pdf_path else html_path.with_suffix(".pdf")
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    HTML(filename=str(html_path)).write_pdf(
        str(pdf_path),
        stylesheets=[CSS(string=css)],
        presentational_hints=True,
    )
    logger.info(f"PDF[{variant}] -> {pdf_path}  ({pdf_path.stat().st_size // 1024} KB)")
    return str(pdf_path)
