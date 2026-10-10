"""Investigation state, evidence-backed diagnosis, guided questions, explanations, recommendations and charts.

Everything is derived from metrics.compute() over the investigation's records. The language here is templated
from computed numbers (Egyptian Arabic and English); no figure is ever typed in by hand. Hypotheses whose data is
missing are reported as untested, never as causes.
"""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta

from ..ledger.csv_import import money_fmt
from . import metrics, store
from .ingest import VARIABLE

MIN_ORDERS = 30          # per period, for a "supported" finding
MATERIAL_SHARE = 0.01    # a driver matters when it moves contribution/order by ≥1% of net sales/order

DRIVER_LABEL = {
    "price_and_mix": {"en": "selling price / product mix", "ar": "سعر البيع أو نوعية المنتجات المباعة"},
    "shipping_income": {"en": "delivery fees customers pay", "ar": "رسوم التوصيل اللي العملاء بيدفعوها"},
    "discounts": {"en": "discounts", "ar": "الخصومات"},
    "refunds": {"en": "refunds and returns", "ar": "المرتجعات"},
    "product_costs": {"en": "product costs", "ar": "تكلفة المنتجات"},
    "packaging": {"en": "packaging", "ar": "التغليف"},
    "shipping": {"en": "shipping", "ar": "الشحن"},
    "payment_fees": {"en": "payment fees", "ar": "رسوم الدفع"},
    "marketplace_fees": {"en": "marketplace commissions", "ar": "عمولات المنصات"},
}
DRIVER_DATA = {  # which data must exist in BOTH periods for a driver to be measured
    "price_and_mix": "sales", "discounts": "sales", "shipping_income": "sales", "refunds": "returns", "product_costs": "product_costs",
    "packaging": "packaging", "shipping": "shipping", "payment_fees": "payment_fees",
    "marketplace_fees": "marketplace_fees",
}


# ------------------------------------------------------------------------------------------ question bank

