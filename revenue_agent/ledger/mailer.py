"""Real email delivery over SMTP. There is no fake mode: if SMTP is not configured, sending is refused.

A successful result means the SMTP server *accepted* the message for delivery. It does not prove the customer
received or read it, and it says nothing about payment.
"""

from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formatdate

from .store import LedgerSettings


class EmailNotConfigured(RuntimeError):
    pass


class EmailSendError(RuntimeError):
    """The server definitely did not accept the message (connection, auth or explicit rejection)."""


class EmailOutcomeUnknown(RuntimeError):
    """The connection failed while the message was being handed over: it may or may not have been accepted.
    Never retried automatically; a person has to resolve it."""


def send_email(s: LedgerSettings, *, to: str, subject: str, body: str, message_id: str) -> dict:
    if not s.email_configured:
        raise EmailNotConfigured("email sending is not configured (EMAIL_SENDING_ENABLED, SMTP_HOST, SMTP_FROM)")
    msg = EmailMessage()
    msg["From"] = s.smtp_from
    msg["To"] = to
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = message_id  # deterministic per approved follow-up: lets providers de-duplicate retries
    msg.set_content(body, charset="utf-8")
    try:
        if s.smtp_port == 465:
            server = smtplib.SMTP_SSL(s.smtp_host, s.smtp_port, timeout=30, context=ssl.create_default_context())
        else:
            server = smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=30)
    except (smtplib.SMTPException, OSError) as exc:
        raise EmailSendError(f"connect failed: {type(exc).__name__}: {str(exc)[:200]}") from exc
    with server:
        try:
            if s.smtp_port != 465 and s.smtp_starttls:
                server.starttls(context=ssl.create_default_context())
            if s.smtp_user:
                server.login(s.smtp_user, s.smtp_password)
        except (smtplib.SMTPException, OSError) as exc:
            raise EmailSendError(f"handshake/login failed: {type(exc).__name__}: {str(exc)[:200]}") from exc
        try:
            refused = server.send_message(msg)
        except (smtplib.SMTPRecipientsRefused, smtplib.SMTPSenderRefused, smtplib.SMTPDataError) as exc:
            raise EmailSendError(f"rejected by server: {type(exc).__name__}: {str(exc)[:200]}") from exc
        except (smtplib.SMTPException, OSError) as exc:  # timeout / disconnect mid-transfer
            raise EmailOutcomeUnknown(f"{type(exc).__name__}: {str(exc)[:200]}") from exc
    if to in refused:
        raise EmailSendError(f"recipient refused by server: {refused[to]}")
    return {"accepted_by_server": True, "provider": f"smtp:{s.smtp_host}", "message_id": message_id}
