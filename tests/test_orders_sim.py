"""Order-level profitability and the what-if simulator, checked against hand-calculated values.
Fictional TEST-ONLY data in per-test temp databases."""

import pytest

from profit_fixtures import costs_csv, expenses_csv, sales_csv
from revenue_agent.profit import diagnosis, ingest, metrics, orders, simulator, store, tracking

SALES = b"""Order ID,Date,Product,Quantity,Unit Price,Discount,Channel,Shipping Charged
A,2026-09-01,Shirt,2,500,100,website,50
A,2026-09-01,Dress,1,1000,0,website,50
B,2026-09-02,Shirt,1,500,0,instagram,0
C,2026-09-03,Dress,1,1000,0,website,0
D,2026-09-04,Scarf,1,300,0,instagram,0
"""
COSTS = b"Product,Unit Cost\nShirt,200\nDress,450\n"           # Scarf has no cost -> incomplete order D
EXP = b"""Date,Description,Category,Amount,Order ID
2026-09-30,Mailer boxes,packaging,120,
2026-09-05,Bosta,shipping,60,A
2026-09-05,Bosta,shipping,40,B
2026-09-05,Bosta,shipping,45,Z
2026-09-30,Paymob fees,payment_fees,30,
2026-09-01,Rent,rent,5000,
2026-09-10,Facebook ads,marketing,700,
"""
RETURNS = b"Order ID,Date,Product,Quantity,Refund\nB,2026-09-09,Shirt,1,500\nQ,2026-09-09,Shirt,1,100\n"


def recs(*files):
    out = []
    for name, raw in files:
        out += ingest.parse_file(name, raw).tables[0].records
    return out


def base():
    return recs(("s.csv", SALES), ("c.csv", COSTS), ("e.csv", EXP))


def test_order_level_values_match_hand_calculation():
    o = orders.compute(base(), "EGP")
    by = {x["order_id"]: x for x in o["orders"]}
    a = by["A"]
    # net 1900 + ship income 50 - cogs 850 - shipping 60 (actual) - packaging 30 (120/4) - fees 30*1900/3700
    assert a["net_sales"] == 190000 and a["shipping_income"] == 5000 and a["cogs"] == 85000
    assert a["costs"]["shipping"] == {"amount": 6000, "basis": "actual"}
    assert a["costs"]["packaging"] == {"amount": 3000, "basis": "allocated_per_order"}
    assert a["costs"]["payment_fees"]["basis"] == "allocated_by_value"
    fees = sum(x["costs"]["payment_fees"]["amount"] for x in o["orders"])
    assert fees == 3000  # allocation adds up exactly to the invoice
    assert a["contribution"] == 190000 + 5000 - 85000 - 6000 - 3000 - a["costs"]["payment_fees"]["amount"]
    assert by["C"]["costs"].get("shipping") is None  # monthly pool has no shipping: no invented shipping cost
    assert by["D"]["contribution"] is None and by["D"]["missing"] == ["product_cost:Scarf"]  # missing, not zero
    assert o["incomplete_orders"] == 1


def test_fixed_marketing_and_unmatched_are_never_allocated():
    o = orders.compute(base(), "EGP")
    assert all(set(x["costs"]) <= {"packaging", "shipping", "payment_fees", "marketplace_fees"} for x in o["orders"])
    assert o["unmatched_costs"] == [{"order_id": "Z", "category": "shipping", "date": "2026-09-05", "amount": 4500,
                                     "file_id": None, "row": 5}]


def test_reconciles_with_monthly_metrics_exactly():
    r = base() + recs(("r.csv", RETURNS))
    o = orders.compute(r, "EGP")
    monthly = sum(p["contribution"] for p in metrics.compute(r)["periods"])
    rec = o["reconciliation"]
    assert rec["refunds_linked_to_unknown_orders"] == 10000 and rec["costs_linked_to_unknown_orders"] == 4500
    assert rec["implied_monthly_contribution_total"] == monthly


def test_allocation_can_be_switched_off_and_is_validated():
    o = orders.compute(base(), "EGP", {"packaging": "none"})
    assert all("packaging" not in x["costs"] for x in o["orders"])
    assert o["unallocated"][0]["category"] == "packaging" and o["unallocated"][0]["amount"] == 12000
    assert o["reconciliation"]["implied_monthly_contribution_total"] == sum(
        p["contribution"] for p in metrics.compute(base())["periods"])
    with pytest.raises(ValueError):
        orders.compute(base(), "EGP", {"rent": "per_order"})


