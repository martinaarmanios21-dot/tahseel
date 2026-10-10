"""Evidence-driven document requests, contextual supplier outreach, quotes as evidence, and the decision loop.
Fictional TEST-ONLY data (apparel and cosmetics) in per-test temp databases."""

import smtplib

import pytest

from profit_fixtures import costs_csv, expenses_csv, sales_csv
from revenue_agent import db
from revenue_agent.profit import diagnosis, outreach, quotes, simulator, store, tracking

T = "default"


def cosmetics(months=("2026-08", "2026-09"), orders=(60, 72), bottle=(9, 21)):
    s, e = ["Order ID,Date,Product,Quantity,Unit Price,Channel"], ["Date,Supplier,Description,Category,Quantity,Amount"]
    n = 0
    for m, k, b in zip(months, orders, bottle):
        for i in range(k):
            n += 1
            prod, price = ("Serum 30ml", 420) if i % 2 else ("Face cream 50ml", 380)
            s.append(f"C{n:04d},{m}-{i % 27 + 1:02d},{prod},1,{price},website")
        e.append(f"{m}-03,GlassPack,Amber glass bottles,packaging,{k},{k * b}")
        e.append(f"{m}-28,Mylerz,Courier statement,shipping,,{k * 45}")
    return ("\n".join(s) + "\n").encode(), b"Product,Unit Cost\nSerum 30ml,110\nFace cream 50ml,95\n", \
        ("\n".join(e) + "\n").encode()


def new_inv(conn, files):
    iid = store.create(conn, title="t")["id"]
    for name, raw in files:
        assert store.add_file(conn, iid, name, raw, tenant=T, actor="o")["status"] == "imported"
    return iid


def apparel(conn):
    return new_inv(conn, [("s.csv", sales_csv()), ("c.csv", costs_csv()), ("e.csv", expenses_csv())])


def ids(st):
    return [q["id"] for q in st["questions"]]


# 1-3 --------------------------------------------------------------------------------- evidence-driven requests

def test_missing_shipping_triggers_request_with_question_and_alternative(conn):
    s, c, _ = cosmetics()
    iid = new_inv(conn, [("s.csv", s), ("c.csv", c)])
    st = diagnosis.state(conn, iid, T, "en")
    q = next(x for x in st["questions"] if x["id"] == "d_shipping")
    assert q["answers_question"]["en"].startswith("What does delivery") and "by hand" in q["if_unavailable"]["en"]
    assert q["optional"] is True and q["trigger"]["en"]
    ev = {e["key"]: e for e in st["evidence"]}
    assert ev["d_shipping"]["status"] == "missing" and ev["d_sales"]["status"] == "processed"


def test_courier_statement_requested_only_when_it_matters_and_never_again(conn):
    sales = b"Order ID,Date,Product,Unit Price\nL1,2026-09-01,Lip balm,60\nL2,2026-09-02,Lip balm,60\n"
    exp = b"Date,Description,Category,Amount\n2026-09-30,Courier monthly,shipping,150\n"
    iid = new_inv(conn, [("s.csv", sales), ("c.csv", b"Product,Unit Cost\nLip balm,20\n"), ("e.csv", exp)])
    st = diagnosis.state(conn, iid, T, "en")
    assert st["orders"]["loss_order_count"] == 2 and "d_courier_orders" in ids(st)
    statement = b"Date,Description,Category,Amount,Order ID\n2026-09-03,Bosta,shipping,70,L1\n2026-09-03,Bosta,shipping,80,L2\n"
    store.add_file(conn, iid, "bosta.csv", statement, tenant=T, actor="o")
    st2 = diagnosis.state(conn, iid, T, "en")
    assert "d_courier_orders" not in ids(st2)
    assert {e["key"]: e for e in st2["evidence"]}["d_courier_orders"]["status"] == "processed"


def test_dont_know_is_never_asked_again_and_analysis_continues(conn):
    iid = apparel(conn)
    assert "d_returns" in ids(diagnosis.state(conn, iid, T, "en"))
    diagnosis.answer(conn, iid, "d_returns", tenant=T, status="dont_know", value=None, actor="o")
    st = diagnosis.state(conn, iid, T, "en")
    assert "d_returns" not in ids(st)
    assert {e["key"]: e for e in st["evidence"]}["d_returns"]["status"] == "unavailable"
    assert st["diagnosis"]["findings"] and "refunds" in st["diagnosis"]["untested"]   # not treated as zero
    assert simulator.run(store.records(conn, iid), "EGP", {"packaging_per_order": "10"})["delta"]["contribution"] > 0


