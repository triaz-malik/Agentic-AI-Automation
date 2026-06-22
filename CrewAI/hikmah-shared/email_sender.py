"""
hikmah-shared/email_sender.py
Email delivery via the SendGrid v3 HTTP API — shared by all 5 HIKMAH projects.

Sends the desktop HTML as the body and attaches every available PDF variant
(desktop + mobile). Uses SENDGRID_API_KEY from the shared CrewAI/.env.

The function signature is unchanged from the old SMTP version so main.py needs
no edits: `smtp_user` is used as the From address and `smtp_pass` is ignored.

SendGrid requires the From address to be a verified sender. Verify
EMAIL_FROM (or SMTP_USER) under SendGrid -> Settings -> Sender Authentication.
"""
import os, base64, logging
from pathlib import Path
import requests

logger = logging.getLogger("hikmah.email")

SENDGRID_URL = "https://api.sendgrid.com/v3/mail/send"


def send(html_path: str, pdf_paths, subject: str,
         smtp_user: str = None, smtp_pass: str = None, recipients: list = None,
         smtp_host: str = None, smtp_port: int = None,
         html_url: str = None, pdf_url: str = None,
         archive_url: str = None) -> bool:
    api_key = os.getenv("SENDGRID_API_KEY")
    from_email = os.getenv("EMAIL_FROM", smtp_user)
    recipients = recipients or []

    if not api_key:
        logger.error("SENDGRID_API_KEY not set — cannot send email.")
        return False
    if not from_email or not recipients:
        logger.error("Missing From address or recipients — cannot send email.")
        return False

    html_body = Path(html_path).read_text(encoding="utf-8")
    if html_url or pdf_url:
        html_body = html_body.replace("</body>",
                                      _links_bar(html_url, pdf_url, archive_url) + "</body>", 1)

    # Accept either a single path or a {'desktop':..,'mobile':..} dict.
    if isinstance(pdf_paths, dict):
        paths = [p for p in pdf_paths.values() if p]
    elif pdf_paths:
        paths = [pdf_paths]
    else:
        paths = []

    attachments = []
    for pdf in paths:
        data = Path(pdf).read_bytes()
        attachments.append({
            "content": base64.b64encode(data).decode(),
            "type": "application/pdf",
            "filename": Path(pdf).name,
            "disposition": "attachment",
        })

    payload = {
        "personalizations": [{"to": [{"email": r} for r in recipients]}],
        "from": {"email": from_email, "name": "HIKMAH Newsletters"},
        "subject": subject,
        "content": [{"type": "text/html", "value": html_body}],
    }
    if attachments:
        payload["attachments"] = attachments

    try:
        resp = requests.post(
            SENDGRID_URL, json=payload,
            headers={"Authorization": f"Bearer {api_key}",
                     "Content-Type": "application/json"},
            timeout=30,
        )
        if resp.status_code in (200, 201, 202):
            logger.info(f"Email sent via SendGrid -> {recipients}")
            return True
        logger.error(f"SendGrid send failed [{resp.status_code}]: {resp.text[:400]}")
        return False
    except Exception as e:
        logger.error(f"SendGrid request error: {e}")
        return False


def _links_bar(html_url, pdf_url, archive_url) -> str:
    links = []
    if html_url:
        links.append(f'<a href="{html_url}" style="margin-right:10px;padding:8px 16px;'
                     f'border:1px solid #007A80;color:#00C4CC;font-size:12px;font-weight:600;">&#8599; View in Browser</a>')
    if pdf_url:
        links.append(f'<a href="{pdf_url}" style="margin-right:10px;padding:8px 16px;'
                     f'border:1px solid #9A7A2E;color:#E8B84B;font-size:12px;font-weight:600;">&#8595; Download PDF</a>')
    if archive_url:
        links.append(f'<a href="{archive_url}" style="padding:8px 16px;'
                     f'border:1px solid #1C2535;color:#8892A4;font-size:12px;font-weight:600;">&#128193; All Issues</a>')
    return (f'<div style="background:#0A0E17;padding:20px;text-align:center;border-top:2px solid #1C2535;">'
            f'{"".join(links)}</div>')
