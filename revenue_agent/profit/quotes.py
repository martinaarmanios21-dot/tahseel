"""Comparable supplier quotations.

Only the owner's own quotes are used: nothing is fetched, scraped or invented. A quote takes part in the comparison
only when the owner confirmed (1) it is a quote they actually received and (2) its specification matches the
group's requirement. Different specs are never treated as equivalent automatically. Missing terms (MOQ, lead time,
payment terms, delivery) stay "unknown" and are listed; they are not assumed to be zero or favourable. Totals are
computed for the same quantity for every supplier; a web listing is shown as "published price, not a quote".
"""

from __future__ import annotations

import json
import math
import re
import sqlite3
import time

from .. import db
from ..ledger.csv_import import CURRENCY_EXPONENT, parse_amount
from ..ledger.store import audit
from . import metrics, store

CATEGORIES = ("packaging", "shipping", "cogs_materials", "product")
SOURCES = ("written_quote", "verbal", "web_listing")


class QuoteError(ValueError):
    pass


def _money(v, cur: str, field: str, required: bool = False) -> int | None:
    if v in (None, ""):
        if required:
            raise QuoteError(f"{field} is required")
        return None
    try:
        m = parse_amount(str(v), CURRENCY_EXPONENT.get(cur, 2))
    except ValueError as exc:
        raise QuoteError(f"{field}: {exc}") from exc
    if m < 0:
        raise QuoteError(f"{field} must not be negative")
    return m


