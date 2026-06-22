"""
hikmah-shared/email_sender.py
SMTP send — shared by all 5 HIKMAH projects.
Sends the desktop HTML as the body and attaches every available PDF
variant (desktop + mobile). Subject comes from the project config.
"""
import logging, smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from pathlib import Path

logger = logging.getLogger("hikmah.email")

def send(html_path: str, pdf_paths, subject: str,
         smtp_user: str, smtp_pass: str, recipients: list,
         smtp_host: str = "smtp.gmail.com", smtp_port: int = 465,
         html_url: str = None, pdf_url: str = None,
         archive_url: str = None) -> bool:
    msg = MIMEMultipart("mixed")
    msg["Subject"] = subject
    msg["From"]    = smtp_user
    msg["To"]      = ", ".join(recipients)

    html_body = Path(html_path).read_text(encoding="utf-8")

    # Inject hosted-links bar before </body>
    if html_url or pdf_url:
        bar = _links_bar(html_url, pdf_url, archive_url)
        html_body = html_body.replace("</body>", bar + "</body>", 1)

    msg.attach(MIMEText(html_body, "html", "utf-8"))

    # Accept either a single path or a {'desktop':..,'mobile':..} dict.
    if isinstance(pdf_paths, dict):
        paths = [p for p in pdf_paths.values() if p]
    elif pdf_paths:
        paths = [pdf_paths]
    else:
        paths = []
    for pdf in paths:
        with open(pdf, "rb") as f:
            att = MIMEApplication(f.read(), _subtype="pdf")
            att.add_header("Content-Disposition", "attachment",
                           filename=Path(pdf).name)
            msg.attach(att)

    try:
        with smtplib.SMTP_SSL(smtp_host, smtp_port) as s:
            s.login(smtp_user, smtp_pass)
            s.sendmail(smtp_user, recipients, msg.as_string())
        logger.info(f"Email sent → {recipients}")
        return True
    except Exception as e:
        logger.error(f"Email failed: {e}")
        return False

def _links_bar(html_url, pdf_url, archive_url) -> str:
    links = []
    if html_url:
        links.append(f'<a href="{html_url}" style="margin-right:10px;padding:8px 16px;'
                     f'border:1px solid #007A80;color:#00C4CC;font-size:12px;font-weight:600;">↗ View in Browser</a>')
    if pdf_url:
        links.append(f'<a href="{pdf_url}" style="margin-right:10px;padding:8px 16px;'
                     f'border:1px solid #9A7A2E;color:#E8B84B;font-size:12px;font-weight:600;">↓ Download PDF</a>')
    if archive_url:
        links.append(f'<a href="{archive_url}" style="padding:8px 16px;'
                     f'border:1px solid #1C2535;color:#8892A4;font-size:12px;font-weight:600;">📁 All Issues</a>')
    return (f'<div style="background:#0A0E17;padding:20px;text-align:center;border-top:2px solid #1C2535;">'
            f'{"".join(links)}</div>')
