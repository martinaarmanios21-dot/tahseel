"""Deterministic profitability metrics. The ONLY place financial formulas live; findings, charts, explanations and
improvement verification all read from here, so the same figure is never computed two ways.

Definitions (monthly periods "YYYY-MM", always per currency; currencies are never combined):
- orders            distinct order IDs with at least one non-cancelled line in the period
- gross_sales       Σ line revenue of non-cancelled lines (price × quantity when no line total is given)
- discounts         Σ line discounts of non-cancelled lines
- refunds           Σ refund amounts from the returns file (by return date). If no returns file exists, lines with
                    status "returned" count as refunded at their net value and the source is flagged.
- net_sales         gross_sales − discounts − refunds
- shipping_income   delivery fees customers paid (sales column shipping_charged; counted once per order: the largest
                    value on the order's lines, because exports often repeat or put it on the first line only)
- cogs              Σ quantity × unit cost for non-cancelled lines whose product has a unit cost (coverage reported).
                    Returned items are not added back (assumption: not resold), so COGS is not reduced by returns.
- variable costs    expenses dated in the period in categories packaging, shipping, payment_fees, marketplace_fees
- gross_profit      net_sales − cogs;  gross_margin = gross_profit / net_sales
- contribution      net_sales + shipping_income − cogs − variable costs;  contribution_margin = contribution / net_sales
- marketing         expenses in category marketing (kept separate: acquisition, not per-order cost)
- fixed costs       rent + payroll + subscriptions + other
- operating_profit  contribution − marketing − fixed costs (only labelled complete when every input exists)
- per order         any of the above ÷ orders;  aov = net_sales ÷ orders
- return_rate       returned units ÷ sold units (needs a returns file)
- break_even_orders (marketing + fixed) ÷ contribution per order, when contribution per order > 0
All money is integer minor units. Ratios are None (not 0) when the denominator is zero or the input is missing.
Expenses are accrual-based (invoice date). Cash view: paid vs unpaid expenses are reported separately.
"""

from __future__ import annotations

from collections import defaultdict

from .ingest import CATEGORIES, FIXED, VARIABLE

DEFINITIONS = {
    "net_sales": {"en": "Sales after discounts and refunds.", "ar": "المبيعات بعد الخصومات والمرتجعات."},
    "cogs": {"en": "What the products you sold cost you (units × unit cost).",
             "ar": "تكلفة المنتجات اللي اتباعت (عدد القطع × تكلفة القطعة)."},
    "gross_profit": {"en": "Net sales minus product costs.", "ar": "المبيعات الصافية ناقص تكلفة المنتجات."},
    "contribution": {"en": "What each order leaves you after product, packaging, shipping and fees. This is the money "
                           "that pays rent, salaries and ads, and then becomes profit.",
                     "ar": "اللي بيفضل لك من كل طلب بعد تكلفة المنتج والتغليف والشحن والرسوم. الفلوس دي هي اللي "
                           "بتدفع الإيجار والمرتبات والإعلانات، واللي يفضل بعد كده هو الربح."},
    "contribution_margin": {"en": "Of every 100 in sales, how much is left after per-order costs.",
                            "ar": "من كل ١٠٠ جنيه مبيعات، بيفضل كام بعد تكاليف الطلب."},
    "operating_profit": {"en": "Contribution minus marketing and fixed costs (rent, salaries, subscriptions).",
                         "ar": "اللي بيفضل بعد كمان الإعلانات والمصاريف الثابتة (إيجار، مرتبات، اشتراكات)."},
    "aov": {"en": "Average money a customer pays per order.", "ar": "متوسط اللي العميل بيدفعه في الطلب الواحد."},
    "return_rate": {"en": "Share of sold units that came back.", "ar": "نسبة القطع اللي رجعت من اللي اتباع."},
    "break_even_orders": {"en": "Orders needed per month to cover marketing and fixed costs.",
                          "ar": "عدد الطلبات اللي محتاجها في الشهر عشان تغطي الإعلانات والمصاريف الثابتة."},
}


def _ratio(a: int | float | None, b: int | float | None) -> float | None:
    if a is None or b in (None, 0):
        return None
    return round(a / b, 4)


def period_of(d: str) -> str:
    return d[:7]


