"""
hikmah-shared/html_renderer.py
Jinja2 renderer — shared by all 5 HIKMAH projects.

Renders a separate file per VARIANT:
    issue_NNN_desktop.html   (wide, multi-column, full masthead)
    issue_NNN_mobile.html    (single-column, lightweight, phone-first)

Each project passes its own template (which extends the shared base.html.j2),
its output dir, and its brand dict (merged into the payload by main.py).
"""
import logging
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, select_autoescape

logger = logging.getLogger("hikmah.renderer")

SHARED_TEMPLATES = Path(__file__).parent / "templates"
VARIANTS = ("desktop", "mobile")


def render(payload: dict, template_dir: str, template_file: str,
           output_dir: str, variant: str = "desktop",
           pdf_url: str = None, archive_url: str = None) -> str:
    """Render one variant and return the written path."""
    if variant not in VARIANTS:
        raise ValueError(f"variant must be one of {VARIANTS}, got {variant!r}")

    Path(output_dir).mkdir(parents=True, exist_ok=True)
    issue_num = payload["issue_number"]
    out_path = Path(output_dir) / f"issue_{issue_num:03d}_{variant}.html"

    # Search the project's own templates first, then the shared base template.
    env = Environment(
        loader=FileSystemLoader([template_dir, str(SHARED_TEMPLATES)]),
        autoescape=select_autoescape(["html", "j2"]),
        trim_blocks=True, lstrip_blocks=True,
    )
    html = env.get_template(template_file).render(
        variant=variant, pdf_url=pdf_url, archive_url=archive_url, **payload
    )
    out_path.write_text(html, encoding="utf-8")
    logger.info(f"HTML[{variant}] -> {out_path}  ({len(html):,} chars)")
    return str(out_path)


def render_all(payload: dict, template_dir: str, template_file: str,
               output_dir: str, pdf_url: str = None,
               archive_url: str = None) -> dict:
    """Render every variant. Returns {'desktop': path, 'mobile': path}."""
    return {
        v: render(payload, template_dir, template_file, output_dir,
                  variant=v, pdf_url=pdf_url, archive_url=archive_url)
        for v in VARIANTS
    }
