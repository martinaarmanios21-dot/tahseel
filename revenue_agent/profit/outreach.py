"""Supplier outreach tied to an investigation (never a general email client).

When it is allowed
  quote_request : a current finding shows a cost driver that supplier quotes can address (packaging, shipping,
                  product costs). The request records the finding as its trigger.
  moq_question  : a quote comparison shows a minimum order quantity forcing extra units; the request asks about
                  smaller quantities or price tiers.
  Otherwise creation is refused: no finding, no outreach.

Draft rules
  - Built from the owner's brief only. Missing facts (business name, specification, quantity…) are left as
    [[placeholders]]; nothing is invented. The draft states that it is a request for a quote, not an order.
  - Internal figures (current costs, margins) are never put in the email.
  - Sending needs: no placeholders left, a valid supplier email, explicit approval of the exact
    recipient/subject/body (approval hash), kill switch off, and a configured SMTP server. Otherwise the owner gets a
    copyable draft and the status says it was NOT sent.
  - approved -> sending is a compare-and-set, so a double click can't send twice. A timeout mid-send is recorded as
    send_unknown (never retried automatically).
  - Replies are never collected automatically: the owner reports a reply by adding the quote, which links it here.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import time

from .. import db
from ..ledger import mailer
from ..ledger.store import audit, ledger_settings
from . import diagnosis, quotes as quotes_mod, store

QUOTABLE = {"packaging": "packaging", "shipping": "shipping", "product_costs": "product"}
TERMS = ("unit_price", "price_tiers", "moq", "setup_fee", "delivery_fee", "lead_time", "payment_terms", "samples")
PLACEHOLDER = re.compile(r"\[\[[^\]]+\]\]")
_EMAIL = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")
_COMMITMENT = re.compile(r"\b(we will order|we will buy|confirmed order|purchase order|we commit|we agree to buy)\b|"
                         r"هنطلب أكيد|هنشتري أكيد|أمر شراء|طلب مؤكد|بنأكد الطلب", re.I)


DISCLAIMERS = {"ده طلب عرض سعر للمقارنة، مش طلب شراء مؤكد.",
               "This is a request for a quotation to compare options, not a confirmed order."}


class OutreachError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


TERM_TEXT = {
    "unit_price": {"en": "Unit price", "ar": "سعر الوحدة"},
    "price_tiers": {"en": "Prices at different quantities (price tiers)", "ar": "الأسعار حسب الكميات المختلفة"},
    "moq": {"en": "Minimum order quantity", "ar": "أقل كمية للطلب"},
    "setup_fee": {"en": "Any setup, printing-plate or mould costs", "ar": "أي مصاريف تجهيز أو كليشيه أو قالب"},
    "delivery_fee": {"en": "Delivery cost to us", "ar": "تكلفة التوصيل لينا"},
    "lead_time": {"en": "Production and delivery time", "ar": "مدة التنفيذ والتسليم"},
    "payment_terms": {"en": "Payment terms", "ar": "طريقة الدفع وشروطه"},
    "samples": {"en": "Whether a sample is available, and its cost", "ar": "هل فيه عينة متاحة وتكلفتها"},
}


def opportunities(st: dict) -> list[dict]:
    """Where outreach is justified right now, derived from the investigation (empty when nothing calls for it)."""
    out = []
    d = st.get("diagnosis") or {}
    for f in d.get("findings", []) if d.get("comparable") else []:
        if f["driver"] in QUOTABLE:
            out.append({"purpose": "quote_request", "driver": f["driver"], "category": QUOTABLE[f["driver"]],
                        "finding": {"driver": f["driver"], "label": f.get("label"), "confidence": f["confidence"],
                                    "base_per_order": f["base_value_per_order"],
                                    "current_per_order": f["current_value_per_order"],
                                    "periods": [d["base"]["period"], d["current"]["period"]], "currency": d["currency"]}})
    return out


def _suggested_quantity(st: dict, category: str) -> dict | None:
    d = st.get("diagnosis") or {}
    if category in ("packaging", "shipping") and d.get("comparable"):
        return {"value": d["current"]["orders"], "basis": f"orders in {d['current']['period']}",
                "note": "suggested from your orders; confirm before using it in an email"}
    return None


def create(conn: sqlite3.Connection, iid: str, *, tenant: str, actor: str, purpose: str, driver: str | None = None,
           quote_id: int | None = None, lang: str = "ar") -> dict:
    st = diagnosis.state(conn, iid, tenant, "en")
    if purpose == "quote_request":
        opp = next((o for o in opportunities(st) if o["driver"] == driver), None)
        if opp is None:
            raise OutreachError("no_business_reason", "outreach needs a current cost finding for this driver")
        trigger = opp["finding"] | {"kind": "finding"}
        category, item_key = opp["category"], f"{opp['category']} (from {driver} finding)"
        brief = {"sourcing": "", "specification": "", "quality_requirements": "", "quantity": None,
                 "quantity_unit": "units per month", "terms": ["unit_price", "moq", "setup_fee", "delivery_fee",
                                                               "lead_time", "payment_terms"],
                 "business_name": "", "contact_name": "", "suggested_quantity": _suggested_quantity(st, category),
                 "decision": f"compare against the current {driver} cost per order "
                             f"({opp['finding']['current_per_order']} minor units in {opp['finding']['periods'][1]})"}
        supplier_name = None
    elif purpose == "moq_question":
        q = quotes_mod.get(conn, iid, int(quote_id or 0)) if quote_id else None
        if q is None:
            raise OutreachError("no_business_reason", "choose the quote whose minimum order quantity is the problem")
        cmp = quotes_mod.compare(conn, iid, tenant=tenant, item_key=q["item_key"])
        row = next((r for r in cmp["comparable"] if r["quote_id"] == q["id"]), None)
        if row is None or not row["extra_units_due_to_moq"]:
            raise OutreachError("no_business_reason", "this quote's minimum order quantity doesn't force extra units")
        trigger = {"kind": "moq", "quote_id": q["id"], "moq": q["moq"], "needed": cmp["quantity"],
                   "extra_units": row["extra_units_due_to_moq"], "quantity_source": cmp["quantity_source"]}
        category, item_key = q["category"], q["item_key"]
        brief = {"sourcing": q["item_key"], "specification": q["spec"], "quality_requirements": "",
                 "quantity": cmp["quantity"], "quantity_unit": "units per month", "terms": ["price_tiers", "moq"],
                 "business_name": "", "contact_name": "", "suggested_quantity": None,
                 "decision": f"avoid buying {row['extra_units_due_to_moq']} extra units because of the minimum order"}
        supplier_name = q["supplier"]
    else:
        raise OutreachError("invalid_purpose", "purpose must be quote_request or moq_question")
    subject, body = render(brief, purpose, lang, supplier_name)
    now = time.time()
    with db.tx(conn):
        cur = conn.execute(
            "INSERT INTO outreach(investigation_id, purpose, trigger, category, item_key, brief, language, supplier_name, "
            "subject, body, status, created_at, updated_at) VALUES(?,?,?,?,?,?,?,?,?,?, 'draft', ?, ?)",
            (iid, purpose, json.dumps(trigger), category, item_key[:120], json.dumps(brief, ensure_ascii=False),
             lang, supplier_name, subject, body, now, now))
        audit(conn, actor, "outreach_drafted", tenant=tenant, investigation=iid, outreach=cur.lastrowid,
              purpose=purpose, trigger=trigger.get("kind"))
    return get(conn, iid, cur.lastrowid)


def render(brief: dict, purpose: str, lang: str, supplier_name: str | None = None) -> tuple[str, str]:
    """Deterministic RFQ text from the brief. Unknown facts stay as visible [[placeholders]]."""
    ar = lang == "ar"
    ph = (lambda en, a: f"[[{a if ar else en}]]")  # noqa: E731
    item = brief.get("sourcing") or ph("what you are buying, e.g. printed mailer boxes", "إنت عايز تشتري إيه، مثلاً علب كرتون مطبوعة")
    spec = brief.get("specification") or ph("exact specification: size, material, print, finish", "المواصفات بالظبط: المقاس، الخامة، الطباعة")
    qty = (f"{brief['quantity']:g} {brief.get('quantity_unit') or ''}".strip() if isinstance(brief.get("quantity"), (int, float))
           else ph("approximate quantity, or delete this line and ask only for price tiers", "الكمية التقريبية، أو امسح السطر ده واطلب أسعار حسب الكميات بس"))
    business = brief.get("business_name") or ph("your business name", "اسم نشاطك")
    contact = brief.get("contact_name") or ph("your name", "اسمك")
    hello = (f"أهلاً {supplier_name}،" if supplier_name else "أهلاً حضرتك،") if ar else (f"Hello {supplier_name}," if supplier_name else "Hello,")
    terms = "\n".join(f"- {TERM_TEXT[t]['ar' if ar else 'en']}" for t in brief.get("terms", []) if t in TERM_TEXT)
    quality = brief.get("quality_requirements")
    if ar:
        if purpose == "moq_question":
            subject = f"استفسار عن كميات أقل: {brief.get('sourcing') or ''}".strip()
            lines = [hello, "", f"شكراً على عرض السعر بخصوص {item} ({spec}).",
                     f"احتياجنا الحالي حوالي {qty}، والحد الأدنى في العرض أكبر من كده.",
                     "ممكن تبلّغونا لو فيه إمكانية لكميات أقل، أو أسعار حسب الكميات المختلفة؟", "", terms]
        else:
            subject = f"طلب عرض سعر: {brief.get('sourcing') or ph('', 'المنتج أو الخدمة')}"
            lines = [hello, "", f"إحنا {business}، وبنجمع عروض أسعار لـ {item}.", f"المواصفات: {spec}"]
            if quality:
                lines.append(f"متطلبات الجودة: {quality}")
            lines += [f"الكمية المتوقعة: {qty}", "", "ياريت العرض يوضّح:", terms]
        lines += ["", "ده طلب عرض سعر للمقارنة، مش طلب شراء مؤكد.", "", "شكراً لحضرتك،", f"{contact}", f"{business}"]
    else:
        if purpose == "moq_question":
            subject = f"Question about smaller quantities: {brief.get('sourcing') or ''}".strip()
            lines = [hello, "", f"Thank you for your quotation for {item} ({spec}).",
                     f"Our current need is about {qty}, which is below the minimum order in the quote.",
                     "Could you let us know whether smaller quantities are possible, or share your prices at different "
                     "quantities?", "", terms]
        else:
            subject = f"Request for quotation: {brief.get('sourcing') or ph('product or service', '')}"
            lines = [hello, "", f"We are {business}, and we are collecting quotations for {item}.",
                     f"Specification: {spec}"]
            if quality:
                lines.append(f"Quality requirements: {quality}")
            lines += [f"Expected quantity: {qty}", "", "Please include:", terms]
        lines += ["", "This is a request for a quotation to compare options, not a confirmed order.", "",
                  "Thank you,", f"{contact}", f"{business}"]
    return subject[:200], "\n".join(l for l in lines if l is not None)


def get(conn, iid: str, oid: int) -> dict:
    r = db.one(conn.execute("SELECT * FROM outreach WHERE id=? AND investigation_id=?", (oid, iid)))
    if r is None:
        raise store.NotFound(str(oid))
    for k in ("trigger", "brief", "provider_result"):
        r[k] = json.loads(r[k]) if r[k] else None
    r["placeholders"] = PLACEHOLDER.findall(f"{r['subject']}\n{r['body']}")
    r["linked_quotes"] = [q["id"] for q in quotes_mod.list_for(conn, iid) if q.get("outreach_id") == oid]
    return r


def list_for(conn, iid: str) -> list[dict]:
    return [get(conn, iid, r[0]) for r in conn.execute("SELECT id FROM outreach WHERE investigation_id=? ORDER BY id DESC",
                                                        (iid,))]


def update(conn, iid: str, oid: int, *, tenant: str, actor: str, brief: dict | None = None,
           supplier_name: str | None = None, supplier_email: str | None = None, subject: str | None = None,
           body: str | None = None, regenerate: bool = False, language: str | None = None) -> dict:
    """Edit the brief and/or the text. Any edit drops an approval (it must be approved again)."""
    store.get(conn, iid, tenant)
    o = get(conn, iid, oid)
    if o["status"] not in ("draft", "approved"):
        raise OutreachError("not_editable", f"request is {o['status']}")
    b = o["brief"]
    if brief:
        for k in ("sourcing", "specification", "quality_requirements", "business_name", "contact_name", "quantity_unit"):
            if k in brief:
                b[k] = str(brief[k] or "")[:500]
        if "quantity" in brief:
            q = brief["quantity"]
            try:
                b["quantity"] = float(q) if q not in (None, "") else None
            except (TypeError, ValueError) as exc:
                raise OutreachError("invalid", "quantity must be a number or empty") from exc
            if b["quantity"] is not None and b["quantity"] <= 0:
                raise OutreachError("invalid", "quantity must be positive")
        if "terms" in brief:
            b["terms"] = [t for t in brief["terms"] if t in TERMS]
    name = (supplier_name if supplier_name is not None else o["supplier_name"]) or None
    email = (supplier_email if supplier_email is not None else o["supplier_email"]) or None
    if email and not _EMAIL.match(email.strip()):
        raise OutreachError("invalid_email", "supplier email address is not valid")
    lang = language if language in ("ar", "en") else o["language"]
    if regenerate or brief or lang != o["language"]:
        subject, body = render(b, o["purpose"], lang, name)
    subject = (subject if subject is not None else o["subject"])[:200]
    body = (body if body is not None else o["body"])[:4000]
    with db.tx(conn):
        conn.execute("UPDATE outreach SET brief=?, supplier_name=?, supplier_email=?, subject=?, body=?, language=?, "
                     "status='draft', approval_hash=NULL, approved_by=NULL, updated_at=? WHERE id=?",
                     (json.dumps(b, ensure_ascii=False), name, email.strip() if email else None, subject, body, lang,
                      time.time(), oid))
        audit(conn, actor, "outreach_edited", tenant=tenant, investigation=iid, outreach=oid,
              approval_voided=o["status"] == "approved")
    return get(conn, iid, oid)


def _hash(o: dict) -> str:
    return hashlib.sha256(json.dumps([o["id"], o["investigation_id"], (o["supplier_email"] or "").lower(),
                                      o["subject"], o["body"]], ensure_ascii=False).encode()).hexdigest()


def problems(conn, o: dict, for_send: bool) -> list[dict]:
    out = []
    if o["placeholders"]:
        out.append({"code": "placeholders", "reason": "fill in or delete: " + ", ".join(o["placeholders"][:5])})
    body_wo_disclaimer = "\n".join(l for l in o["body"].splitlines() if l.strip() not in DISCLAIMERS)
    if _COMMITMENT.search(body_wo_disclaimer):
        out.append({"code": "commitment", "reason": "the text reads like a purchase commitment; this is only a quote request"})
    if len(o["body"]) < 40:
        out.append({"code": "too_short", "reason": "message is too short"})
    if for_send:
        if not o["supplier_email"]:
            out.append({"code": "no_recipient", "reason": "add the supplier's email address"})
        if db.kill_switch_on(conn):
            out.append({"code": "kill_switch", "reason": "the emergency stop is on"})
    return out


def approve(conn, iid: str, oid: int, *, tenant: str, actor: str) -> dict:
    store.get(conn, iid, tenant)
    o = get(conn, iid, oid)
    if o["status"] != "draft":
        raise OutreachError("not_draft", f"request is {o['status']}")
    p = problems(conn, o, for_send=False)
    if p:
        raise OutreachError("blocked", "; ".join(x["reason"] for x in p))
    h = _hash(o)
    with db.tx(conn):
        cur = conn.execute("UPDATE outreach SET status='approved', approval_hash=?, approved_by=?, updated_at=? "
                           "WHERE id=? AND status='draft'", (h, actor, time.time(), oid))
        if cur.rowcount != 1:
            raise OutreachError("conflict", "request changed; reload it")
        audit(conn, actor, "outreach_approved", tenant=tenant, investigation=iid, outreach=oid, approval=h[:16])
    return get(conn, iid, oid)


def send(conn, iid: str, oid: int, *, tenant: str, actor: str, approval: str) -> dict:
    store.get(conn, iid, tenant)
    o = get(conn, iid, oid)
    if o["status"] != "approved":
        raise OutreachError("not_approved", f"request is {o['status']}: approve the exact message first")
    if approval != o["approval_hash"] or _hash(o) != o["approval_hash"]:
        raise OutreachError("approval_mismatch", "the message changed after approval")
    p = problems(conn, o, for_send=True)
    s = ledger_settings()
    if not s.email_configured:
        p.append({"code": "email_not_configured", "reason": "email sending is not set up: copy the draft and send it "
                                                            "yourself (it has NOT been sent)"})
    if p:
        audit(conn, actor, "outreach_send", "blocked", tenant=tenant, investigation=iid, outreach=oid,
              codes=[x["code"] for x in p])
        raise OutreachError("blocked", "; ".join(x["reason"] for x in p))
    with db.tx(conn):
        cur = conn.execute("UPDATE outreach SET status='sending', updated_at=? WHERE id=? AND status='approved' AND "
                           "approval_hash=?", (time.time(), oid, approval))
        if cur.rowcount != 1:
            raise OutreachError("not_approved", "already being sent")
    domain = (s.smtp_from.split("@")[-1] or "tahseela.local").strip(">")
    try:
        result = mailer.send_email(s, to=o["supplier_email"], subject=o["subject"], body=o["body"],
                                   message_id=f"<tahseela-rfq-{oid}-{approval[:12]}@{domain}>")
    except mailer.EmailOutcomeUnknown as exc:
        _finish(conn, oid, "send_unknown", {"error": str(exc), "outcome": "unknown"})
        audit(conn, actor, "outreach_send", "unknown", tenant=tenant, investigation=iid, outreach=oid)
        raise OutreachError("send_outcome_unknown", "the connection failed mid-send; check your sent folder") from exc
    except (mailer.EmailSendError, mailer.EmailNotConfigured) as exc:
        _finish(conn, oid, "send_failed", {"error": str(exc)})
        audit(conn, actor, "outreach_send", "failed", tenant=tenant, investigation=iid, outreach=oid, error=str(exc))
        raise OutreachError("send_failed", str(exc)) from exc
    _finish(conn, oid, "sent", result, sent=True)
    audit(conn, actor, "outreach_send", tenant=tenant, investigation=iid, outreach=oid, provider=result["provider"])
    return get(conn, iid, oid)


def _finish(conn, oid: int, status: str, result: dict, sent: bool = False) -> None:
    now = time.time()
    with db.tx(conn):
        conn.execute("UPDATE outreach SET status=?, provider_result=?, sent_at=?, updated_at=? WHERE id=?",
                     (status, json.dumps(result), now if sent else None, now, oid))


def mark_copied(conn, iid: str, oid: int, *, tenant: str, actor: str) -> dict:
    """The owner copied the approved draft and says they sent it themselves (recorded as unverified)."""
    store.get(conn, iid, tenant)
    o = get(conn, iid, oid)
    if o["status"] != "approved":
        raise OutreachError("not_approved", "approve the message before marking it as sent by you")
    _finish(conn, oid, "copied_manual", {"reported_by": actor, "verified": False}, sent=True)
    audit(conn, actor, "outreach_reported_sent", tenant=tenant, investigation=iid, outreach=oid, verified=False)
    return get(conn, iid, oid)


def cancel(conn, iid: str, oid: int, *, tenant: str, actor: str) -> dict:
    store.get(conn, iid, tenant)
    o = get(conn, iid, oid)
    if o["status"] not in ("draft", "approved"):
        raise OutreachError("not_cancellable", f"request is {o['status']}")
    with db.tx(conn):
        conn.execute("UPDATE outreach SET status='cancelled', updated_at=? WHERE id=?", (time.time(), oid))
        audit(conn, actor, "outreach_cancelled", tenant=tenant, investigation=iid, outreach=oid)
    return get(conn, iid, oid)


def link_reply(conn, iid: str, oid: int, quote_id: int) -> None:
    """A quote the owner entered answers this request: the request becomes reply_reported (owner-reported)."""
    o = get(conn, iid, oid)
    with db.tx(conn):
        conn.execute("UPDATE quotes SET outreach_id=? WHERE id=? AND investigation_id=?", (oid, quote_id, iid))
        if o["status"] in ("sent", "copied_manual", "approved", "draft"):
            conn.execute("UPDATE outreach SET status='reply_reported', updated_at=? WHERE id=?", (time.time(), oid))