def compute(records: list[dict]) -> dict:
    """All metrics for all periods and currencies, plus coverage information. Pure function of the records."""
    sales = [r for r in records if r["type"] == "sales"]
    costs = {}
    for r in records:
        if r["type"] == "product_costs" and r.get("unit_cost_minor") is not None:
            costs[(r["product"] or "").strip().lower(), r["currency"]] = r["unit_cost_minor"]
    expenses = [r for r in records if r["type"] == "expenses"]
    returns = [r for r in records if r["type"] == "returns"]
    has_returns_file = bool(returns)

    P: dict[tuple, dict] = defaultdict(lambda: {
        "orders": set(), "ship_by_order": {}, "gross_sales": 0, "discounts": 0, "refunds": 0, "cogs": 0, "units": 0.0,
        "revenue_with_cost": 0, "returned_units": 0.0, "lines": 0, "returned_lines_value": 0,
        **{f"exp_{c}": 0 for c in CATEGORIES}, "exp_unpaid": 0, "exp_paid": 0, "exp_unknown_paid": 0})
    products: dict[tuple, dict] = defaultdict(lambda: {"units": 0.0, "gross": 0, "discounts": 0, "refunds": 0,
                                                       "cogs": 0, "cost_known": True})
    channels: dict[tuple, dict] = defaultdict(lambda: {"orders": set(), "net": 0})
    for s in sales:
        if s["status"] == "cancelled":
            continue
        key = (period_of(s["date"]), s["currency"])
        p = P[key]
        p["orders"].add(s["order_id"])
        so = s.get("shipping_charged_minor") or 0
        if so > p["ship_by_order"].get(s["order_id"], 0):
            p["ship_by_order"][s["order_id"]] = so
        p["gross_sales"] += s["gross_minor"]
        p["discounts"] += s["discount_minor"]
        p["units"] += s["quantity"]
        p["lines"] += 1
        prod = (s.get("product") or "(unnamed)").strip()
        pr = products[(key[0], key[1], prod)]
        pr["units"] += s["quantity"]
        pr["gross"] += s["gross_minor"]
        pr["discounts"] += s["discount_minor"]
        uc = costs.get((prod.lower(), s["currency"]))
        if uc is not None:
            c = round(uc * s["quantity"])
            p["cogs"] += c
            p["revenue_with_cost"] += s["gross_minor"]
            pr["cogs"] += c
        else:
            pr["cost_known"] = False
        if s["status"] == "returned" and not has_returns_file:
            v = s["gross_minor"] - s["discount_minor"]
            p["refunds"] += v
            p["returned_lines_value"] += v
            p["returned_units"] += s["quantity"]
            pr["refunds"] += v
        ch = channels[(key[0], key[1], s.get("channel") or "(none)")]
        ch["orders"].add(s["order_id"])
        ch["net"] += s["gross_minor"] - s["discount_minor"]
    for r in returns:
        key = (period_of(r["date"]), r["currency"])
        P[key]["refunds"] += r["refund_minor"]
        P[key]["returned_units"] += r["quantity"]
        if r.get("product"):
            products[(key[0], key[1], r["product"].strip())]["refunds"] += r["refund_minor"]
    for e in expenses:
        key = (period_of(e["date"]), e["currency"])
        P[key][f"exp_{e['category']}"] += e["amount_minor"]
        P[key]["exp_paid" if e.get("paid") is True else "exp_unpaid" if e.get("paid") is False
               else "exp_unknown_paid"] += e["amount_minor"]

    present = {c for e in expenses for c in [e["category"]]}
    periods = []
    for (period, cur), p in sorted(P.items()):
        orders = len(p["orders"])
        net = p["gross_sales"] - p["discounts"] - p["refunds"]
        var = {c: p[f"exp_{c}"] for c in VARIABLE}
        fixed = {c: p[f"exp_{c}"] for c in FIXED}
        materials = p["exp_cogs_materials"]
        cogs_cov = _ratio(p["revenue_with_cost"], p["gross_sales"])
        cogs = p["cogs"]
        ship_income = sum(p["ship_by_order"].values())
        gross_profit = net - cogs
        contribution = gross_profit + ship_income - sum(var.values())
        missing = []
        if not costs:
            missing.append("product_costs")
        elif cogs_cov is not None and cogs_cov < 0.999:
            missing.append("product_costs_partial")
        for c in ("packaging", "shipping"):
            if c not in present:
                missing.append(c)
        if not has_returns_file:
            missing.append("returns")
        if "payment_fees" not in present and "marketplace_fees" not in present:
            missing.append("fees")
        fixed_total = sum(fixed.values())
        operating = contribution - p["exp_marketing"] - fixed_total
        operating_complete = (not missing or missing == ["fees"]) and any(c in present for c in FIXED)
        per = lambda v: _ratio(v, orders)  # noqa: E731
        periods.append({
            "period": period, "currency": cur, "orders": orders, "units": round(p["units"], 2), "lines": p["lines"],
            "gross_sales": p["gross_sales"], "discounts": p["discounts"], "refunds": p["refunds"], "net_sales": net,
            "shipping_income": ship_income,
            "cogs": cogs, "cogs_coverage": cogs_cov, "gross_profit": gross_profit,
            "gross_margin": _ratio(gross_profit, net), "variable": var, "variable_total": sum(var.values()),
            "contribution": contribution, "contribution_margin": _ratio(contribution, net),
            "marketing": p["exp_marketing"], "fixed": fixed, "fixed_total": fixed_total,
            "materials_purchased": materials, "operating_profit": operating,
            "operating_profit_complete": operating_complete,
            "per_order": {"net_sales": per(net), "gross_sales": per(p["gross_sales"]), "discounts": per(p["discounts"]),
                          "shipping_income": per(ship_income),
                          "refunds": per(p["refunds"]), "cogs": per(cogs), **{c: per(v) for c, v in var.items()},
                          "contribution": per(contribution)},
            "aov": per(net), "return_rate": _ratio(p["returned_units"], p["units"]) if has_returns_file or
            p["returned_units"] else None,
            "break_even_orders": (round((p["exp_marketing"] + fixed_total) / per(contribution), 1)
                                  if per(contribution) and per(contribution) > 0 and (p["exp_marketing"] + fixed_total)
                                  else None),
            "expenses_paid": p["exp_paid"], "expenses_unpaid": p["exp_unpaid"],
            "expenses_payment_unknown": p["exp_unknown_paid"],
            "missing": missing, "estimated": bool(missing),
            "refund_source": "returns_file" if has_returns_file else ("order_status" if p["returned_lines_value"]
                                                                      else "none"),
        })
    prod_rows = []
    for (period, cur, name), pr in sorted(products.items()):
        net = pr["gross"] - pr["discounts"] - pr["refunds"]
        prod_rows.append({"period": period, "currency": cur, "product": name, "units": round(pr["units"], 2),
                          "net_sales": net, "cogs": pr["cogs"] if pr["cost_known"] else None,
                          "product_margin": (net - pr["cogs"]) if pr["cost_known"] else None,
                          "product_margin_pct": _ratio(net - pr["cogs"], net) if pr["cost_known"] else None})
    ch_rows = [{"period": k[0], "currency": k[1], "channel": k[2], "orders": len(v["orders"]), "net_before_refunds":
                v["net"]} for k, v in sorted(channels.items())]
    payables = sorted([{"date": e["date"], "due_date": e.get("due_date"), "supplier": e.get("supplier"),
                        "category": e["category"], "amount_minor": e["amount_minor"], "currency": e["currency"],
                        "invoice_id": e.get("invoice_id"), "row": e["row"], "file_id": e.get("file_id")}
                       for e in expenses if e.get("paid") is False], key=lambda x: x.get("due_date") or x["date"])
    return {"periods": periods, "products": prod_rows, "channels": ch_rows, "payables": payables,
            "categories_present": sorted(present), "has_returns_file": has_returns_file,
            "has_product_costs": bool(costs), "currencies": sorted({p["currency"] for p in periods})}


