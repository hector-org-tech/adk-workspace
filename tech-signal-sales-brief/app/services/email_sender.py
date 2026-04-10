"""Send PDF report emails via SMTP.

Supports Gmail (with App Passwords), corporate SMTP, and SendGrid SMTP.

Required env vars:
    SMTP_HOST      — e.g. smtp.gmail.com
    SMTP_PORT      — e.g. 587
    SMTP_USER      — sender email address
    SMTP_PASSWORD  — app password or SMTP credential
    SMTP_FROM      — display "From" address (defaults to SMTP_USER)
"""

import logging
import os
import smtplib
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)


def send_report_email(
    recipients: list[str],
    subject: str,
    body_text: str,
    pdf_bytes: bytes,
    pdf_filename: str,
) -> None:
    """Send an email with a PDF attachment via SMTP.

    Args:
        recipients: List of email addresses.
        subject: Email subject line.
        body_text: Plain-text email body (brief summary).
        pdf_bytes: The PDF report as bytes.
        pdf_filename: Filename for the attachment.

    Raises:
        RuntimeError: If SMTP config is missing or send fails.
    """
    host = os.environ.get("SMTP_HOST", "")
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ.get("SMTP_USER", "")
    password = os.environ.get("SMTP_PASSWORD", "")
    from_addr = os.environ.get("SMTP_FROM", user)

    if not all([host, user, password]):
        raise RuntimeError(
            "Email not configured. Set SMTP_HOST, SMTP_USER, SMTP_PASSWORD env vars."
        )

    msg = MIMEMultipart()
    msg["From"] = from_addr
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = subject

    msg.attach(MIMEText(body_text, "plain"))

    attachment = MIMEBase("application", "pdf")
    attachment.set_payload(pdf_bytes)
    encoders.encode_base64(attachment)
    attachment.add_header(
        "Content-Disposition", f'attachment; filename="{pdf_filename}"'
    )
    msg.attach(attachment)

    try:
        with smtplib.SMTP(host, port, timeout=30) as server:
            server.ehlo()
            if port != 25:
                server.starttls()
                server.ehlo()
            server.login(user, password)
            server.sendmail(from_addr, recipients, msg.as_string())

        logger.info("Email sent to %s: %s", recipients, subject)
    except smtplib.SMTPException:
        logger.exception("Failed to send email to %s", recipients)
        raise