# 4-6 --------------------------------------------------------------------------------- contextual outreach

def test_packaging_finding_creates_quote_action_and_outreach_needs_a_reason(conn):
    s, c, e = cosmetics()
    iid = new_inv(conn, [("s.csv", s), ("c.csv", c), ("e.csv", e)])
    st = diagnosis.state(conn, iid, T, "en")
    act = next(a for a in st["actions"] if a["kind"] == "request_quotes")
    assert act["driver"] == "packaging" and "packaging" in act["trigger"].lower() and "estimate" in act["impact"]
    o = outreach.create(conn, iid, tenant=T, actor="o", purpose="quote_request", driver="packaging", lang="en")
    assert o["status"] == "draft" and o["trigger"]["kind"] == "finding" and o["placeholders"]
    assert "not a confirmed order" in o["body"] and "2100" not in o["body"]      # internal costs never disclosed
    with pytest.raises(outreach.OutreachError) as e1:
        outreach.create(conn, iid, tenant=T, actor="o", purpose="quote_request", driver="shipping")
    assert e1.value.code == "no_business_reason"


def _ready(conn, iid, lang="en"):
    o = outreach.create(conn, iid, tenant=T, actor="o", purpose="quote_request", driver="packaging", lang=lang)
    return outreach.update(conn, iid, o["id"], tenant=T, actor="o", supplier_name="GlassPack",
                           supplier_email="sales@glasspack.test",
                           brief={"sourcing": "amber glass bottles", "specification": "30ml amber glass, dropper cap",
                                  "quantity": 72, "business_name": "Test Beauty", "contact_name": "Mona"})


def test_outreach_cannot_be_sent_without_explicit_approval_of_exact_text(conn, monkeypatch):
    s, c, e = cosmetics()
    iid = new_inv(conn, [("s.csv", s), ("c.csv", c), ("e.csv", e)])
    blank = outreach.create(conn, iid, tenant=T, actor="o", purpose="quote_request", driver="packaging")
    with pytest.raises(outreach.OutreachError, match="fill in"):
        outreach.approve(conn, iid, blank["id"], tenant=T, actor="o")          # placeholders block approval
    o = _ready(conn, iid)
    assert not o["placeholders"]
    with pytest.raises(outreach.OutreachError) as e1:
        outreach.send(conn, iid, o["id"], tenant=T, actor="o", approval="x")
    assert e1.value.code == "not_approved"
    a = outreach.approve(conn, iid, o["id"], tenant=T, actor="o")
    conn.execute("UPDATE outreach SET body = body || ' extra' WHERE id=?", (o["id"],))
    with pytest.raises(outreach.OutreachError) as e2:
        outreach.send(conn, iid, o["id"], tenant=T, actor="o", approval=a["approval_hash"])
    assert e2.value.code == "approval_mismatch"
    edited = outreach.update(conn, iid, o["id"], tenant=T, actor="o", body="We will order 10,000 units now. " * 3)
    assert edited["status"] == "draft"
    with pytest.raises(outreach.OutreachError, match="commitment"):
        outreach.approve(conn, iid, o["id"], tenant=T, actor="o")


def test_without_email_integration_it_is_a_draft_not_a_send(conn, monkeypatch):
    for k in ("EMAIL_SENDING_ENABLED", "SMTP_HOST", "SMTP_FROM"):
        monkeypatch.delenv(k, raising=False)
    s, c, e = cosmetics()
    iid = new_inv(conn, [("s.csv", s), ("c.csv", c), ("e.csv", e)])
    o = outreach.approve(conn, iid, _ready(conn, iid)["id"], tenant=T, actor="o")
    with pytest.raises(outreach.OutreachError, match="NOT been sent"):
        outreach.send(conn, iid, o["id"], tenant=T, actor="o", approval=o["approval_hash"])
    assert outreach.get(conn, iid, o["id"])["status"] == "approved" and outreach.get(conn, iid, o["id"])["sent_at"] is None
    m = outreach.mark_copied(conn, iid, o["id"], tenant=T, actor="o")
    assert m["status"] == "copied_manual" and m["provider_result"]["verified"] is False
    acts = diagnosis.state(conn, iid, T, "en")["actions"]
    assert any(a["kind"] == "await_reply" for a in acts)