Q = {
    "p_sells": {"kind": "profile", "options": ["products", "services", "both"],
                "en": "What do you sell: products, services, or both?",
                "ar": "إنت بتبيع منتجات، ولا خدمات، ولا الاتنين؟",
                "why_en": "So I know which costs to look at.", "why_ar": "عشان أعرف أركّز على أنهي تكاليف."},
    "p_worry": {"kind": "profile", "options": ["profit_low_despite_sales", "sales_falling", "cash_tight", "not_sure"],
                "en": "What worries you most right now?", "ar": "إيه أكتر حاجة قلقاك في الشغل دلوقتي؟",
                "why_en": "So we investigate the right problem first.",
                "why_ar": "عشان نبدأ بالمشكلة اللي تهمك فعلاً."},
    "p_channels": {"kind": "profile", "options": ["shop", "website", "social", "marketplaces"], "multi": True,
                   "en": "Where do you sell?", "ar": "بتبيع فين؟",
                   "why_en": "Online sales usually add shipping and fees.",
                   "why_ar": "البيع أونلاين غالباً بيضيف شحن ورسوم."},
    "d_sales": {"kind": "document", "upload": "sales",
                "en": "Upload your sales or orders report (CSV or Excel).",
                "ar": "ارفع تقرير المبيعات أو الطلبات (CSV أو Excel).",
                "why_en": "It shows what came in from each order. With it I can calculate sales, discounts and "
                          "average order value per month.",
                "why_ar": "ده بيوضح الفلوس اللي دخلت من كل طلب. بيه أقدر أحسب المبيعات والخصومات ومتوسط الطلب كل شهر."},
    "d_costs": {"kind": "document", "upload": "product_costs",
                "en": "Upload what each product costs you (a list of products with their unit cost).",
                "ar": "ارفع تكلفة كل منتج عليك (قائمة بالمنتجات وتكلفة القطعة).",
                "why_en": "Without product costs I can't tell how much each sale really leaves you.",
                "why_ar": "من غير تكلفة المنتجات مقدرش أعرف كل بيعة بتسيبلك كام فعلاً."},
    "d_packaging": {"kind": "document", "upload": "expenses", "category": "packaging",
                    "en": "Upload your packaging supplier invoices.", "ar": "ارفع فواتير مورد التغليف.",
                    "why_en": "I'll compare what you earn per order with what you spend on packaging per order.",
                    "why_ar": "هقارن اللي بتكسبه من كل طلب باللي بتصرفه على التغليف لكل طلب."},
    "d_shipping": {"kind": "document", "upload": "expenses", "category": "shipping",
                   "en": "Upload your shipping / courier invoices or statement.",
                   "ar": "ارفع فواتير أو كشف حساب شركة الشحن.",
                   "why_en": "Shipping is often the cost that grows fastest with orders. I'll calculate your real "
                             "delivery cost per order.",
                   "why_ar": "الشحن غالباً أسرع تكلفة بتزيد مع الطلبات. هحسب تكلفة التوصيل الحقيقية لكل طلب."},
    "d_returns": {"kind": "document", "upload": "returns",
                  "en": "Upload your returns / refunds report (with reasons if you have them).",
                  "ar": "ارفع تقرير المرتجعات (ولو فيه أسباب الإرجاع يبقى أحسن).",
                  "why_en": "Returns take money back after a sale. Reasons tell us what to fix.",
                  "why_ar": "المرتجعات بتاخد فلوس تاني بعد البيع، وأسبابها بتقولنا نصلّح إيه."},
    "d_fees": {"kind": "document", "upload": "expenses", "category": "payment_fees",
               "en": "Upload payment-gateway or marketplace fee statements.",
               "ar": "ارفع كشوف رسوم بوابة الدفع أو عمولات المنصات.",
               "why_en": "Fees are taken from every order and are easy to miss.",
               "why_ar": "الرسوم بتتخصم من كل طلب وسهل ننساها."},
    "d_courier_orders": {"kind": "document", "upload": "expenses", "category": "shipping",
                         "en": "Upload your courier statement that lists each order number and its delivery fee.",
                         "ar": "ارفع كشف شركة الشحن اللي فيه رقم كل طلب ورسوم توصيله.",
                         "why_en": "Then delivery becomes an actual cost per order instead of an equal share.",
                         "why_ar": "ساعتها الشحن هيبقى تكلفة فعلية لكل طلب بدل ما يتقسم بالتساوي."},
    "d_payment_orders": {"kind": "document", "upload": "expenses", "category": "payment_fees",
                         "en": "Upload the payment-gateway statement with order numbers and fees.",
                         "ar": "ارفع كشف بوابة الدفع اللي فيه رقم كل طلب والرسوم.",
                         "why_en": "Then payment fees become actual per order instead of an estimate.",
                         "why_ar": "ساعتها رسوم الدفع هتبقى فعلية لكل طلب بدل التقدير."},
    "d_fixed": {"kind": "document", "upload": "expenses", "category": "rent",
                "en": "Optional: upload rent, salaries and subscriptions to see operating profit.",
                "ar": "اختياري: ارفع الإيجار والمرتبات والاشتراكات عشان نشوف الربح التشغيلي.",
                "why_en": "Then I can tell how many orders you need each month to break even.",
                "why_ar": "ساعتها أقدر أقولك محتاج كام طلب في الشهر عشان تغطي مصاريفك."},
}
EVIDENCE_Q = {
    "packaging": {"options": ["supplier_price_up", "changed_packaging", "more_items_per_order", "not_sure"],
                  "en": "Packaging now costs more per order. Did your supplier raise prices, or did the packaging "
                        "itself change?",
                  "ar": "التغليف بقى بيكلّف أكتر في كل طلب. هل المورد غلّى الأسعار، ولا شكل التغليف نفسه اتغير؟"},
    "shipping": {"options": ["courier_rates_up", "farther_deliveries", "more_failed_deliveries", "not_sure"],
                 "en": "Shipping per order went up. Did the courier change rates, are you delivering farther, or are "
                       "more deliveries failing?",
                 "ar": "الشحن لكل طلب زاد. هل شركة الشحن غيّرت أسعارها، ولا بتوصّل لأماكن أبعد، ولا التوصيلات "
                       "الفاشلة زادت؟"},
    "discounts": {"options": ["more_promotions", "bigger_discounts", "not_sure"],
                  "en": "Discounts per order increased. Did you run more promotions, or bigger ones?",
                  "ar": "الخصم لكل طلب زاد. عملت عروض أكتر، ولا العروض بقت أكبر؟"},
    "refunds": {"options": ["size_fit", "quality_defect", "late_delivery", "changed_mind", "not_sure"],
                "en": "Refunds per order increased. What do customers usually say when they return items?",
                "ar": "المرتجعات لكل طلب زادت. العملاء بيقولوا إيه عادةً لما يرجّعوا؟"},
    "product_costs": {"options": ["supplier_price_up", "selling_costlier_items", "not_sure"],
                      "en": "Product costs per order went up. Did suppliers raise prices, or are you selling more of "
                            "your costlier items?",
                      "ar": "تكلفة المنتجات لكل طلب زادت. الموردين غلّوا الأسعار، ولا بتبيع أكتر من المنتجات الغالية؟"},
    "price_and_mix": {"options": ["lowered_prices", "selling_cheaper_items", "not_sure"],
                      "en": "Each order now brings in less before costs. Did you lower prices, or are customers buying "
                            "cheaper items?",
                      "ar": "كل طلب بقى بيجيب فلوس أقل قبل التكاليف. نزّلت الأسعار، ولا العملاء بيشتروا حاجات أرخص؟"},
}


# ------------------------------------------------------------------------------------------ helpers

def _fmt(minor: float | int | None, cur: str, lang: str) -> str:
    return "—" if minor is None else money_fmt(int(round(minor)), cur, lang)


def _pct(x: float | None) -> str:
    return "—" if x is None else f"{x * 100:.1f}%"


def _answers(conn: sqlite3.Connection, iid: str) -> dict:
    return {r[0]: {"status": r[1], "answer": r[2]} for r in conn.execute(
        "SELECT qid, status, answer FROM inv_questions WHERE investigation_id=?", (iid,))}


def answer(conn: sqlite3.Connection, iid: str, qid: str, *, tenant: str, status: str, value: str | None,
           actor: str) -> None:
    import time
    from .. import db
    from ..ledger.store import audit
    inv = store.get(conn, iid, tenant)
    if status not in ("answered", "skipped", "dont_know"):
        raise ValueError("status must be answered, skipped or dont_know")
    known = qid in Q or (qid.startswith("e_") and qid[2:] in EVIDENCE_Q) or qid.startswith("gap_")
    if not known:
        raise ValueError("unknown question")
    value = (value or "")[:500] or None
    with db.tx(conn):
        conn.execute("INSERT INTO inv_questions(investigation_id, qid, status, answer, answered_at) VALUES(?,?,?,?,?) "
                     "ON CONFLICT(investigation_id, qid) DO UPDATE SET status=excluded.status, answer=excluded.answer, "
                     "answered_at=excluded.answered_at", (iid, qid, status, value, time.time()))
        if qid.startswith("p_") and status == "answered":
            prof = inv["profile"] | {qid[2:]: value}
            store.touch(conn, iid, profile=prof)
        audit(conn, actor, "investigation_answer", tenant=tenant, investigation=iid, qid=qid, status=status)


