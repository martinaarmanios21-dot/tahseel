"""Persistence for investigations. Every query is scoped by tenant (another tenant's ID behaves like a missing one)."""

from __future__ import annotations

import json
import sqlite3
import time
import uuid

from .. import db
from ..ledger.csv_import import CURRENCY_EXPONENT, parse_amount, parse_date
from ..ledger.store import DEFAULT_TENANT, audit
from . import ingest, memory


class NotFound(LookupError):
    pass


def create(conn: sqlite3.Connection, *, tenant: str = DEFAULT_TENANT, title: str = "", currency: str = "EGP",
           actor: str = "owner") -> dict:
    iid = f"inv-{uuid.uuid4().hex[:10]}"
    now = time.time()
    with db.tx(conn):
        conn.execute("INSERT INTO investigations(id, tenant_id, title, default_currency, created_at, updated_at) "
                     "VALUES(?,?,?,?,?,?)", (iid, tenant, (title or "")[:120] or "My business", currency.upper()[:3],
                                             now, now))
        audit(conn, actor, "investigation_created", tenant=tenant, investigation=iid)
    return get(conn, iid, tenant)


def get(conn: sqlite3.Connection, iid: str, tenant: str = DEFAULT_TENANT) -> dict:
    r = db.one(conn.execute("SELECT * FROM investigations WHERE id=? AND tenant_id=?", (iid, tenant)))
    if r is None:
        raise NotFound(iid)
    r["profile"] = json.loads(r["profile"])
    r["settings"] = json.loads(r.get("settings") or "{}")
    return r


def list_all(conn: sqlite3.Connection, tenant: str = DEFAULT_TENANT) -> list[dict]:
    out = db.rows(conn.execute(
        "SELECT i.*, (SELECT COUNT(*) FROM inv_files f WHERE f.investigation_id=i.id AND f.status='imported') "
        "AS file_count FROM investigations i WHERE i.tenant_id=? ORDER BY i.updated_at DESC", (tenant,)))
    for r in out:
        r["profile"] = json.loads(r["profile"])
        r["settings"] = json.loads(r.get("settings") or "{}")
    return out


def touch(conn: sqlite3.Connection, iid: str, **fields) -> None:
    sets = ", ".join(f"{k}=?" for k in fields)
    vals = [json.dumps(v, ensure_ascii=False) if k in ("profile", "settings") else v for k, v in fields.items()]
    conn.execute(f"UPDATE investigations SET {sets + ', ' if sets else ''}updated_at=? WHERE id=?",
                 (*vals, time.time(), iid))


def delete(conn: sqlite3.Connection, iid: str, tenant: str, actor: str) -> None:
    get(conn, iid, tenant)
    with db.tx(conn):
        for t in ("inv_records", "inv_files", "inv_questions", "interventions", "scenarios", "quotes", "outreach"):
            conn.execute(f"DELETE FROM {t} WHERE investigation_id=?", (iid,))
        conn.execute("DELETE FROM investigations WHERE id=?", (iid,))
        audit(conn, actor, "investigation_deleted", tenant=tenant, investigation=iid)


# ------------------------------------------------------------------------------------------ files

