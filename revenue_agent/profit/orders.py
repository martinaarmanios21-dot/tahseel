"""Order-level contribution profit, with every cost labelled ACTUAL or ALLOCATED, and a reconciliation to the
monthly figures from metrics.py.

Per order (non-cancelled sales lines grouped by order ID, one currency):
  net_sales      = Σ line gross − Σ line discounts                               (actual)
  shipping_income= largest shipping_charged on the order's lines                  (actual)
  refunds        = returns-file rows with this order ID; else lines marked returned (actual)
  cogs           = Σ quantity × product unit cost; missing if any product has no unit cost
  variable costs = per category:
      actual      expense rows that carry this order ID (courier / gateway statements)
      allocated   the month's expense rows WITHOUT an order ID, shared only across that month's orders that have no
                  actual cost in that category, by a method whose cost driver is defensible:
                    packaging, shipping       -> per_order  (one package / one shipment per order)
                    payment_fees, marketplace -> by_value   (fees scale with order value)
                  The owner can switch any category to "none" (left unallocated). Rounding remainders are placed so the
                  allocated amounts add up exactly to the invoice totals.
  NEVER allocated: rent, payroll, subscriptions, other, marketing, materials purchases (no per-order driver).
  contribution   = net_sales + shipping_income − refunds − cogs − Σ variable costs   (None when cogs is missing)

Reconciliation (whole dataset, per currency):
  monthly contribution (metrics) = Σ order contribution computed with known costs
                                   − unallocated order-type costs − costs linked to unknown orders
                                   − refunds linked to unknown orders
Product breakdown: an order's shared costs and refunds are split across its lines by line net value (labelled).
"""

from __future__ import annotations

from collections import defaultdict

from .ingest import VARIABLE

DEFAULT_ALLOCATION = {"packaging": "per_order", "shipping": "per_order", "payment_fees": "by_value",
                      "marketplace_fees": "by_value"}
ALLOWED = {"packaging": ("per_order", "none"), "shipping": ("per_order", "none"),
           "payment_fees": ("by_value", "per_order", "none"), "marketplace_fees": ("by_value", "none")}
METHOD_TEXT = {
    "per_order": {"en": "shared equally across the month's orders (one package/shipment per order)",
                  "ar": "اتقسمت بالتساوي على طلبات الشهر (طرد أو شحنة واحدة لكل طلب)"},
    "by_value": {"en": "shared in proportion to each order's value (fees grow with order value)",
                 "ar": "اتقسمت حسب قيمة كل طلب (الرسوم بتزيد مع قيمة الطلب)"},
    "none": {"en": "not allocated to orders (shown separately)", "ar": "مااتوزعتش على الطلبات (ظاهرة لوحدها)"},
    "actual": {"en": "actual cost recorded for this order", "ar": "تكلفة فعلية متسجلة للطلب ده"},
}


def _split(total: int, weights: list[float]) -> list[int]:
    """Integer split that sums exactly to `total` (largest-remainder)."""
    if not weights:
        return []
    s = sum(weights)
    if s <= 0:
        weights, s = [1.0] * len(weights), float(len(weights))
    raw = [total * w / s for w in weights]
    base = [int(r) for r in raw]
    rem = total - sum(base)
    order = sorted(range(len(raw)), key=lambda i: -(raw[i] - base[i]))
    for i in order[:rem]:
        base[i] += 1
    return base


def validate_allocation(allocation: dict | None) -> dict:
    out = dict(DEFAULT_ALLOCATION)
    for cat, method in (allocation or {}).items():
        if cat not in ALLOWED or method not in ALLOWED[cat]:
            raise ValueError(f"allocation for {cat} must be one of {ALLOWED.get(cat, ())}")
        out[cat] = method
    return out