def _main_currency(m: dict) -> str | None:
    tot: dict[str, int] = {}
    for p in m["periods"]:
        tot[p["currency"]] = tot.get(p["currency"], 0) + p["net_sales"]
    return max(tot, key=tot.get) if tot else None


def _data_by_period(records: list[dict], cur: str) -> dict[str, set]:
    out: dict[str, set] = {}
    for r in records:
        if r.get("currency") != cur or not r.get("date"):
            continue
        tag = r["category"] if r["type"] == "expenses" else r["type"]
        out.setdefault(r["date"][:7], set()).add(tag)
    return out


def _partial_period(records: list[dict], period: str) -> bool:
    ds = [r["date"] for r in records if r["type"] == "sales" and r.get("date", "").startswith(period)]
    if not ds:
        return False
    y, mth = int(period[:4]), int(period[5:7])
    last = (date(y + (mth == 12), mth % 12 + 1, 1) - timedelta(days=1))
    return date.fromisoformat(max(ds)) < last - timedelta(days=3)


# ------------------------------------------------------------------------------------------ diagnosis

def diagnose(records: list[dict], m: dict, cur: str, base_p: str | None = None, cur_p: str | None = None) -> dict:
    periods = [p for p in m["periods"] if p["currency"] == cur and p["orders"] > 0]
    if len(periods) < 2:
        return {"comparable": False, "reason": "need_two_periods", "periods": [p["period"] for p in periods]}
    by = {p["period"]: p for p in periods}
    base = by.get(base_p) if base_p else periods[-2]
    curr = by.get(cur_p) if cur_p else periods[-1]
    if not base or not curr or base["period"] >= curr["period"]:
        raise ValueError("choose two periods with orders, the first earlier than the second")
    bridge = metrics.contribution_bridge(base, curr)
    data = _data_by_period(records, cur)
    has = lambda tag, per: tag in data.get(per, set())  # noqa: E731
    present_anywhere = {t for s in data.values() for t in s}
    if m["has_product_costs"]:
        present_anywhere.add("product_costs")
    findings, untested, gaps = [], [], []
    threshold = MATERIAL_SHARE * (base["per_order"]["net_sales"] or 0)
    for key, delta in sorted(bridge["components"].items(), key=lambda kv: kv[1]):
        need = DRIVER_DATA[key]
        if need == "product_costs":
            measured = m["has_product_costs"]
            coverage_ok = (base["cogs_coverage"] or 0) >= 0.9 and (curr["cogs_coverage"] or 0) >= 0.9
        elif need == "sales":
            measured, coverage_ok = True, True
        elif need == "returns":
            measured = m["has_returns_file"] or base["refund_source"] == "order_status" or \
                curr["refund_source"] == "order_status"
            coverage_ok = m["has_returns_file"]
        else:
            in_b, in_c = has(need, base["period"]), has(need, curr["period"])
            measured = in_b and in_c
            coverage_ok = measured
            if (in_b or in_c) and not measured:
                gaps.append({"category": need, "present_in": base["period"] if in_b else curr["period"],
                             "missing_in": curr["period"] if in_b else base["period"]})
                continue
        if not measured:
            if need in VARIABLE or need in ("product_costs", "returns"):
                untested.append(key)
            continue
        if delta < 0 and abs(delta) >= threshold:
            low_orders = base["orders"] < MIN_ORDERS or curr["orders"] < MIN_ORDERS
            conf = "supported" if coverage_ok and not low_orders else "preliminary"
            b_val, c_val = _component_values(key, base, curr)
            findings.append({
                "driver": key, "change_per_order": delta, "impact_total": round(delta * curr["orders"]),
                "base_value_per_order": b_val, "current_value_per_order": c_val, "confidence": conf,
                "why_preliminary": ([] if conf == "supported" else
                                    (["fewer than %d orders in a period" % MIN_ORDERS] if low_orders else []) +
                                    ([] if coverage_ok else ["incomplete data for this cost"])),
                "evidence": _evidence(records, key, cur, base["period"], curr["period"]),
            })
    sales_growth = metrics._ratio(curr["net_sales"] - base["net_sales"], base["net_sales"])
    contrib_growth = metrics._ratio(curr["contribution"] - base["contribution"], abs(base["contribution"]) or None)
    return {"comparable": True, "currency": cur, "base": base, "current": curr, "bridge": bridge,
            "findings": findings, "untested": untested, "gaps": gaps, "sales_growth": sales_growth,
            "contribution_growth": contrib_growth, "partial_current_period": _partial_period(records, curr["period"]),
            "headline": _headline(base, curr, findings)}


def _component_values(key: str, b: dict, c: dict) -> tuple[float, float]:
    field = {"price_and_mix": "gross_sales", "product_costs": "cogs"}.get(key, key)
    if field not in b["per_order"]:
        return 0.0, 0.0
    return round(b["per_order"][field], 2), round(c["per_order"][field], 2)