def add_file(conn: sqlite3.Connection, iid: str, filename: str, raw: bytes, *, tenant: str, actor: str,
             date_format: str = "auto", overrides: dict | None = None, confirm: bool = False) -> dict:
    """Parse a file and store its valid records. Uses an owner-confirmed mapping for the same layout if one exists.
    `confirm=True` with overrides records the mapping as owner-confirmed (business memory, reusable)."""
    inv = get(conn, iid, tenant)
    reused = {}
    if not overrides:
        pre = ingest.parse_file(filename, raw, default_currency=inv["default_currency"], date_format=date_format)
        for t in pre.tables:
            m = memory.find_mapping(conn, tenant, ingest.header_signature(t.headers))
            if m:
                reused[t.sheet] = m
        overrides = {k: {"type": v["type"], "mapping": v["mapping"]} for k, v in reused.items()} or None
    fr = ingest.parse_file(filename, raw, default_currency=inv["default_currency"], date_format=date_format,
                           overrides=overrides)
    if confirm and overrides:  # the owner reviewed this file in "Fix columns": inferred categories are now confirmed
        for t in fr.tables:
            if t.sheet in overrides:
                for rec in t.records:
                    if "category_inferred" in rec.get("flags", []):
                        rec["flags"] = [f for f in rec["flags"] if f != "category_inferred"] + ["category_owner_confirmed"]
                t.needs_confirmation = [n for n in t.needs_confirmation if "inferred" not in n]
    summary = fr.summary()
    for t in summary["tables"]:
        if t["sheet"] in reused:
            t["mapping_reused_from_memory"] = True
    dup = conn.execute("SELECT id FROM inv_files WHERE investigation_id=? AND sha256=? AND status='imported'",
                       (iid, fr.sha256)).fetchone()
    status = "failed" if fr.fatal or not any(t.records for t in fr.tables) else "imported"
    if dup and status == "imported":
        summary["fatal"] = f"this exact file was already imported (file #{dup[0]}); nothing was added twice"
        status = "failed"
    with db.tx(conn):
        cur = conn.execute("INSERT INTO inv_files(investigation_id, filename, kind, sha256, summary, status, "
                           "uploaded_at) VALUES(?,?,?,?,?,?,?)", (iid, fr.filename, fr.kind, fr.sha256,
                                                                 json.dumps(summary, ensure_ascii=False), status,
                                                                 time.time()))
        fid = cur.lastrowid
        if status == "imported":
            for t in fr.tables:
                for rec in t.records:
                    rec["file_id"] = fid
                    conn.execute("INSERT INTO inv_records(investigation_id, file_id, rtype, data) VALUES(?,?,?,?)",
                                 (iid, fid, rec["type"], json.dumps(rec, ensure_ascii=False)))
        touch(conn, iid)
        audit(conn, actor, "investigation_file", "ok" if status == "imported" else "failed", tenant=tenant,
              investigation=iid, file_id=fid, filename=fr.filename, status=status,
              rows=sum(len(t.records) for t in fr.tables))
    if confirm and overrides and status == "imported":
        for t in fr.tables:
            if t.sheet in overrides and t.detected_type:
                memory.confirm_mapping(conn, tenant, ingest.header_signature(t.headers), t.detected_type,
                                       t.mapping, filename)
    elif reused and status == "imported":
        for v in reused.values():
            memory.record_use(conn, tenant, "mapping", v["signature"])
    return {"file_id": fid, "status": status, "summary": summary}


def files(conn: sqlite3.Connection, iid: str) -> list[dict]:
    out = db.rows(conn.execute("SELECT * FROM inv_files WHERE investigation_id=? ORDER BY id", (iid,)))
    for f in out:
        f["summary"] = json.loads(f["summary"])
    return out


def remove_file(conn: sqlite3.Connection, iid: str, file_id: int, *, tenant: str, actor: str) -> None:
    get(conn, iid, tenant)
    with db.tx(conn):
        cur = conn.execute("UPDATE inv_files SET status='removed' WHERE id=? AND investigation_id=?", (file_id, iid))
        if cur.rowcount != 1:
            raise NotFound(str(file_id))
        conn.execute("DELETE FROM inv_records WHERE investigation_id=? AND file_id=?", (iid, file_id))
        audit(conn, actor, "investigation_file_removed", tenant=tenant, investigation=iid, file_id=file_id)


def records(conn: sqlite3.Connection, iid: str) -> list[dict]:
    return [json.loads(r[0]) for r in conn.execute("SELECT data FROM inv_records WHERE investigation_id=? ORDER BY id",
                                                   (iid,))]


class CurrencyLocked(ValueError):
    pass