def test_actual_cost_orders_are_not_double_charged_by_the_monthly_pool():
    exp = EXP + b"2026-09-30,Courier monthly top-up,shipping,90,\n"
    o = orders.compute(recs(("s.csv", SALES), ("c.csv", COSTS), ("e.csv", exp)), "EGP")
    by = {x["order_id"]: x for x in o["orders"]}
    assert by["A"]["costs"]["shipping"]["amount"] == 6000  # actual stays actual
    assert by["C"]["costs"]["shipping"] == {"amount": 4500, "basis": "allocated_per_order"}  # 90 over C and D only
    assert by["D"]["costs"]["shipping"]["amount"] == 4500


def test_product_breakdown_and_top_seller_insight():
    s = sales_csv(months=("2026-09",), orders=(31,))  # Dress ×11 (1000 each), Shirt ×20 (500 each)
    c = b"Product,Unit Cost\nShirt,150\nDress,900\n"   # Dress: most sales, thin margin
    r = recs(("s.csv", s), ("c.csv", c))
    o = orders.compute(r, "EGP")
    p = {x["product"]: x for x in o["products"]}
    assert p["Dress"]["net_sales"] == 1100000 and p["Shirt"]["net_sales"] == 1000000
    assert p["Shirt"]["contribution_per_unit"] == 35000 and p["Dress"]["contribution_per_unit"] == 10000
    assert sum(x["contribution"] for x in o["products"]) == sum(x["contribution"] for x in o["orders"])
    ins = {i["kind"]: i for i in orders.insights(o, "en")}
    assert ins["top_seller_not_top_earner"]["product"] == "Dress" and ins["top_seller_not_top_earner"]["other"] == "Shirt"
    assert "EGP 100.00" in ins["top_seller_not_top_earner"]["text"] and "EGP 350.00" in ins["top_seller_not_top_earner"]["text"]


def test_loss_orders_identified():
    sales = b"Order ID,Date,Product,Unit Price\nL1,2026-09-01,Gift,100\nL2,2026-09-02,Gift,900\n"
    exp = b"Date,Description,Category,Amount,Order ID\n2026-09-03,Bosta,shipping,150,L1\n"
    o = orders.compute(recs(("s.csv", sales), ("c.csv", b"Product,Unit Cost\nGift,40\n"), ("e.csv", exp)), "EGP")
    assert o["loss_order_count"] == 1 and o["loss_orders"][0]["order_id"] == "L1"
    assert o["loss_orders"][0]["contribution"] == 10000 - 4000 - 15000


# ------------------------------------------------------------------------------------------ simulator

def fixture_recs():
    return recs(("s.csv", sales_csv()), ("c.csv", costs_csv()), ("e.csv", expenses_csv()))


@pytest.mark.parametrize("scenario,delta", [
    ({"packaging_per_order": "10"}, 15 * 72 * 100),
    ({"price_change_pct": {"all": 5}}, 240000),
    ({"product_unit_cost": {"Shirt": "180"}}, 48 * 20 * 100),
    ({"discount_pct": 10}, -480000),
    ({"price_change_pct": {"all": 5}, "volume_change_pct": -10}, round((2220000 + 240000) * 0.9) - 2220000),
])
def test_scenarios_recalculate_from_real_baseline(scenario, delta):
    r = simulator.run(fixture_recs(), "EGP", scenario)
    assert r["type"] == "projection" and r["period"] == "2026-09"
    assert r["baseline"]["contribution"] == 2220000
    assert r["delta"]["contribution"] == delta


def test_price_change_states_demand_assumption_and_unchanged_items():
    r = simulator.run(fixture_recs(), "EGP", {"price_change_pct": {"Shirt": 10}})
    assert any("same quantities" in a for a in r["assumptions"])
    assert any(a.startswith("unchanged from the baseline month") and "packaging" in a for a in r["assumptions"])
    assert "projection" in r["summary"]


