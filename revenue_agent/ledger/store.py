"""Shared persistence helpers: the append-only audit log, the default tenant, and email (SMTP) settings used by
supplier outreach. The collections ledger's datasets/invoices functions were removed; their tables are kept so no
stored records are lost.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from dataclasses import dataclass

from .. import db
from ..observability import mask


@dataclass(frozen=True)
class LedgerSettings:
    """Email settings (the name is kept for compatibility with existing imports)."""
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password: str
    smtp_from: str
    smtp_starttls: bool
    email_sending_enabled: bool

    @property
    def email_configured(self) -> bool:
        return bool(self.email_sending_enabled and self.smtp_host and self.smtp_from)


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "").split("#", 1)[0].strip() or default)
    except ValueError:
        return default


def ledger_settings() -> LedgerSettings:
    env = os.environ.get
    return LedgerSettings(
        smtp_host=env("SMTP_HOST", "").strip(),
        smtp_port=_int("SMTP_PORT", 587),
        smtp_user=env("SMTP_USER", "").strip(),
        smtp_password=env("SMTP_PASSWORD", ""),
        smtp_from=env("SMTP_FROM", "").strip(),
        smtp_starttls=env("SMTP_STARTTLS", "1").strip().lower() in {"1", "true", "yes", "on"},
        email_sending_enabled=env("EMAIL_SENDING_ENABLED", "0").strip().lower() in {"1", "true", "yes", "on"},
    )


DEFAULT_TENANT = "default"


# ------------------------------------------------------------------------------------------ audit

def audit(conn: sqlite3.Connection, actor: str, action: str, outcome: str = "ok", *, dataset_id: str | None = None,
          invoice_id: str | None = None, followup_id: int | None = None, tenant: str | None = None, **detail) -> None:
    """Append-only audit entry. Emails/secrets are masked; message bodies are never stored here."""
    if tenant is None and dataset_id:
        row = conn.execute("SELECT tenant_id FROM datasets WHERE id=?", (dataset_id,)).fetchone()
        tenant = row[0] if row else None
    conn.execute(
        "INSERT INTO audit_log(ts, actor, action, dataset_id, invoice_id, followup_id, outcome, detail, tenant_id) "
        "VALUES(?,?,?,?,?,?,?,?,?)",
        (time.time(), actor[:80], action, dataset_id, invoice_id, followup_id, outcome,
         mask(json.dumps(detail, default=str, ensure_ascii=False))[:4000], tenant or DEFAULT_TENANT))


def audit_entries(conn: sqlite3.Connection, tenant: str = DEFAULT_TENANT, limit: int = 200) -> list[dict]:
    sql, args = "SELECT * FROM audit_log WHERE tenant_id=?", [tenant]
    sql += " ORDER BY id DESC LIMIT ?"
    args.append(limit)
    out = db.rows(conn.execute(sql, args))
    for r in out:
        r["detail"] = json.loads(r["detail"]) if r["detail"] else {}
    return out