def _evidence(records: list[dict], key: str, cur: str, bp: str, cp: str) -> dict:
    """Which records support a driver: counts, files and rows (traceability back to the uploads)."""
    rtype, cat = {"product_costs": ("product_costs", None), "refunds": ("returns", None),
                  "price_and_mix": ("sales", None), "discounts": ("sales", None),
                  "shipping_income": ("sales", None)}.get(key, ("expenses", key))
    rows = [r for r in records if r["type"] == rtype and r.get("currency", cur) == cur and
            (cat is None or r.get("category") == cat) and
            (rtype == "product_costs" or r.get("date", "")[:7] in (bp, cp))]
    unit_prices = {}
    if rtype == "expenses":  # unit price per period when invoices carry quantities (e.g. boxes): price vs volume
        for per in (bp, cp):
            q = [r for r in rows if r["date"][:7] == per and r.get("quantity")]
            if q:
                unit_prices[per] = round(sum(r["amount_minor"] for r in q) / sum(r["quantity"] for r in q), 2)
    return {"record_type": rtype, "category": cat, "records": len(rows),
            "files": sorted({r.get("file_id") for r in rows if r.get("file_id")}),
            "manual_entries": sum(1 for r in rows if "manual_entry" in r.get("flags", [])),
            "inferred_categories": sum(1 for r in rows if "category_inferred" in r.get("flags", [])),
            "sample_rows": [{"file_id": r.get("file_id"), "sheet": r.get("sheet"), "row": r.get("row")} for r in rows[:8]],
            "unit_price_by_period": unit_prices}


def _headline(b: dict, c: dict, findings: list) -> str:
    if c["net_sales"] > b["net_sales"] and c["contribution"] < b["contribution"]:
        return "sales_up_profit_down"
    if c["net_sales"] < b["net_sales"]:
        return "sales_down"
    if c["per_order"]["contribution"] < b["per_order"]["contribution"]:
        return "margin_down"
    return "stable_or_improving"


# ------------------------------------------------------------------------------------------ explanations

def explain(f: dict, d: dict, lang: str) -> dict:
    """Five-part plain-language explanation built only from computed numbers."""
    cur, b, c = d["currency"], d["base"], d["current"]
    key, ar = f["driver"], lang == "ar"
    lbl = DRIVER_LABEL[key]["ar" if ar else "en"]
    bv, cv = _fmt(f["base_value_per_order"], cur, lang), _fmt(f["current_value_per_order"], cur, lang)
    impact = _fmt(abs(f["impact_total"]), cur, lang)
    per = _fmt(abs(f["change_per_order"]), cur, lang)
    up_is_bad = key not in ("price_and_mix", "shipping_income")
    ev = f["evidence"]
    if ar:
        what = (f"كل طلب بقى بيسيبلك {per} أقل بسبب {lbl}." if up_is_bad else
                f"كل طلب بقى بيجيب {per} أقل قبل أي تكاليف.")
        why = ("تخيّل كل طلب كإنه جردل فلوس: العميل بيحط فيه، والمنتج والتغليف والشحن والرسوم بياخدوا منه. لو "
               "التكاليف دي زادت أسرع من اللازم، ممكن تبيع أكتر وتكسب أقل. "
               f"على {c['orders']} طلب في {c['period']}، ده معناه حوالي {impact} أقل في الشهر.")
        evidence = (f"{lbl} لكل طلب كان {bv} في {b['period']} وبقى {cv} في {c['period']} "
                    f"(من {ev['records']} سجل في الملفات اللي رفعتها).")
        if ev["unit_price_by_period"]:
            evidence += " سعر الوحدة في الفواتير: " + "، ".join(
                f"{p}: {_fmt(v, cur, lang)}" for p, v in ev["unit_price_by_period"].items()) + "."
    else:
        what = (f"Each order now leaves you {per} less because of {lbl}." if up_is_bad else
                f"Each order now brings in {per} less before any costs.")
        why = ("Think of every order as a small bucket of money: the customer fills it, and product, packaging, "
               "delivery and fees take some back out. If those costs grow too fast, you can sell more and still keep "
               f"less. Across {c['orders']} orders in {c['period']}, that is about {impact} less this month.")
        evidence = (f"{lbl.capitalize()} per order was {bv} in {b['period']} and {cv} in {c['period']} "
                    f"(from {ev['records']} records in your uploaded files).")
        if ev["unit_price_by_period"]:
            evidence += " Unit price on the invoices: " + ", ".join(
                f"{p}: {_fmt(v, cur, lang)}" for p, v in ev["unit_price_by_period"].items()) + "."
    caveats = []
    if f["confidence"] != "supported":
        caveats.append("ده استنتاج مبدئي: " + "، ".join(f["why_preliminary"]) if ar else
                       "Preliminary: " + ", ".join(f["why_preliminary"]))
    if ev["manual_entries"]:
        caveats.append("جزء من الأرقام دي إنت كتبته بإيدك." if ar else "Some of these figures were typed in manually.")
    if ev["inferred_categories"]:
        caveats.append("بعض الفواتير اتصنّفت من الوصف، راجع التصنيف." if ar else
                       "Some invoices were categorised from their description; please check the categories.")
    if d.get("partial_current_period"):
        caveats.append(f"شهر {c['period']} ممكن يكون مش كامل." if ar else f"{c['period']} may be a partial month.")
    next_step = {
        "packaging": ("نتأكد الأول: المورد غلّى السعر ولا التغليف نفسه اتغيّر، قبل ما نقرر أي حاجة." if ar else
                      "Let's check whether the supplier raised prices or the packaging changed before deciding."),
        "shipping": ("نشوف فواتير الشحن: الزيادة من السعر ولا من التوصيلات الفاشلة والأماكن البعيدة." if ar else
                     "Let's check the shipping invoices: is it the rate, failed deliveries, or longer routes?"),
        "discounts": ("نراجع العروض اللي اتعملت ونشوف أنهي واحد جاب طلبات فعلاً." if ar else
                      "Let's review which promotions actually brought orders."),
        "refunds": ("نجمع أسباب المرتجعات عشان نعرف نصلّح إيه." if ar else
                    "Let's collect return reasons so we know what to fix."),
        "product_costs": ("نقارن تكلفة القطعة من الموردين بين الشهرين." if ar else
                          "Let's compare supplier unit costs between the two months."),
        "price_and_mix": ("نشوف أنهي منتجات بتتباع أكتر دلوقتي وهامشها قد إيه." if ar else
                          "Let's see which products sell more now and what margin they carry."),
    }.get(key, "نراجع الفواتير دي بالتفصيل." if ar else "Let's review these invoices in detail.")
    return {"what": what, "why": why, "evidence": evidence, "caveats": caveats, "next": next_step}