def contribution_bridge(base: dict, cur: dict) -> dict:
    """Exact per-order decomposition of the change in contribution per order between two periods (same currency):
    Δcontribution/order = Δgross/order − Δdiscounts/order + Δshipping_income/order − Δrefunds/order − Δcogs/order
                          − Σ Δvariable/order.
    Every component is reported in minor units per order; the components sum to the total change."""
    if base["currency"] != cur["currency"]:
        raise ValueError("periods have different currencies")
    if not base["orders"] or not cur["orders"]:
        raise ValueError("both periods need orders")
    b, c = base["per_order"], cur["per_order"]
    comps = {"price_and_mix": c["gross_sales"] - b["gross_sales"], "discounts": -(c["discounts"] - b["discounts"]),
             "shipping_income": (c.get("shipping_income") or 0) - (b.get("shipping_income") or 0),
             "refunds": -(c["refunds"] - b["refunds"]), "product_costs": -(c["cogs"] - b["cogs"]),
             **{k: -(c[k] - b[k]) for k in VARIABLE}}
    total = c["contribution"] - b["contribution"]
    comps = {k: round(v, 2) for k, v in comps.items()}
    return {"base_period": base["period"], "current_period": cur["period"], "currency": cur["currency"],
            "base_per_order": round(b["contribution"], 2), "current_per_order": round(c["contribution"], 2),
            "change_per_order": round(total, 2), "components": comps,
            "residual": round(total - sum(comps.values()), 2),
            "orders_base": base["orders"], "orders_current": cur["orders"],
            "total_contribution_change": cur["contribution"] - base["contribution"],
            "volume_effect": round((cur["orders"] - base["orders"]) * b["contribution"], 2),
            "rate_effect": round(cur["orders"] * total, 2)}