def test_unsupported_scenarios_are_refused_with_reason():
    with pytest.raises(simulator.ScenarioError, match="shipping charged"):
        simulator.run(fixture_recs(), "EGP", {"free_shipping": {"threshold": "800", "fee": "50"}})
    with pytest.raises(simulator.ScenarioError, match="no current unit cost"):
        simulator.run(fixture_recs(), "EGP", {"product_unit_cost": {"Hat": "10"}})
    with pytest.raises(simulator.ScenarioError):
        simulator.run(fixture_recs(), "EGP", {"discount_pct": 95})
    with pytest.raises(simulator.ScenarioError):
        simulator.run(fixture_recs(), "EGP", {"delete_records": True})


def test_free_shipping_threshold_uses_customer_delivery_fees():
    r = simulator.run(base(), "EGP", {"free_shipping": {"threshold": "1000", "fee": "40"}})
    # orders: A net 1900 (>=1000 -> 0 fee, was 50), B 500 (<1000 -> 40, was 0), C 1000 (-> 0); D excluded (no cost)
    assert r["baseline"]["shipping_income"] == 5000 and r["projected"]["shipping_income"] == 4000
    assert r["delta"]["contribution"] == -1000 and r["excluded_incomplete_orders"] == 1


def test_simulation_never_modifies_records(conn):
    iid = store.create(conn, title="x")["id"]
    for n, raw in (("s.csv", sales_csv()), ("c.csv", costs_csv()), ("e.csv", expenses_csv())):
        store.add_file(conn, iid, n, raw, tenant="default", actor="t")
    before = store.records(conn, iid)
    simulator.run(before, "EGP", {"price_change_pct": {"all": 20}, "packaging_per_order": "1"})
    assert store.records(conn, iid) == before


def test_api_scenario_saved_tracked_and_verified():
    from fastapi.testclient import TestClient
    from revenue_agent.web.app import app
    c = TestClient(app)
    iid = c.post("/api/investigations", json={"title": "Shop"}).json()["id"]
    c.post(f"/api/investigations/{iid}/files", files=[("files", ("s.csv", sales_csv(), "text/csv")),
                                                       ("files", ("c.csv", costs_csv(), "text/csv")),
                                                       ("files", ("e.csv", expenses_csv(), "text/csv"))])
    st = c.get(f"/api/investigations/{iid}?lang=en").json()
    assert st["orders"]["order_count"] == 132 and st["orders"]["simulator"]["capabilities"]["free_shipping"]["ok"] is False
    assert st["orders"]["reconciliation"]["implied_monthly_contribution_total"] == st["orders"]["monthly_contribution_total"]
    sim = c.post(f"/api/investigations/{iid}/simulate", json={"scenario": {"packaging_per_order": "12"}, "lang": "en"})
    assert sim.status_code == 200 and sim.json()["delta"]["contribution"] == 13 * 72 * 100
    bad = c.post(f"/api/investigations/{iid}/simulate", json={"scenario": {"free_shipping": {"threshold": "1"}}})
    assert bad.status_code == 422
    saved = c.post(f"/api/investigations/{iid}/scenarios", json={"scenario": {"packaging_per_order": "12"},
                                                                 "name": "Cheaper boxes", "track": True}).json()
    x = saved["intervention"]
    assert x["driver"] == "packaging" and x["baseline"]["per_order"] == 2500 and x["projection"]["type"] == "projection"
    assert c.post(f"/api/investigations/{iid}/scenarios/{saved['scenario_id']}/track").status_code == 422  # once only
    c.post(f"/api/investigations/{iid}/interventions/{x['id']}/status", json={"status": "in_progress",
                                                                             "implemented_on": "2026-10-01"})
    c.post(f"/api/investigations/{iid}/files", files=[
        ("files", ("oct.csv", sales_csv(months=("2026-10",), orders=(70,)), "text/csv")),
        ("files", ("oct-e.csv", expenses_csv(months=("2026-10",), box_qty=(70,), box_price=(12,)), "text/csv"))])
    v = c.post(f"/api/investigations/{iid}/interventions/{x['id']}/verify").json()
    assert v["status"] == "verified_improvement" and v["result"]["post_per_order"] == 1200
    orders_page = c.get(f"/api/investigations/{iid}/orders?filter=allocated&limit=5").json()
    assert orders_page["total"] > 0 and orders_page["orders"][0]["costs"]["packaging"]["basis"] == "allocated_per_order"
    al = c.put(f"/api/investigations/{iid}/allocation", json={"allocation": {"packaging": "none"}})
    assert al.status_code == 200 and c.get(f"/api/investigations/{iid}?lang=en").json()["orders"]["unallocated"]