# ------------------------------------------------------------------------------------------ recommendations

OPTIONS = {
    "packaging": ["verify_supplier_price", "request_quotes", "pilot_alternative", "keep_and_reprice"],
    "shipping": ["compare_couriers", "reduce_failed_deliveries", "free_shipping_threshold", "pass_through_fee"],
    "discounts": ["review_promotions", "minimum_order_value", "targeted_offers"],
    "refunds": ["collect_reasons", "size_guide_quality_check", "pre_dispatch_confirmation"],
    "product_costs": ["compare_supplier_quotes", "reprice_low_margin", "review_bill_of_materials"],
    "price_and_mix": ["promote_high_margin", "review_prices"],
    "payment_fees": ["compare_gateways", "encourage_cheaper_methods"],
    "marketplace_fees": ["compare_channels", "review_fee_tier"],
}
OPTION_TEXT = {
    "verify_supplier_price": ("Check the packaging invoices: same item at a higher price, or a different item?",
                              "راجع فواتير التغليف: نفس الصنف بسعر أعلى، ولا صنف مختلف؟",
                              "No quality change; needs only the invoices you already have.",
                              "مفيش أي تغيير في الجودة، ومحتاج بس الفواتير اللي عندك."),
    "request_quotes": ("Ask 2–3 suppliers for quotes on the SAME specification (size, material, print).",
                       "اطلب عروض أسعار من ٢-٣ موردين لنفس المواصفات بالظبط (المقاس، الخامة، الطباعة).",
                       "Compare total cost: unit price, delivery, minimum order, payment terms. Cheapest is not "
                       "automatically best: protection and brand look matter.",
                       "قارن التكلفة الكاملة: سعر الوحدة والتوصيل والحد الأدنى للطلب وطريقة الدفع. الأرخص مش دايماً الأحسن: "
                       "حماية المنتج وشكل البراند مهمين."),
    "pilot_alternative": ("Pilot an alternative on a small share of orders for 2–4 weeks.",
                          "جرّب البديل على جزء صغير من الطلبات لمدة ٢-٤ أسابيع.",
                          "Measure packaging cost per order, damaged/returned items and customer comments before "
                          "switching fully.",
                          "قيس تكلفة التغليف لكل طلب، والمنتجات اللي اتضررت أو رجعت، وتعليقات العملاء قبل ما تغيّر خالص."),
    "keep_and_reprice": ("Keep the packaging (brand experience) and recover the cost in price or a gift-wrap fee.",
                         "سيب التغليف زي ما هو (تجربة البراند) وعوّض التكلفة في السعر أو رسوم تغليف هدايا.",
                         "Protects quality; watch whether order volume drops after a price change.",
                         "بيحافظ على الجودة؛ راقب لو الطلبات قلّت بعد تغيير السعر."),
    "compare_couriers": ("Get rates from 2–3 couriers for your real delivery areas and parcel sizes.",
                         "اطلب أسعار من ٢-٣ شركات شحن لنفس مناطق التوصيل وأحجام الشحنات بتاعتك.",
                         "Compare delivery success rate and speed, not only price: a failed delivery costs twice.",
                         "قارن نسبة التوصيل الناجح والسرعة، مش السعر بس: التوصيلة الفاشلة بتتحسب مرتين."),
    "reduce_failed_deliveries": ("Confirm orders by phone/WhatsApp before dispatch to cut failed deliveries.",
                                 "أكّد الطلب بالتليفون أو واتساب قبل الشحن عشان تقلّل التوصيلات الفاشلة.",
                                 "Costs staff time; measure failed-delivery rate and shipping cost per order.",
                                 "بياخد وقت من الموظفين؛ قيس نسبة التوصيل الفاشل وتكلفة الشحن لكل طلب."),
    "free_shipping_threshold": ("Offer free shipping only above a minimum order value.",
                                "خلّي الشحن المجاني بس للطلبات فوق مبلغ معيّن.",
                                "Can raise average order value; may reduce small orders.",
                                "ممكن يزوّد متوسط الطلب؛ وممكن يقلّل الطلبات الصغيرة."),
    "pass_through_fee": ("Show a fair delivery fee instead of absorbing it.", "اعرض رسوم توصيل عادلة بدل ما تتحملها.",
                         "Watch conversion: some customers may not complete the order.",
                         "راقب العملاء اللي بيكمّلوا الطلب: البعض ممكن يتراجع."),
    "review_promotions": ("Review which promotions brought new orders vs just discounted existing ones.",
                          "راجع أنهي عروض جابت طلبات جديدة وأنهي خصمت على طلبات كانت هتيجي أصلاً.",
                          "Measure net sales per order and number of orders during and after promotions.",
                          "قيس صافي المبيعات لكل طلب وعدد الطلبات وقت العرض وبعده."),
    "minimum_order_value": ("Apply discounts only above a minimum basket.", "خلّي الخصم بس فوق مبلغ معيّن للطلب.",
                            "Protects margin; may reduce promo-driven orders.", "بيحمي الهامش؛ وممكن يقلّل طلبات العروض."),
    "targeted_offers": ("Target discounts at returning or slow-moving items instead of everything.",
                        "خلّي الخصومات لعملاء معيّنين أو منتجات راكدة بدل كل حاجة.", "Needs simple customer/product data.",
                        "محتاج بيانات بسيطة عن العملاء أو المنتجات."),
    "collect_reasons": ("Record a reason for every return for the next month.",
                        "سجّل سبب كل مرتجع لمدة الشهر الجاي.", "No cost; it tells us what to fix.",
                        "من غير تكلفة؛ وبيقولنا نصلّح إيه."),
    "size_guide_quality_check": ("Add a size guide or a quality check before dispatch.",
                                 "ضيف جدول مقاسات أو فحص جودة قبل الشحن.",
                                 "Small effort; measure return rate on the same products.",
                                 "مجهود بسيط؛ قيس نسبة المرتجع على نفس المنتجات."),
    "pre_dispatch_confirmation": ("Confirm size/colour with the customer before shipping.",
                                  "أكّد المقاس واللون مع العميل قبل الشحن.", "Costs time; reduces wrong-item returns.",
                                  "بياخد وقت؛ بيقلّل مرتجعات الطلب الغلط."),
    "compare_supplier_quotes": ("Ask current and alternative suppliers for written quotes on the same items.",
                                "اطلب عروض أسعار مكتوبة من المورد الحالي وموردين تانيين لنفس الأصناف.",
                                "Check quality samples before switching; include delivery and minimum quantities.",
                                "اطلب عينات للجودة قبل التغيير، واحسب التوصيل والحد الأدنى للكمية."),
    "reprice_low_margin": ("Raise prices on products whose margin fell the most.",
                           "زوّد سعر المنتجات اللي هامشها قلّ أكتر.", "Watch units sold after the change.",
                           "راقب عدد القطع المباعة بعد التغيير."),
    "review_bill_of_materials": ("Check whether materials or labour per item changed.",
                                 "راجع هل الخامات أو المصنعية للقطعة اتغيّرت.", "Needs production records.",
                                 "محتاج سجلات الإنتاج."),
    "promote_high_margin": ("Feature products that leave more per sale.", "اعرض المنتجات اللي بتكسّب أكتر في الأول.",
                            "Low risk; measure contribution per order.", "مخاطرة قليلة؛ قيس المساهمة لكل طلب."),
    "review_prices": ("Check whether recent price cuts brought enough extra orders.",
                      "شوف هل تخفيض الأسعار الأخير جاب طلبات زيادة تكفي.", "Compare orders and margin before/after.",
                      "قارن الطلبات والهامش قبل وبعد."),
    "compare_gateways": ("Compare payment providers' fees for your typical order size.",
                         "قارن رسوم شركات الدفع لحجم الطلب المعتاد عندك.", "Consider payout speed and reliability.",
                         "خد في اعتبارك سرعة تحويل الفلوس والاعتمادية."),
    "encourage_cheaper_methods": ("Encourage cheaper payment methods where customers accept them.",
                                  "شجّع طرق دفع أرخص لو العملاء متقبّلينها.", "Don't add friction at checkout.",
                                  "من غير ما تصعّب الدفع على العميل."),
    "compare_channels": ("Compare what each sales channel leaves after its commission.",
                         "قارن كل قناة بيع بتسيبلك كام بعد العمولة.", "Needs sales by channel.", "محتاج المبيعات حسب القناة."),
    "review_fee_tier": ("Check whether a different marketplace plan or category has lower fees.",
                        "شوف لو فيه باقة أو فئة تانية في المنصة رسومها أقل.", "Read the plan terms carefully.",
                        "اقرأ شروط الباقة كويس."),
}