def compute(records: list[dict], currency: str, allocation: dict | None = None) -> dict:
    alloc = validate_allocation(allocation)
    costs = {(r["product"] or "").strip().lower(): r["unit_cost_minor"] for r in records
             if r["type"] == "product_costs" and r.get("currency") == currency and r.get("unit_cost_minor") is not None}
    returns = [r for r in records if r["type"] == "returns" and r.get("currency") == currency]
    has_returns = bool([r for r in records if r["type"] == "returns"])
    orders: dict[str, dict] = {}
    for s in records:
        if s["type"] != "sales" or s.get("currency") != currency or s["status"] == "cancelled":
            continue
        o = orders.setdefault(s["order_id"], {
            "order_id": s["order_id"], "date": s["date"], "period": s["date"][:7], "channel": s.get("channel"),
            "lines": [], "gross": 0, "discount": 0, "shipping_income": 0, "refunds": 0, "refund_source": None,
            "cogs": 0, "cogs_missing": [], "costs": {}, "sources": []})
        o["date"] = min(o["date"], s["date"])
        o["period"] = o["date"][:7]
        o["channel"] = o["channel"] or s.get("channel")
        net = s["gross_minor"] - s["discount_minor"]
        uc = costs.get((s.get("product") or "").strip().lower())
        line = {"product": (s.get("product") or "(unnamed)").strip(), "quantity": s["quantity"], "net": net,
                "gross": s["gross_minor"], "discount": s["discount_minor"],
                "cogs": round(uc * s["quantity"]) if uc is not None else None}
        o["lines"].append(line)
        o["gross"] += s["gross_minor"]
        o["discount"] += s["discount_minor"]
        o["shipping_income"] = max(o["shipping_income"], s.get("shipping_charged_minor") or 0)
        if uc is None:
            o["cogs_missing"].append(line["product"])
        else:
            o["cogs"] += line["cogs"]
        if s["status"] == "returned" and not has_returns:
            o["refunds"] += net
            o["refund_source"] = "order_status"
            line["refund"] = line.get("refund", 0) + net
        o["sources"].append({"file_id": s.get("file_id"), "row": s.get("row"), "sheet": s.get("sheet")})

    unmatched_refunds = []
    for r in returns:
        o = orders.get(r["order_id"])
        if o is None:
            unmatched_refunds.append({"order_id": r["order_id"], "date": r["date"], "amount": r["refund_minor"],
                                      "file_id": r.get("file_id"), "row": r.get("row")})
            continue
        o["refunds"] += r["refund_minor"]
        o["refund_source"] = "returns_file"
        target = [l for l in o["lines"] if r.get("product") and l["product"].lower() == r["product"].strip().lower()]
        if target:
            target[0]["refund"] = target[0].get("refund", 0) + r["refund_minor"]
        else:
            o.setdefault("unassigned_refund", 0)
            o["unassigned_refund"] += r["refund_minor"]

    # actual order-linked costs
    unmatched_costs, pools = [], defaultdict(int)
    pool_rows: dict[tuple, list] = defaultdict(list)
    for e in records:
        if e["type"] != "expenses" or e.get("currency") != currency or e["category"] not in VARIABLE:
            continue
        if e.get("order_id"):
            o = orders.get(e["order_id"])
            if o is None:
                unmatched_costs.append({"order_id": e["order_id"], "category": e["category"], "date": e["date"],
                                        "amount": e["amount_minor"], "file_id": e.get("file_id"), "row": e.get("row")})
                continue
            c = o["costs"].setdefault(e["category"], {"amount": 0, "basis": "actual"})
            c["amount"] += e["amount_minor"]
        else:
            pools[(e["date"][:7], e["category"])] += e["amount_minor"]
            pool_rows[(e["date"][:7], e["category"])].append({"file_id": e.get("file_id"), "row": e.get("row")})

    allocations, unallocated = [], []
    for (period, cat), total in sorted(pools.items()):
        method = alloc[cat]
        eligible = [o for o in orders.values() if o["period"] == period and cat not in o["costs"]]
        if method == "none" or not eligible:
            unallocated.append({"period": period, "category": cat, "amount": total,
                                "reason": "allocation switched off" if method == "none" else
                                "no orders without an actual cost in that month"})
            continue
        weights = [1.0] * len(eligible) if method == "per_order" else [max(o["gross"] - o["discount"], 0) for o in eligible]
        parts = _split(total, weights)
        for o, part in zip(eligible, parts):
            o["costs"][cat] = {"amount": part, "basis": f"allocated_{method}"}
        allocations.append({"period": period, "category": cat, "method": method, "amount": total,
                            "orders": len(eligible), "per_order_avg": round(total / len(eligible), 2),
                            "source_rows": pool_rows[(period, cat)][:10]})

    rows = []
    for o in orders.values():
        o["net_sales"] = o["gross"] - o["discount"]
        o["variable_total"] = sum(c["amount"] for c in o["costs"].values())
        known = o["net_sales"] + o["shipping_income"] - o["refunds"] - o["cogs"] - o["variable_total"]
        o["contribution_known_costs"] = known
        o["complete"] = not o["cogs_missing"]
        o["contribution"] = known if o["complete"] else None
        o["has_allocated"] = any(c["basis"].startswith("allocated") for c in o["costs"].values())
        o["missing"] = ["product_cost:" + ",".join(sorted(set(o["cogs_missing"])))] if o["cogs_missing"] else []
        rows.append(o)
    rows.sort(key=lambda o: (o["date"], o["order_id"]))

    products = _products(rows)
    channels = _group(rows, lambda o: o["channel"] or "(none)")
    periods = _group(rows, lambda o: o["period"])
    recon = {"orders_contribution_known_costs": sum(o["contribution_known_costs"] for o in rows),
             "unallocated_costs": sum(u["amount"] for u in unallocated),
             "costs_linked_to_unknown_orders": sum(u["amount"] for u in unmatched_costs),
             "refunds_linked_to_unknown_orders": sum(u["amount"] for u in unmatched_refunds)}
    recon["implied_monthly_contribution_total"] = (recon["orders_contribution_known_costs"] - recon["unallocated_costs"]
                                                   - recon["costs_linked_to_unknown_orders"]
                                                   - recon["refunds_linked_to_unknown_orders"])
    loss = sorted([o for o in rows if o["contribution"] is not None and o["contribution"] < 0],
                  key=lambda o: o["contribution"])
    return {"currency": currency, "allocation": alloc, "orders": rows, "products": products, "channels": channels,
            "periods": periods, "allocations": allocations, "unallocated": unallocated,
            "unmatched_costs": unmatched_costs, "unmatched_refunds": unmatched_refunds, "reconciliation": recon,
            "loss_orders": [_brief(o) for o in loss[:25]], "loss_order_count": len(loss),
            "incomplete_orders": sum(1 for o in rows if not o["complete"]),
            "orders_with_allocated_costs": sum(1 for o in rows if o["has_allocated"]),
            "orders_with_actual_costs": sum(1 for o in rows if any(c["basis"] == "actual" for c in o["costs"].values())),
            "method_text": METHOD_TEXT}


