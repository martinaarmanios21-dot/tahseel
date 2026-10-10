"""Governed business memory (bounded learning).

Only two sources may write here: the owner confirming something (a column mapping, a business fact, a preference)
and a verified improvement outcome. Model output and uploaded text never write memory. Every entry is per tenant,
so one business's data is never used for another. Entries track how often they were reused and corrected; an
entry corrected more often than it was confirmed-and-reused is retired automatically, and owners can retire any
entry (rollback).
"""

from __future__ import annotations

import json
import sqlite3
import time

from .. import db
from ..ledger.store import audit

KINDS = ("fact", "preference", "mapping", "outcome")
SOURCES = ("owner_confirmed", "verified_outcome")


def remember(conn: sqlite3.Connection, tenant: str, kind: str, key: str, value, source: str) -> None:
    if kind not in KINDS or source not in SOURCES:
        raise ValueError("invalid memory kind/source")
    now = time.time()
    with db.tx(conn):
        conn.execute(
            "INSERT INTO business_memory(tenant_id, kind, key, value, source, created_at, updated_at) "
            "VALUES(?,?,?,?,?,?,?) ON CONFLICT(tenant_id, kind, key) DO UPDATE SET value=excluded.value, "
            "source=excluded.source, status='active', updated_at=excluded.updated_at",
            (tenant, kind, key[:200], json.dumps(value, ensure_ascii=False)[:4000], source, now, now))
        audit(conn, f"memory:{source}", "memory_write", tenant=tenant, kind=kind, key=key[:80])


def entries(conn: sqlite3.Connection, tenant: str, kind: str | None = None, include_retired: bool = False) -> list:
    sql, args = "SELECT * FROM business_memory WHERE tenant_id=?", [tenant]
    if kind:
        sql += " AND kind=?"
        args.append(kind)
    if not include_retired:
        sql += " AND status='active'"
    out = db.rows(conn.execute(sql + " ORDER BY updated_at DESC", args))
    for r in out:
        r["value"] = json.loads(r["value"])
    return out


def retire(conn: sqlite3.Connection, tenant: str, entry_id: int, actor: str) -> None:
    with db.tx(conn):
        cur = conn.execute("UPDATE business_memory SET status='retired', updated_at=? WHERE id=? AND tenant_id=?",
                           (time.time(), entry_id, tenant))
        if cur.rowcount != 1:
            raise LookupError(entry_id)
        audit(conn, actor, "memory_retired", tenant=tenant, entry=entry_id)


def find_mapping(conn: sqlite3.Connection, tenant: str, signature: str) -> dict | None:
    row = db.one(conn.execute("SELECT * FROM business_memory WHERE tenant_id=? AND kind='mapping' AND key=? AND "
                              "status='active'", (tenant, signature)))
    if not row:
        return None
    v = json.loads(row["value"])
    return {"type": v["type"], "mapping": v["mapping"], "signature": signature, "uses": row["uses"]}


def confirm_mapping(conn: sqlite3.Connection, tenant: str, signature: str, rtype: str, mapping: dict,
                    filename: str) -> None:
    existing = find_mapping(conn, tenant, signature)
    if existing and (existing["type"] != rtype or existing["mapping"] != mapping):
        with db.tx(conn):  # the owner corrected a mapping we had learned
            conn.execute("UPDATE business_memory SET corrections=corrections+1 WHERE tenant_id=? AND kind='mapping' "
                         "AND key=?", (tenant, signature))
    remember(conn, tenant, "mapping", signature, {"type": rtype, "mapping": mapping, "example_file": filename[:120]},
             "owner_confirmed")
    _auto_retire(conn, tenant, signature)


def record_use(conn: sqlite3.Connection, tenant: str, kind: str, key: str) -> None:
    with db.tx(conn):
        conn.execute("UPDATE business_memory SET uses=uses+1, updated_at=? WHERE tenant_id=? AND kind=? AND key=?",
                     (time.time(), tenant, kind, key))


def _auto_retire(conn: sqlite3.Connection, tenant: str, key: str) -> None:
    row = db.one(conn.execute("SELECT id, uses, corrections FROM business_memory WHERE tenant_id=? AND kind='mapping' "
                              "AND key=?", (tenant, key)))
    if row and row["corrections"] >= 3 and row["corrections"] > row["uses"]:
        retire(conn, tenant, row["id"], "memory:auto")


def mapping_reliability(conn: sqlite3.Connection, tenant: str) -> dict:
    """Measurable learning signal: how often reused mappings were accepted vs corrected."""
    rows = entries(conn, tenant, "mapping", include_retired=True)
    uses = sum(r["uses"] for r in rows)
    corr = sum(r["corrections"] for r in rows)
    return {"mappings": len(rows), "reuses": uses, "corrections": corr,
            "acceptance_rate": round(uses / (uses + corr), 3) if uses + corr else None}