def recommendations(f: dict, d: dict, lang: str) -> list[dict]:
    ar = lang == "ar"
    cur = d["currency"]
    saving_per_order = abs(f["change_per_order"])
    monthly = saving_per_order * d["current"]["orders"]
    out = []
    for key in OPTIONS.get(f["driver"], []):
        en_t, ar_t, en_n, ar_n = OPTION_TEXT[key]
        out.append({"key": key, "title": ar_t if ar else en_t, "tradeoffs": ar_n if ar else en_n})
    projection = {
        "type": "projection", "per_order": round(saving_per_order, 2), "monthly": round(monthly),
        "currency": cur,
        "text": (f"لو {DRIVER_LABEL[f['driver']]['ar']} لكل طلب رجع لمستوى {d['base']['period']}، التوفير المتوقع حوالي "
                 f"{_fmt(monthly, cur, lang)} في الشهر على نفس عدد الطلبات ({d['current']['orders']}). ده تقدير مش توفير "
                 "حصل فعلاً." if ar else
                 f"If {DRIVER_LABEL[f['driver']]['en']} per order returned to its {d['base']['period']} level, the "
                 f"projected saving is about {_fmt(monthly, cur, lang)} per month at the same order volume "
                 f"({d['current']['orders']} orders). This is an estimate, not a realised saving."),
        "assumptions": ["same order volume and mix", f"returning to the {d['base']['period']} cost per order",
                        "no change in quality, returns or conversion"],
    }
    return [{"options": out, "projection": projection}]


# ------------------------------------------------------------------------------------------ questions

