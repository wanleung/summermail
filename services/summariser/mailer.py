"""Email sending functionality for summaries."""
import smtplib
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from html import escape

from shared.config import settings


def send_summary_email(summary_text: str, to_addr: str) -> None:
    """Send the email digest via SMTP.
    
    Args:
        summary_text: Markdown-formatted summary text
        to_addr: Recipient email address
        
    Raises:
        ValueError: If summary_text is empty or to_addr is invalid
    """
    # Input validation
    if not summary_text or not summary_text.strip():
        raise ValueError("summary_text cannot be empty")
    if not to_addr or "@" not in to_addr:
        raise ValueError(f"Invalid recipient email: {to_addr}")
    
    today = date.today().strftime("%A %d %B %Y")
    subject = f"Daily Email Summary — {today}"

    html_body = escape(summary_text).replace("\n", "<br>")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.gmail_user
    msg["To"] = to_addr
    msg.attach(MIMEText(summary_text, "plain"))
    msg.attach(MIMEText(f"<html><body>{html_body}</body></html>", "html"))

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
        server.ehlo()
        server.starttls()
        server.login(settings.gmail_user, settings.gmail_app_password.get_secret_value())
        server.sendmail(settings.gmail_user, [to_addr], msg.as_string())