def _brief(o: dict) -> dict:
    biggest = max(o["costs"].items(), key=lambda kv: kv[1]["amount"], default=(None, {"amount": 0}))
    return {"order_id": o["order_id"], "date": o["date"], "channel": o["channel"], "net_sales": o["net_sales"],
            "shipping_income": o["shipping_income"], "refunds": o["refunds"], "cogs": o["cogs"],
            "costs": {k: v for k, v in o["costs"].items()}, "contribution": o["contribution"],
            "biggest_cost": biggest[0] if biggest[1]["amount"] > (o["cogs"] or 0) else "product_cost",
            "products": sorted({l["product"] for l in o["lines"]}), "has_allocated": o["has_allocated"],
            "sources": o["sources"][:5]}


def _products(rows: list[dict]) -> list[dict]:
    """Line-level view: order-level shared costs/income/refunds split across lines by line net value."""
    P: dict[str, dict] = defaultdict(lambda: {"units": 0.0, "net_sales": 0, "refunds": 0, "cogs": 0, "costs": 0,
                                              "shipping_income": 0, "orders": set(), "cogs_missing": False,
                                              "allocated_share": 0})
    for o in rows:
        weights = [max(l["net"], 0) for l in o["lines"]]
        shared_cost = _split(o["variable_total"], weights)
        ship = _split(o["shipping_income"], weights)
        unassigned = _split(o.get("unassigned_refund", 0), weights)
        allocated_amt = sum(c["amount"] for c in o["costs"].values() if c["basis"].startswith("allocated"))
        alloc_parts = _split(allocated_amt, weights)
        for i, l in enumerate(o["lines"]):
            p = P[l["product"]]
            p["units"] += l["quantity"]
            p["net_sales"] += l["net"]
            p["refunds"] += l.get("refund", 0) + unassigned[i]
            p["costs"] += shared_cost[i]
            p["shipping_income"] += ship[i]
            p["allocated_share"] += alloc_parts[i]
            p["orders"].add(o["order_id"])
            if l["cogs"] is None:
                p["cogs_missing"] = True
            else:
                p["cogs"] += l["cogs"]
    out = []
    for name, p in P.items():
        contrib = None if p["cogs_missing"] else p["net_sales"] + p["shipping_income"] - p["refunds"] - p["cogs"] - p["costs"]
        out.append({"product": name, "units": round(p["units"], 2), "orders": len(p["orders"]),
                    "net_sales": p["net_sales"], "refunds": p["refunds"], "cogs": None if p["cogs_missing"] else p["cogs"],
                    "order_costs": p["costs"], "shipping_income": p["shipping_income"],
                    "allocated_part_of_costs": p["allocated_share"], "contribution": contrib,
                    "contribution_per_unit": round(contrib / p["units"], 2) if contrib is not None and p["units"] else None,
                    "contribution_margin": round(contrib / p["net_sales"], 4) if contrib is not None and p["net_sales"] else None})
    out.sort(key=lambda r: -r["net_sales"])
    return out