def test_with_smtp_sends_once_and_records_provider_result(conn, monkeypatch):
    sent = []
    monkeypatch.setenv("EMAIL_SENDING_ENABLED", "1")
    monkeypatch.setenv("SMTP_HOST", "smtp.test")
    monkeypatch.setenv("SMTP_FROM", "me@shop.test")
    monkeypatch.setenv("SMTP_STARTTLS", "0")

    class Fake:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def send_message(self, msg):
            sent.append(msg)
            return {}
    monkeypatch.setattr(smtplib, "SMTP", Fake)
    s, c, e = cosmetics()
    iid = new_inv(conn, [("s.csv", s), ("c.csv", c), ("e.csv", e)])
    o = outreach.approve(conn, iid, _ready(conn, iid, "ar")["id"], tenant=T, actor="o")
    r = outreach.send(conn, iid, o["id"], tenant=T, actor="o", approval=o["approval_hash"])
    assert r["status"] == "sent" and r["provider_result"]["accepted_by_server"] and sent[0]["To"] == "sales@glasspack.test"
    assert "طلب عرض سعر" in sent[0]["Subject"]
    with pytest.raises(outreach.OutreachError):
        outreach.send(conn, iid, o["id"], tenant=T, actor="o", approval=o["approval_hash"])
    assert len(sent) == 1
    db.set_kill_switch(conn, True)
    o2 = outreach.approve(conn, iid, _ready(conn, iid)["id"], tenant=T, actor="o")
    with pytest.raises(outreach.OutreachError, match="emergency stop"):
        outreach.send(conn, iid, o2["id"], tenant=T, actor="o", approval=o2["approval_hash"])


# 7-9 --------------------------------------------------------------------------------- quotes as evidence

def test_quote_document_extraction_suggests_and_leaves_unknowns_unknown():
    doc = ("Quotation\nItem: 30ml amber glass bottle\nUnit price: 14.50 EGP\nMOQ: 1,000 pcs\n"
           "Payment terms: 50% advance\n").encode()
    r = quotes.extract("glasspack.csv", doc)
    assert r["fields"]["unit_price"]["value"] == "14.50" and r["fields"]["moq"]["value"] == "1,000"
    assert r["fields"]["payment_terms"]["value"].startswith("50% advance")
    assert all(f["status"] == "needs_confirmation" for f in r["fields"].values())
    assert "lead_time_days" not in r["fields"] and "delivery_fee" not in r["fields"]   # absent = unknown, not zero
    assert quotes.extract("scan.png", b"\x89PNG...")["error"].startswith("unsupported")


def test_reply_quotes_link_to_outreach_and_non_equivalent_specs_stay_apart(conn):
    s, c, e = cosmetics()
    iid = new_inv(conn, [("s.csv", s), ("c.csv", c), ("e.csv", e)])
    o = outreach.mark_copied(conn, iid, outreach.approve(conn, iid, _ready(conn, iid)["id"], tenant=T, actor="o")["id"],
                             tenant=T, actor="o")
    g = o["item_key"]
    base = {"item_key": g, "category": "packaging", "spec": "30ml amber glass, dropper cap", "source": "written_quote",
            "owner_confirmed_quote": True, "spec_confirmed": True}
    q1 = quotes.add(conn, iid, tenant=T, actor="o", data=base | {"supplier": "GlassPack", "unit_price": "14",
                                                               "outreach_id": o["id"], "field_sources": {"unit_price": "extracted_confirmed"}})
    q2 = quotes.add(conn, iid, tenant=T, actor="o", data=base | {"supplier": "BottleCo", "unit_price": "16", "moq": "500"})
    q3 = quotes.add(conn, iid, tenant=T, actor="o", data=base | {"supplier": "PlasticCo", "spec": "30ml PET plastic",
                                                               "unit_price": "6", "spec_confirmed": False})
    assert outreach.get(conn, iid, o["id"])["status"] == "reply_reported" and q1["id"] in outreach.get(conn, iid, o["id"])["linked_quotes"]
    cmp = quotes.compare(conn, iid, tenant=T, item_key=g)
    assert [r["quote_id"] for r in cmp["comparable"]] == [q1["id"], q2["id"]]
    assert cmp["not_comparable"][0]["quote_id"] == q3["id"]                       # cheaper but not equivalent
    r1 = next(r for r in cmp["comparable"] if r["quote_id"] == q1["id"])
    assert "minimum order quantity" in r1["unknown_terms"] and r1["field_sources"] == {"unit_price": "extracted_confirmed"}
    st = diagnosis.state(conn, iid, T, "en")
    kinds = [a["kind"] for a in st["actions"]]
    assert "compare" in kinds and "moq" in kinds                                    # BottleCo MOQ 500 > 72 needed
    m = outreach.create(conn, iid, tenant=T, actor="o", purpose="moq_question", quote_id=q2["id"], lang="en")
    assert m["trigger"]["extra_units"] == 428 and "smaller quantities" in m["body"]
    with pytest.raises(outreach.OutreachError):
        outreach.create(conn, iid, tenant=T, actor="o", purpose="moq_question", quote_id=q1["id"])  # no MOQ problem