# ------------------------------------------------------------------------------------------ supplier quotes

def _inv_with_data(conn):
    iid = store.create(conn, title="x")["id"]
    for n, raw in (("s.csv", sales_csv()), ("c.csv", costs_csv()), ("e.csv", expenses_csv())):
        store.add_file(conn, iid, n, raw, tenant="default", actor="t")
    return iid


def test_quotes_compare_only_confirmed_equivalent_specs_with_total_cost(conn):
    from revenue_agent.profit import quotes
    iid = _inv_with_data(conn)
    common = {"item_key": "mailer 30x20", "category": "packaging", "spec": "30x20x8 printed kraft", "currency": "EGP"}
    a = quotes.add(conn, iid, tenant="default", actor="o", data=common | {
        "supplier": "Quote A", "unit_price": "14", "moq": "500", "delivery_fee": "150", "setup_fee": "0",
        "payment_terms": "50% upfront", "lead_time_days": 7, "source": "written_quote",
        "owner_confirmed_quote": True, "spec_confirmed": True})
    b = quotes.add(conn, iid, tenant="default", actor="o", data=common | {
        "supplier": "Quote B", "unit_price": "16", "source": "written_quote", "owner_confirmed_quote": True,
        "spec_confirmed": True})
    w = quotes.add(conn, iid, tenant="default", actor="o", data=common | {
        "supplier": "Web shop", "unit_price": "9", "source": "web_listing", "owner_confirmed_quote": True,
        "spec_confirmed": True})
    d = quotes.add(conn, iid, tenant="default", actor="o", data=common | {
        "supplier": "Quote D", "spec": "25x15 plain", "unit_price": "8", "source": "written_quote",
        "owner_confirmed_quote": True})
    r = quotes.compare(conn, iid, tenant="default", item_key="mailer 30x20")
    assert r["quantity"] == 72 and "orders in 2026-09" in r["quantity_source"]
    by = {x["quote_id"]: x for x in r["comparable"]}
    # A: MOQ 500 forces 500 units: 500*14 + 150 = 7150 EGP for 72 needed -> 99.31 per needed unit
    assert by[a["id"]]["units_to_buy"] == 500 and by[a["id"]]["total_known"] == 715000
    assert by[a["id"]]["extra_units_due_to_moq"] == 428
    # B: unknown MOQ/delivery stay unknown, total is a lower bound, not assumed favourable
    assert by[b["id"]]["total_known"] == 72 * 1600 and by[b["id"]]["total_is_lower_bound"]
    assert "minimum order quantity" in by[b["id"]]["unknown_terms"]
    assert r["comparable"][0]["quote_id"] == b["id"]  # per-unit cost, not the headline price, decides the order
    nc = {x["quote_id"]: x["not_comparable_because"] for x in r["not_comparable"]}
    assert "published price, not a quote you received" in nc[w["id"]]
    assert "specification not confirmed as equivalent" in nc[d["id"]]
    assert r["current_cost_per_unit"] == 2500 and "not automatically best" in r["note"]
    assert quotes.update_flags(conn, iid, w["id"], tenant="default", actor="o",
                               owner_confirmed_quote=True)["owner_confirmed_quote"] == 0


def test_quote_validation_and_isolation(conn):
    from revenue_agent.profit import quotes
    iid = _inv_with_data(conn)
    with pytest.raises(quotes.QuoteError):
        quotes.add(conn, iid, tenant="default", actor="o", data={"item_key": "x", "category": "packaging",
                                                               "supplier": "s", "spec": "", "unit_price": "1",
                                                               "source": "written_quote"})
    with pytest.raises(quotes.QuoteError):
        quotes.add(conn, iid, tenant="default", actor="o", data={"item_key": "x", "category": "packaging",
                                                               "supplier": "s", "spec": "y", "unit_price": "-1",
                                                               "source": "written_quote"})
    with pytest.raises(store.NotFound):
        quotes.add(conn, iid, tenant="other", actor="o", data={})