def set_currency(conn: sqlite3.Connection, iid: str, *, tenant: str, actor: str, currency: str) -> dict:
    """Correct the currency the owner's files are in (e.g. they picked SAR but the files are in EGP).

    This is a RE-LABEL, never a conversion: no exchange rate is used. Only amounts that took the investigation's
    currency by default change (rows from files with no currency column, and typed-in totals). Rows whose file had a
    currency column keep their own currency. Amounts are re-scaled only for a different number of decimals
    (e.g. EGP 2 → KWD 3). Refused once quotes, outreach, scenarios or experiments exist, because their saved
    figures and baselines were made in the old currency.
    """
    inv = get(conn, iid, tenant)
    new = (currency or "").upper().strip()
    if new not in CURRENCY_EXPONENT:
        raise ValueError(f"unknown currency '{currency}'")
    old = inv["default_currency"]
    if new == old:
        return {"currency": new, "relabelled": 0}
    for table, what in (("quotes", "quotes"), ("outreach", "supplier requests"), ("scenarios", "saved scenarios"),
                        ("interventions", "experiments")):
        if conn.execute(f"SELECT 1 FROM {table} WHERE investigation_id=? LIMIT 1", (iid,)).fetchone():
            raise CurrencyLocked(f"the currency can't change once {what} exist; start a new investigation instead")
    has_currency_col: dict[tuple[int, str], bool] = {}
    for fid, summary in conn.execute("SELECT id, summary FROM inv_files WHERE investigation_id=?", (iid,)):
        for t in json.loads(summary).get("tables", []):
            has_currency_col[(fid, t.get("sheet"))] = "currency" in (t.get("mapping") or {})
    shift = CURRENCY_EXPONENT[new] - CURRENCY_EXPONENT.get(old, 2)
    changed = 0
    with db.tx(conn):
        for rid, data in conn.execute("SELECT id, data FROM inv_records WHERE investigation_id=?", (iid,)).fetchall():
            rec = json.loads(data)
            from_column = rec.get("file_id") is not None and has_currency_col.get((rec["file_id"], rec.get("sheet")), False)
            if from_column or rec.get("currency") != old:
                continue
            for k, v in list(rec.items()):
                if k.endswith("_minor") and isinstance(v, int):
                    scaled = v * 10 ** shift if shift >= 0 else v / 10 ** -shift
                    if scaled != int(scaled):
                        raise ValueError(f"{new} has fewer decimals than {old}; an amount would lose its fractional part")
                    rec[k] = int(scaled)
            rec["currency"] = new
            conn.execute("UPDATE inv_records SET data=? WHERE id=?", (json.dumps(rec, ensure_ascii=False), rid))
            changed += 1
        conn.execute("UPDATE investigations SET default_currency=?, updated_at=? WHERE id=?", (new, time.time(), iid))
        audit(conn, actor, "investigation_currency_set", tenant=tenant, investigation=iid, old=old, new=new,
              relabelled=changed)
    return {"currency": new, "relabelled": changed}


def add_manual_expense(conn: sqlite3.Connection, iid: str, *, tenant: str, actor: str, category: str, month: str,
                       amount: str, note: str = "") -> dict:
    """Owner types a monthly total when no file exists (e.g. 'shipping in 2026-09 was 12,000'). Stored with
    source 'manual' so every finding that uses it says so."""
    inv = get(conn, iid, tenant)
    if category not in ingest.CATEGORIES:
        raise ValueError(f"category must be one of {', '.join(ingest.CATEGORIES)}")
    d = parse_date(f"{month}-01" if len(month) == 7 else month, "YMD")[0]
    cur = inv["default_currency"]
    minor = parse_amount(amount, CURRENCY_EXPONENT.get(cur, 2))
    if minor <= 0:
        raise ValueError("amount must be positive")
    rec = {"type": "expenses", "currency": cur, "sheet": "manual", "row": 0, "flags": ["manual_entry"],
           "date": d.isoformat(), "amount_minor": minor, "category": category, "description": note[:200] or None,
           "supplier": None, "quantity": None, "invoice_id": None, "paid": None, "file_id": None}
    with db.tx(conn):
        conn.execute("INSERT INTO inv_records(investigation_id, file_id, rtype, data) VALUES(?,?,?,?)",
                     (iid, None, "expenses", json.dumps(rec, ensure_ascii=False)))
        touch(conn, iid)
        audit(conn, actor, "investigation_manual_entry", tenant=tenant, investigation=iid, category=category,
              month=d.isoformat()[:7], amount_minor=minor)
    return rec