def next_questions(conn: sqlite3.Connection, iid: str, inv: dict, records: list[dict], m: dict,
                   d: dict | None, evidence_items: list[dict] | None = None) -> list[dict]:
    """Ordered list of the most useful open questions/document requests (first one is 'the next question')."""
    ans = _answers(conn, iid)
    done = lambda qid: qid in ans  # noqa: E731  answered, skipped or "don't know" are never asked again
    prof = inv["profile"]
    have_sales = any(r["type"] == "sales" for r in records)
    queue: list[tuple[str, dict]] = []
    if not have_sales:
        for qid in ("p_worry", "p_sells", "p_channels"):
            if not done(qid):
                queue.append((qid, Q[qid]))
        queue.append(("d_sales", Q["d_sales"]))
    if d and d.get("comparable"):
        for g in d["gaps"]:
            qid = f"gap_{g['category']}_{g['missing_in']}"
            if not done(qid):
                lbl = DRIVER_LABEL.get(g["category"], {"en": g["category"], "ar": g["category"]})
                queue.append((qid, {"kind": "gap", "options": ["missing_invoice", "no_purchase_that_month", "not_sure"],
                                    "upload": "expenses", "category": g["category"],
                                    "en": f"I see {lbl['en']} records for {g['present_in']} but none for "
                                          f"{g['missing_in']}. Is an invoice missing?",
                                    "ar": f"لقيت سجلات {lbl['ar']} لشهر {g['present_in']} ومفيش لشهر {g['missing_in']}. "
                                          "فيه فاتورة ناقصة؟",
                                    "why_en": "Without it I'd compare a full month with an empty one and get it wrong.",
                                    "why_ar": "من غيرها هقارن شهر كامل بشهر فاضي وأطلع بنتيجة غلط."}))
        for f in d["findings"][:2]:
            qid = f"e_{f['driver']}"
            if f["driver"] in EVIDENCE_Q and not done(qid):
                queue.append((qid, {"kind": "evidence", **EVIDENCE_Q[f["driver"]],
                                    "why_en": "Your answer decides which fix makes sense.",
                                    "why_ar": "إجابتك هتحدد أنهي حل منطقي."}))
    ev = {i["key"]: i for i in (evidence_items or [])}
    if have_sales:
        from . import evidence as evidence_mod
        for it in evidence_mod.requests(evidence_items or [], ans):  # document requests come from the register
            queue.append((it["key"], Q[it["key"]]))
        for qid in ("p_worry", "p_sells", "p_channels"):
            if not done(qid):
                queue.append((qid, Q[qid]))
    from .evidence import SPEC as EV_SPEC
    out = []
    for qid, q in queue:
        extra = {}
        if qid in EV_SPEC:  # every document request says what it answers and what to do without it
            extra = {"answers_question": EV_SPEC[qid]["question"], "if_unavailable": EV_SPEC[qid]["alternative"],
                     "optional": EV_SPEC[qid]["optional"], "trigger": (ev.get(qid) or {}).get("trigger")}
        out.append({"id": qid, "kind": q["kind"], "options": q.get("options", []), "multi": q.get("multi", False),
                    "upload": q.get("upload"), "category": q.get("category"),
                    "text": {"en": q["en"], "ar": q["ar"]}, "why": {"en": q["why_en"], "ar": q["why_ar"]}, **extra})
    return out


# ------------------------------------------------------------------------------------------ charts

def charts(m: dict, d: dict | None, cur: str | None) -> list[dict]:
    if not cur:
        return []
    ps = [p for p in m["periods"] if p["currency"] == cur]
    out = [{"id": "trend", "type": "line", "currency": cur,
            "periods": [p["period"] for p in ps],
            "series": {"net_sales": [p["net_sales"] for p in ps], "contribution": [p["contribution"] for p in ps]},
            "estimated": any(p["estimated"] for p in ps),
            "missing": sorted({x for p in ps for x in p["missing"]})}]
    if d and d.get("comparable"):
        gap_cats = {g["category"] for g in d.get("gaps", [])}
        comps = [k for k in ["cogs", "packaging", "shipping", "payment_fees", "marketplace_fees", "discounts", "refunds"]
                 if k not in gap_cats]  # a month with no records is missing data, not a cost drop
        out.append({"id": "cost_per_order", "type": "grouped_bar", "currency": cur, "missing_months": sorted(gap_cats),
                    "periods": [d["base"]["period"], d["current"]["period"]],
                    "series": {k: [round(d["base"]["per_order"][k]), round(d["current"]["per_order"][k])] for k in comps},
                    "estimated": d["base"]["estimated"] or d["current"]["estimated"],
                    "missing": sorted(set(d["base"]["missing"]) | set(d["current"]["missing"]))})
        out.append({"id": "bridge", "type": "waterfall", "currency": cur,
                    "periods": [d["base"]["period"], d["current"]["period"]],
                    "start": round(d["bridge"]["base_per_order"]), "end": round(d["bridge"]["current_per_order"]),
                    "steps": {k: round(v) for k, v in d["bridge"]["components"].items()},
                    "untested": d["untested"], "estimated": d["base"]["estimated"] or d["current"]["estimated"]})
        prods = [p for p in m["products"] if p["currency"] == cur and p["period"] == d["current"]["period"]
                 and p["product_margin"] is not None]
        if prods:
            prods.sort(key=lambda p: p["product_margin_pct"] if p["product_margin_pct"] is not None else 0)
            out.append({"id": "products", "type": "bar", "currency": cur, "periods": [d["current"]["period"]],
                        "items": [{"product": p["product"], "margin_pct": p["product_margin_pct"],
                                   "product_margin": p["product_margin"], "units": p["units"]} for p in prods[:15]],
                        "note": "before packaging, shipping and fees"})
    return out