def test_verified_quote_feeds_simulator_for_packaging_and_product_costs(conn):
    s, c, e = cosmetics()
    iid = new_inv(conn, [("s.csv", s), ("c.csv", c), ("e.csv", e)])
    recs = store.records(conn, iid)
    pk = simulator.run(recs, "EGP", {"packaging_per_order": "14"})
    assert pk["delta"]["contribution"] == (21 - 14) * 72 * 100 and pk["type"] == "projection"
    q = quotes.add(conn, iid, tenant=T, actor="o", data={"item_key": "serum ingredients", "category": "product",
                                                       "supplier": "LabSupply", "spec": "same formula, 30ml",
                                                       "unit_price": "90", "source": "written_quote",
                                                       "owner_confirmed_quote": True, "spec_confirmed": True,
                                                       "linked_product": "Serum 30ml"})
    assert q["linked_product"] == "Serum 30ml"
    pc = simulator.run(recs, "EGP", {"product_unit_cost": {q["linked_product"]: "90"}})
    assert pc["delta"]["contribution"] == (110 - 90) * 36 * 100
    with pytest.raises(quotes.QuoteError):
        quotes.add(conn, iid, tenant=T, actor="o", data={"item_key": "x", "category": "product", "supplier": "s",
                                                       "spec": "y", "unit_price": "1", "source": "written_quote",
                                                       "linked_product": "Not sold here"})


# 10, 12 ------------------------------------------------------------------------------ projections vs results

def test_projection_never_becomes_observed_or_verified_without_new_records(conn):
    iid = apparel(conn)
    conn.execute("INSERT INTO scenarios(investigation_id, name, params, result, created_at) VALUES(?,?,?,?,0)",
                 (iid, "cheaper boxes", '{"packaging_per_order": "12"}',
                  __import__("json").dumps(simulator.run(store.records(conn, iid), "EGP", {"packaging_per_order": "12"}))))
    sid = conn.execute("SELECT id FROM scenarios").fetchone()[0]
    x = tracking.create_from_scenario(conn, iid, tenant=T, actor="o", scenario_id=sid)
    assert x["projection"]["type"] == "projection" and x["result"] is None and x["status"] == "planned"
    tracking.set_status(conn, iid, x["id"], tenant=T, actor="o", status="in_progress", implemented_on="2026-10-01")
    v = tracking.verify(conn, iid, x["id"], tenant=T, actor="o")
    assert v["status"] == "awaiting_data" and "observed_difference_total" not in (v["result"] or {})
    st = diagnosis.state(conn, iid, T, "en")
    assert any(a["kind"] == "verify" for a in st["actions"])


def test_no_issue_no_gap_means_no_requests_and_no_outreach(conn):
    flat = expenses_csv(box_price=(10, 10))
    iid = new_inv(conn, [("s.csv", sales_csv()), ("c.csv", costs_csv()), ("e.csv", flat)])
    for k in ("d_returns", "d_fees"):
        diagnosis.answer(conn, iid, k, tenant=T, status="dont_know", value=None, actor="o")
    st = diagnosis.state(conn, iid, T, "en")
    assert not st["diagnosis"]["findings"]
    assert st["actions"] == [] and not outreach.opportunities(st)
    with pytest.raises(outreach.OutreachError):
        outreach.create(conn, iid, tenant=T, actor="o", purpose="quote_request", driver="packaging")