def _group(rows: list[dict], key) -> list[dict]:
    G: dict[str, dict] = defaultdict(lambda: {"orders": 0, "net_sales": 0, "contribution": 0, "incomplete": 0,
                                              "loss_orders": 0})
    for o in rows:
        g = G[key(o)]
        g["orders"] += 1
        g["net_sales"] += o["net_sales"]
        if o["contribution"] is None:
            g["incomplete"] += 1
        else:
            g["contribution"] += o["contribution"]
            g["loss_orders"] += o["contribution"] < 0
    return [{"key": k, **v, "contribution_per_order": round(v["contribution"] / (v["orders"] - v["incomplete"]), 2)
             if v["orders"] - v["incomplete"] else None} for k, v in sorted(G.items())]


def insights(o: dict, lang: str) -> list[dict]:
    """Plain-language observations computed from the order-level result (no new numbers are made up here)."""
    from ..ledger.csv_import import money_fmt
    ar, cur, out = lang == "ar", o["currency"], []
    prods = [p for p in o["products"] if p["contribution"] is not None and p["units"] > 0]
    if len(prods) >= 2:
        top_sales = max(prods, key=lambda p: p["net_sales"])
        best = max(prods, key=lambda p: p["contribution_per_unit"] if p["contribution_per_unit"] is not None else -1e18)
        worst_margin = min(prods, key=lambda p: p["contribution_margin"] if p["contribution_margin"] is not None else 1e9)
        if top_sales["product"] != best["product"]:
            out.append({"kind": "top_seller_not_top_earner", "product": top_sales["product"], "other": best["product"],
                        "text": (f"«{top_sales['product']}» أكتر منتج بيجيب مبيعات ({money_fmt(top_sales['net_sales'], cur, lang)})، "
                                 f"بس كل قطعة منه بتسيبلك {money_fmt(round(top_sales['contribution_per_unit']), cur, lang)} بس، "
                                 f"وقطعة «{best['product']}» بتسيبلك {money_fmt(round(best['contribution_per_unit']), cur, lang)}. "
                                 "المبيعات الكبيرة مش دايماً معناها ربح أكبر لو تكلفة المنتج والتغليف والشحن عالية."
                                 if ar else
                                 f"“{top_sales['product']}” brings the most sales ({money_fmt(top_sales['net_sales'], cur, lang)}), "
                                 f"but each unit leaves only {money_fmt(round(top_sales['contribution_per_unit']), cur, lang)}, while "
                                 f"“{best['product']}” leaves {money_fmt(round(best['contribution_per_unit']), cur, lang)} per unit. "
                                 "High sales don't mean high profit when product, packaging and delivery costs are high.")})
        if worst_margin["contribution_margin"] is not None and worst_margin["contribution_margin"] < 0:
            out.append({"kind": "loss_product", "product": worst_margin["product"],
                        "text": (f"«{worst_margin['product']}» بيخسّرك: بعد كل التكاليف كل ١٠٠ جنيه مبيعات بتسيب "
                                 f"{worst_margin['contribution_margin'] * 100:.0f} جنيه." if ar else
                                 f"“{worst_margin['product']}” loses money: after all order costs, every 100 of sales leaves "
                                 f"{worst_margin['contribution_margin'] * 100:.0f}.")})
    if o["loss_order_count"]:
        n, total = o["loss_order_count"], len([x for x in o["orders"] if x["contribution"] is not None])
        out.append({"kind": "loss_orders", "count": n,
                    "text": (f"{n} من {total} طلب خسروا فلوس بعد كل تكاليف الطلب." if ar else
                             f"{n} of {total} orders lost money after all order costs.")})
    if o["orders_with_allocated_costs"]:
        out.append({"kind": "allocation_note",
                    "text": ("جزء من تكاليف الطلبات متوزّع من فواتير شهرية (موضّح جنب كل طلب)، مش متسجل لكل طلب لوحده. "
                             "ارفع كشف شركة الشحن أو بوابة الدفع برقم الطلب عشان الأرقام تبقى فعلية."
                             if ar else
                             "Some order costs are allocated from monthly invoices (marked on each order), not recorded "
                             "per order. Upload courier or payment-gateway statements with order IDs to make them actual.")})
    return out