# ------------------------------------------------------------------------------------------ full state

def state(conn: sqlite3.Connection, iid: str, tenant: str, lang: str = "ar", base_p: str | None = None,
          cur_p: str | None = None) -> dict:
    from . import tracking
    inv = store.get(conn, iid, tenant)
    recs = store.records(conn, iid)
    m = metrics.compute(recs)
    cur = _main_currency(m)
    d = diagnose(recs, m, cur, base_p, cur_p) if cur else None
    if d and d.get("comparable"):
        for f in d["findings"]:
            f["explanation"] = explain(f, d, lang)
            f["recommendation"] = recommendations(f, d, lang)[0]
            f["label"] = DRIVER_LABEL[f["driver"]][lang]
    order_view, o = None, None
    if cur and any(r["type"] == "sales" for r in recs):
        from . import orders as orders_mod, simulator
        try:
            o = orders_mod.compute(recs, cur, (inv.get("settings") or {}).get("allocation"))
        except ValueError:
            o = orders_mod.compute(recs, cur, None)
        last = max((x["period"] for x in o["orders"]), default=None)
        order_view = {k: o[k] for k in ("currency", "allocation", "products", "channels", "periods", "allocations",
                                        "unallocated", "unmatched_costs", "unmatched_refunds", "reconciliation",
                                        "loss_orders", "loss_order_count", "incomplete_orders",
                                        "orders_with_allocated_costs", "orders_with_actual_costs", "method_text")}
        order_view["order_count"] = len(o["orders"])
        order_view["insights"] = orders_mod.insights(o, lang)
        order_view["allowed_allocation"] = orders_mod.ALLOWED
        order_view["simulator"] = {"period": last, "periods": sorted({x["period"] for x in o["orders"]}),
                                   "capabilities": simulator.capabilities(o, last) if last else {}}
        order_view["monthly_contribution_total"] = sum(p["contribution"] for p in m["periods"] if p["currency"] == cur)
    from . import evidence as evidence_mod
    files = store.files(conn, iid)
    answers_now = _answers(conn, iid)
    ev_items = evidence_mod.register(records=recs, m=m, d=d, orders=order_view, files=files, answers=answers_now,
                                     profile=inv["profile"]) if recs else []
    qs = next_questions(conn, iid, inv, recs, m, d, ev_items)
    stage = ("profile" if not recs and qs and qs[0]["kind"] == "profile" else "documents"
             if not any(r["type"] == "sales" for r in recs) else "analysis")
    interventions = tracking.list_for(conn, iid)
    if interventions:
        stage = "tracking"
    elif d and d.get("findings"):
        stage = "recommendations"
    counts: dict[str, int] = {}
    for r in recs:
        counts[r["type"]] = counts.get(r["type"], 0) + 1
    out = {"investigation": inv, "stage": stage, "files": files, "record_counts": counts, "evidence": ev_items,
            "orders": order_view, "scenarios": _scenarios(conn, iid),
            "metrics": m, "main_currency": cur, "diagnosis": d, "questions": qs,
            "answers": _answers(conn, iid), "charts": charts(m, d, cur), "interventions": interventions,
            "definitions": metrics.DEFINITIONS, "summary": _import_summary(recs, m, lang)}
    from . import actions as actions_mod, outreach as outreach_mod
    out["outreach"] = outreach_mod.list_for(conn, iid)
    out["actions"] = actions_mod.build(conn, iid, out, lang, tenant)
    return out


def _scenarios(conn: sqlite3.Connection, iid: str) -> list[dict]:
    import json
    out = []
    for r in conn.execute("SELECT id, name, params, result, intervention_id, created_at FROM scenarios WHERE "
                          "investigation_id=? ORDER BY id DESC", (iid,)):
        res = json.loads(r[3])
        out.append({"id": r[0], "name": r[1], "params": json.loads(r[2]), "period": res.get("period"),
                    "delta_contribution": res.get("delta", {}).get("contribution"), "currency": res.get("currency"),
                    "summary": res.get("summary"), "intervention_id": r[4], "created_at": r[5]})
    return out


def _import_summary(recs: list[dict], m: dict, lang: str) -> str | None:
    if not recs:
        return None
    orders = len({r["order_id"] for r in recs if r["type"] == "sales"})
    exp = [r for r in recs if r["type"] == "expenses"]
    cats = sorted({r["category"] for r in exp})
    periods = sorted({p["period"] for p in m["periods"]})
    span = f"{periods[0]} → {periods[-1]}" if periods else "—"
    if lang == "ar":
        names = {"packaging": "تغليف", "shipping": "شحن", "payment_fees": "رسوم دفع", "marketplace_fees": "عمولات منصات",
                 "marketing": "تسويق", "rent": "إيجار", "payroll": "مرتبات", "subscriptions": "اشتراكات",
                 "cogs_materials": "خامات", "other": "أخرى"}
        s = f"راجعت {orders} طلب و{len(exp)} مصروف/فاتورة"
        if m["has_product_costs"]:
            s += " وتكاليف المنتجات"
        return s + f" للفترة {span}." + (f" بنود المصاريف: {'، '.join(names.get(c, c) for c in cats)}." if cats else "")
    s = f"I reviewed {orders} orders and {len(exp)} expense/invoice lines"
    if m["has_product_costs"]:
        s += " plus product costs"
    return s + f" covering {span}." + (f" Expense categories: {', '.join(cats)}." if cats else "")