def test_api_outreach_flow_and_isolation(monkeypatch):
    from fastapi.testclient import TestClient
    from revenue_agent.web.app import app
    for k in ("EMAIL_SENDING_ENABLED", "SMTP_HOST", "SMTP_FROM"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("TENANT_TOKENS", "acme:acme-token-123456,beta:beta-token-123456")
    A, B = {"X-Tahsila-Token": "acme-token-123456"}, {"X-Tahsila-Token": "beta-token-123456"}
    c = TestClient(app)
    s, cc, e = cosmetics()
    iid = c.post("/api/investigations", headers=A, json={}).json()["id"]
    c.post(f"/api/investigations/{iid}/files", headers=A, files=[("files", ("s.csv", s, "text/csv")),
                                                                  ("files", ("c.csv", cc, "text/csv")),
                                                                  ("files", ("e.csv", e, "text/csv"))])
    o = c.post(f"/api/investigations/{iid}/outreach", headers=A, json={"purpose": "quote_request", "driver": "packaging"}).json()
    assert c.post(f"/api/investigations/{iid}/outreach/{o['id']}/approve", headers=A).status_code == 409  # placeholders
    c.put(f"/api/investigations/{iid}/outreach/{o['id']}", headers=A, json={
        "supplier_email": "a@b.test", "brief": {"sourcing": "bottles", "specification": "30ml amber", "quantity": 72,
                                                "business_name": "Shop", "contact_name": "Mona"}})
    a = c.post(f"/api/investigations/{iid}/outreach/{o['id']}/approve", headers=A).json()
    r = c.post(f"/api/investigations/{iid}/outreach/{o['id']}/send", headers=A, json={"approval": a["approval_hash"]})
    assert r.status_code == 409 and "NOT been sent" in r.json()["detail"]["message"]
    assert c.post(f"/api/investigations/{iid}/outreach/{o['id']}/send", headers=B,
                  json={"approval": a["approval_hash"]}).status_code == 404
    st = c.get(f"/api/investigations/{iid}?lang=ar", headers=A).json()
    assert st["outreach"][0]["status"] == "approved" and st["actions"]
    ex = c.post(f"/api/investigations/{iid}/quotes/extract", headers=A,
                files={"file": ("q.csv", b"Unit price,MOQ\n14,500\n", "text/csv")}).json()
    assert ex["fields"]


def test_outreach_language_can_be_switched_and_regenerates_draft(conn):
    s, c, e = cosmetics()
    iid = new_inv(conn, [("s.csv", s), ("c.csv", c), ("e.csv", e)])
    o = _ready(conn, iid, "en")
    ar = outreach.update(conn, iid, o["id"], tenant=T, actor="o", language="ar")
    assert ar["language"] == "ar" and "طلب عرض سعر" in ar["subject"] and "مش طلب شراء مؤكد" in ar["body"]
    assert "amber glass bottles" in ar["body"] and ar["status"] == "draft"


def test_owner_confirmation_clears_inferred_categories(conn):
    raw = b"Date,Order ID,Area,Delivery Fee,Description\n2026-09-03,X1,Cairo,45,Bosta delivery\n"
    iid = store.create(conn, title="t")["id"]
    first = store.add_file(conn, iid, "bosta.csv", raw, tenant=T, actor="o")
    t = first["summary"]["tables"][0]
    assert t["detected_type"] == "expenses" and t["needs_confirmation"]
    store.remove_file(conn, iid, first["file_id"], tenant=T, actor="o")
    again = store.add_file(conn, iid, "bosta.csv", raw, tenant=T, actor="o",
                           overrides={"csv": {"type": "expenses", "mapping": t["mapping"]}}, confirm=True)
    assert again["summary"]["tables"][0]["needs_confirmation"] == []
    rec = store.records(conn, iid)[0]
    assert rec["category"] == "shipping" and "category_owner_confirmed" in rec["flags"]
