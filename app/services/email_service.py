"""Outbound email via SMTP (password reset & other transactional mail).

Works with any SMTP provider (Gmail app password, SendGrid, Mailgun, Resend
SMTP, Amazon SES, …) — configure SMTP_* in the environment. When SMTP is not
configured, sending is a no-op that logs the message (so flows stay testable in
development without an email account).
"""
from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage

from app.config import settings

logger = logging.getLogger(__name__)


def is_configured() -> bool:
    """True when enough SMTP settings are present to actually send mail."""
    return bool(settings.smtp_host and settings.smtp_user and settings.smtp_password)


def send_email(to: str, subject: str, text: str, html: str | None = None) -> bool:
    """Send one email. Returns True if sent, False if skipped/failed.

    Never raises — callers treat email as best-effort so a mail outage can't
    break the request (e.g. the password-reset endpoint still responds 200).
    """
    if not is_configured():
        logger.warning(
            "SMTP not configured — email to %s NOT sent. Subject: %s", to, subject
        )
        return False

    msg = EmailMessage()
    msg["From"] = settings.smtp_from or settings.smtp_user
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(text)
    if html:
        msg.add_alternative(html, subtype="html")

    try:
        context = ssl.create_default_context()
        if settings.smtp_port == 465:
            with smtplib.SMTP_SSL(
                settings.smtp_host, settings.smtp_port, timeout=15, context=context
            ) as server:
                server.login(settings.smtp_user, settings.smtp_password)
                server.send_message(msg)
        else:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as server:
                server.starttls(context=context)
                server.login(settings.smtp_user, settings.smtp_password)
                server.send_message(msg)
        logger.info("Sent email to %s (%s)", to, subject)
        return True
    except Exception as exc:  # noqa: BLE001 — email is best-effort
        logger.error("Failed to send email to %s: %s", to, exc)
        return False


def send_password_reset(to: str, reset_link: str) -> bool:
    """Email a password-reset link. Falls back to logging the link when SMTP is
    unconfigured, so the flow can be completed in development."""
    subject = "Reset your AutoSocial AI password"
    text = (
        "We received a request to reset your AutoSocial AI password.\n\n"
        f"Reset it here (link expires in {settings.password_reset_expire_minutes} "
        f"minutes):\n{reset_link}\n\n"
        "If you didn't request this, you can safely ignore this email."
    )
    html = f"""\
<div style="font-family:system-ui,Segoe UI,Arial,sans-serif;max-width:480px;margin:auto">
  <h2 style="margin:0 0 8px">Reset your password</h2>
  <p style="color:#475569">We received a request to reset your AutoSocial AI password.</p>
  <p style="margin:24px 0">
    <a href="{reset_link}"
       style="background:#15803d;color:#fff;padding:12px 20px;border-radius:8px;
              text-decoration:none;font-weight:600;display:inline-block">
      Reset password
    </a>
  </p>
  <p style="color:#64748b;font-size:13px">
    This link expires in {settings.password_reset_expire_minutes} minutes.
    If you didn't request it, you can safely ignore this email.
  </p>
  <p style="color:#94a3b8;font-size:12px;word-break:break-all">{reset_link}</p>
</div>"""
    sent = send_email(to, subject, text, html)
    if not sent:
        # Dev fallback: make the link discoverable in the server logs.
        logger.info("Password reset link for %s: %s", to, reset_link)
    return sent