def add(conn: sqlite3.Connection, iid: str, *, tenant: str, actor: str, data: dict) -> dict:
    inv = store.get(conn, iid, tenant)
    cur = (data.get("currency") or inv["default_currency"]).upper()[:3]
    if cur not in CURRENCY_EXPONENT:
        raise QuoteError("unknown currency")
    item, supplier, spec = (str(data.get(k) or "").strip() for k in ("item_key", "supplier", "spec"))
    if not item or not supplier or not spec:
        raise QuoteError("item group, supplier and the written specification are required")
    if data.get("category") not in CATEGORIES:
        raise QuoteError(f"category must be one of {CATEGORIES}")
    if data.get("source") not in SOURCES:
        raise QuoteError(f"source must be one of {SOURCES}")
    moq = data.get("moq")
    if moq not in (None, ""):
        try:
            moq = float(moq)
        except (TypeError, ValueError) as exc:
            raise QuoteError("minimum order quantity must be a number") from exc
        if moq <= 0:
            raise QuoteError("minimum order quantity must be positive")
    else:
        moq = None
    lead = data.get("lead_time_days")
    try:
        lead = int(lead) if lead not in (None, "") else None
    except (TypeError, ValueError) as exc:
        raise QuoteError("lead time must be a whole number of days") from exc
    outreach_id = data.get("outreach_id")
    if outreach_id not in (None, ""):
        if not conn.execute("SELECT 1 FROM outreach WHERE id=? AND investigation_id=?", (int(outreach_id), iid)).fetchone():
            raise QuoteError("that supplier request doesn't belong to this investigation")
        outreach_id = int(outreach_id)
    else:
        outreach_id = None
    linked_product = (str(data.get("linked_product") or "").strip()[:120] or None)
    if linked_product:
        sold = {(r.get("product") or "").strip() for r in store.records(conn, iid) if r["type"] == "sales"}
        if linked_product not in sold:
            raise QuoteError("linked product must be one of the products in your sales file")
    sources = data.get("field_sources") if isinstance(data.get("field_sources"), dict) else {}
    sources = {k: v for k, v in sources.items() if v in ("typed", "extracted_confirmed")}
    row = (iid, item[:120], data["category"], supplier[:120], spec[:500], cur,
           _money(data.get("unit_price"), cur, "unit price", required=True), moq,
           _money(data.get("setup_fee"), cur, "setup fee"), _money(data.get("delivery_fee"), cur, "delivery fee"),
           (str(data.get("payment_terms") or "").strip()[:120] or None), lead,
           (str(data.get("quality_notes") or "").strip()[:500] or None), data["source"],
           (str(data.get("document_name") or "").strip()[:200] or None), (str(data.get("quote_date") or "")[:10] or None),
           int(bool(data.get("owner_confirmed_quote"))) if data["source"] != "web_listing" else 0,
           int(bool(data.get("spec_confirmed"))), time.time())
    with db.tx(conn):
        cur_ = conn.execute(
            "INSERT INTO quotes(investigation_id, item_key, category, supplier, spec, currency, unit_price_minor, moq, "
            "setup_fee_minor, delivery_fee_minor, payment_terms, lead_time_days, quality_notes, source, document_name, "
            "quote_date, owner_confirmed_quote, spec_confirmed, created_at, outreach_id, linked_product, field_sources) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            row + (outreach_id, linked_product, json.dumps(sources)))
        audit(conn, actor, "quote_added", tenant=tenant, investigation=iid, quote=cur_.lastrowid, source=data["source"],
              outreach=outreach_id)
    if outreach_id:
        from . import outreach as outreach_mod
        outreach_mod.link_reply(conn, iid, outreach_id, cur_.lastrowid)
    return get(conn, iid, cur_.lastrowid)


def get(conn, iid: str, qid: int) -> dict:
    r = db.one(conn.execute("SELECT * FROM quotes WHERE id=? AND investigation_id=?", (qid, iid)))
    if r is None:
        raise store.NotFound(str(qid))
    return r


def list_for(conn, iid: str) -> list[dict]:
    return db.rows(conn.execute("SELECT * FROM quotes WHERE investigation_id=? ORDER BY item_key, id", (iid,)))


def update_flags(conn, iid: str, qid: int, *, tenant: str, actor: str, owner_confirmed_quote=None,
                 spec_confirmed=None) -> dict:
    store.get(conn, iid, tenant)
    q = get(conn, iid, qid)
    oc = q["owner_confirmed_quote"] if owner_confirmed_quote is None else int(bool(owner_confirmed_quote))
    if q["source"] == "web_listing":
        oc = 0  # a published price is never a confirmed quote
    sc = q["spec_confirmed"] if spec_confirmed is None else int(bool(spec_confirmed))
    with db.tx(conn):
        conn.execute("UPDATE quotes SET owner_confirmed_quote=?, spec_confirmed=? WHERE id=?", (oc, sc, qid))
        audit(conn, actor, "quote_confirmed", tenant=tenant, investigation=iid, quote=qid, quote_ok=oc, spec_ok=sc)
    return get(conn, iid, qid)


def delete(conn, iid: str, qid: int, *, tenant: str, actor: str) -> None:
    store.get(conn, iid, tenant)
    get(conn, iid, qid)
    with db.tx(conn):
        conn.execute("DELETE FROM quotes WHERE id=?", (qid,))
        audit(conn, actor, "quote_deleted", tenant=tenant, investigation=iid, quote=qid)


def usage_basis(conn, iid: str, category: str, currency: str) -> dict | None:
    """Monthly quantity to compare at, from the owner's data: packaging/shipping -> orders in the latest month."""
    if category not in ("packaging", "shipping"):
        return None
    ps = [p for p in metrics.compute(store.records(conn, iid))["periods"] if p["currency"] == currency and p["orders"]]
    if not ps:
        return None
    p = ps[-1]
    return {"quantity": p["orders"], "period": p["period"], "current_per_order": p["per_order"].get(category),
            "basis": f"orders in {p['period']} (assumes one unit per order)"}


def compare(conn, iid: str, *, tenant: str, item_key: str, quantity: float | None = None) -> dict:
    inv = store.get(conn, iid, tenant)
    group = [q for q in list_for(conn, iid) if q["item_key"] == item_key]
    if not group:
        raise QuoteError("no quotes in this group")
    currencies = {q["currency"] for q in group}
    cur = group[0]["currency"] if len(currencies) == 1 else inv["default_currency"]
    basis = usage_basis(conn, iid, group[0]["category"], cur)
    if quantity is None:
        if not basis:
            raise QuoteError("enter the quantity you need per month (no order data to derive it)")
        quantity, qsrc = basis["quantity"], basis["basis"]
    else:
        if quantity <= 0:
            raise QuoteError("quantity must be positive")
        qsrc = "entered by you"
    rows, excluded = [], []
    for q in group:
        reasons = []
        if q["currency"] != cur:
            reasons.append(f"different currency ({q['currency']})")
        if q["source"] == "web_listing":
            reasons.append("published price, not a quote you received")
        elif not q["owner_confirmed_quote"]:
            reasons.append("not confirmed as a real quote")
        if not q["spec_confirmed"]:
            reasons.append("specification not confirmed as equivalent")
        unknown = [f for f, v in (("minimum order quantity", q["moq"]), ("delivery fee", q["delivery_fee_minor"]),
                                  ("setup fee", q["setup_fee_minor"]), ("payment terms", q["payment_terms"]),
                                  ("lead time", q["lead_time_days"])) if v is None]
        buy = max(quantity, q["moq"] or 0)
        known_total = round(q["unit_price_minor"] * buy) + (q["setup_fee_minor"] or 0) + (q["delivery_fee_minor"] or 0)
        entry = {"quote_id": q["id"], "supplier": q["supplier"], "spec": q["spec"], "source": q["source"],
                 "value_type": "quoted" if q["source"] == "written_quote" else q["source"],
                 "outreach_id": q.get("outreach_id"), "linked_product": q.get("linked_product"),
                 "field_sources": json.loads(q.get("field_sources") or "{}"),
                 "quote_date": q["quote_date"], "document_name": q["document_name"], "unit_price": q["unit_price_minor"],
                 "units_to_buy": buy, "extra_units_due_to_moq": max(0, buy - quantity),
                 "total_known": known_total, "per_needed_unit": round(known_total / quantity, 2),
                 "unknown_terms": unknown, "total_is_lower_bound": bool({"delivery fee", "setup fee"} & set(unknown)),
                 "payment_terms": q["payment_terms"], "lead_time_days": q["lead_time_days"],
                 "quality_notes": q["quality_notes"], "comparable": not reasons, "not_comparable_because": reasons}
        (rows if not reasons else excluded).append(entry)
    rows.sort(key=lambda r: r["per_needed_unit"])
    current = basis["current_per_order"] if basis else None
    for r in rows:
        r["vs_current_per_unit"] = round(r["per_needed_unit"] - current, 2) if current is not None else None
    return {"item_key": item_key, "category": group[0]["category"], "currency": cur, "quantity": quantity, "quantity_source": qsrc, "comparable": rows,
            "not_comparable": excluded, "current_cost_per_unit": current,
            "lowest_known_total": rows[0]["quote_id"] if rows else None,
            "note": "Lowest known total is not automatically best: check quality notes, lead time, payment terms and "
                    "any unknown terms. Totals with unknown delivery or setup fees are lower bounds.",
            "months_of_stock_from_moq": {r["quote_id"]: (math.ceil(r["units_to_buy"] / quantity * 10) / 10)
                                         for r in rows}}


# ------------------------------------------------------------------------------------------ quote documents

_PATTERNS = {
    "unit_price": r"(?:unit\s*price|price\s*per\s*(?:unit|piece|pc)|سعر\s*(?:الوحدة|القطعة))\s*[:=\-]?\s*([\d٠-٩][\d٠-٩.,٫٬]*)",
    "moq": r"(?:moq|minimum\s*order(?:\s*quantity)?|min\.?\s*qty|(?:أقل|اقل)\s*كمية|الحد\s*الأدنى(?:\s*للطلب)?)\s*[:=\-]?\s*([\d٠-٩][\d٠-٩.,٫٬]*)",
    "setup_fee": r"(?:setup(?:\s*fee)?|plate|mou?ld|تجهيز|كليشيه|قالب)\s*[:=\-]?\s*([\d٠-٩][\d٠-٩.,٫٬]*)",
    "delivery_fee": r"(?:delivery(?:\s*fee|\s*cost)?|shipping(?:\s*fee|\s*cost)?|مصاريف\s*(?:الشحن|التوصيل)|التوصيل)\s*[:=\-]?\s*([\d٠-٩][\d٠-٩.,٫٬]*)",
    "lead_time_days": r"(?:lead\s*time|delivery\s*time|production\s*time|مدة\s*(?:التسليم|التنفيذ))\s*[:=\-]?\s*([\d٠-٩]+)",
    "payment_terms": r"(?:payment\s*terms?|terms\s*of\s*payment|شروط\s*الدفع|طريقة\s*الدفع)\s*[:=\-]?\s*([^\n|;]{3,60})",
}


def extract(filename: str, raw: bytes) -> dict:
    """Suggest quote fields from a text-based PDF / CSV / XLSX quote. Nothing is saved: every suggested value comes
    with the text it was read from and must be checked by the owner before the quote is added. Scans/images are
    refused (no OCR)."""
    from .ingest import read_tables
    try:
        kind, sheets, preview = read_tables(filename, raw)
    except ValueError as exc:
        return {"document_name": filename[:200], "fields": {}, "error": str(exc)}
    text = preview or ""
    if kind == "csv":  # read the raw text: a quote saved as CSV/TXT often has "1,000" inside free text
        from ..ledger.csv_import import decode
        text = decode(raw)[:20000]
    elif kind == "xlsx":
        text = "\n".join(" | ".join(c for c in row if c) for _, rows in sheets for row in rows[:200])
    elif sheets:
        text = (preview or "") + "\n" + "\n".join(" | ".join(r) for _, rows in sheets for r in rows[:200])
    fields = {}
    for key, pat in _PATTERNS.items():
        m = re.search(pat, text, re.I)
        if m:
            val = m.group(1).strip().translate(str.maketrans("٠١٢٣٤٥٦٧٨٩٫٬", "0123456789.,"))
            start = max(0, m.start() - 20)
            fields[key] = {"value": val.rstrip(".,"), "snippet": text[start:m.end() + 20].replace("\n", " ")[:120],
                           "status": "needs_confirmation"}
    return {"document_name": filename[:200], "fields": fields,
            "note": "Suggested from the document's text. Check every value against the document; nothing is used "
                    "until you add the quote.",
            "error": None if fields else "no quote fields recognised: type them in from the document"}
