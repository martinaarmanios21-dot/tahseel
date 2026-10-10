"""Evidence register for an investigation: which records exist, which are missing, and why each one matters.

Derived (not stored) from the investigation's records, files, answers, findings and order-level result, so it can
never drift from the data. Each item says what is needed, why, which business question it answers, what the owner
can do if it is unavailable, whether it is optional, and its status:

  missing                 needed and not provided (a request may be shown)
  awaiting_confirmation   data arrived but needs the owner (unclear table, inferred categories, extracted values,
                          a month without invoices)
  processed               usable and in the calculations
  unavailable             the owner said they don't have it  (never asked again; the analysis continues without it)
  skipped                 the owner skipped it               (never asked again)

Uploads are processed synchronously, so "received" collapses into processed / awaiting_confirmation; a file that
could not be read is reported on the file itself and never counts as evidence.
Items are only created when they serve a question: e.g. a courier statement by order is requested only when
shipping costs exist but cannot be tied to orders AND it matters (loss-making orders or a shipping finding).
Nothing here is ever treated as zero: a missing item makes the affected figures "untested" or "estimated".
"""

from __future__ import annotations

ORDER = ["d_sales", "d_costs", "d_shipping", "d_packaging", "d_courier_orders", "d_payment_orders", "d_fees",
         "d_returns", "d_fixed"]

SPEC = {
    "d_sales": {"label": {"en": "Sales or orders report", "ar": "تقرير المبيعات أو الطلبات"}, "optional": False,
                "question": {"en": "How much money comes in per order, and is it growing?",
                             "ar": "كل طلب بيدخّل كام، وهل ده بيزيد؟"},
                "alternative": {"en": "Most shops/platforms can export orders as CSV or Excel; the template shows the "
                                      "columns.", "ar": "أغلب المنصات بتطلّع الطلبات CSV أو Excel؛ القالب بيوضح الأعمدة."}},
    "d_costs": {"label": {"en": "Product unit costs", "ar": "تكلفة القطعة لكل منتج"}, "optional": False,
                "question": {"en": "How much does each sale really leave you after the product cost?",
                             "ar": "كل بيعة بتسيبلك كام فعلاً بعد تكلفة المنتج؟"},
                "alternative": {"en": "A simple list of product + cost per unit is enough (template), or supplier "
                                      "invoices with quantities.",
                                "ar": "يكفي جدول بسيط: المنتج وتكلفة القطعة (القالب)، أو فواتير الموردين بالكميات."}},
    "d_shipping": {"label": {"en": "Shipping / courier invoices", "ar": "فواتير الشحن"}, "optional": True,
                   "question": {"en": "What does delivery really cost you per order?",
                                "ar": "التوصيل بيكلّفك كام فعلاً في الطلب؟"},
                   "alternative": {"en": "Type the monthly shipping total by hand; I'll mark results as estimated.",
                                   "ar": "اكتب إجمالي الشحن الشهري بإيدك، وهعلّم النتايج إنها تقديرية."}},
    "d_packaging": {"label": {"en": "Packaging invoices", "ar": "فواتير التغليف"}, "optional": True,
                    "question": {"en": "Is packaging eating into what each order leaves you?",
                                 "ar": "هل التغليف بياكل من اللي بيفضل لك من كل طلب؟"},
                    "alternative": {"en": "Type the monthly packaging total by hand.",
                                    "ar": "اكتب إجمالي التغليف الشهري بإيدك."}},
    "d_courier_orders": {"label": {"en": "Courier statement with order numbers", "ar": "كشف شركة الشحن برقم كل طلب"},
                         "optional": True,
                         "question": {"en": "Which orders and areas cost the most to deliver, and which orders lose "
                                            "money because of it?",
                                      "ar": "أنهي طلبات وأماكن بتكلّف أكتر في التوصيل، وأنهي طلبات بتخسر بسببه؟"},
                         "alternative": {"en": "Without it I keep sharing the monthly shipping bill equally across "
                                               "orders (shown as an estimate).",
                                         "ar": "من غيره هفضل أقسّم فاتورة الشحن الشهرية بالتساوي على الطلبات (كتقدير)."}},
    "d_payment_orders": {"label": {"en": "Payment-gateway statement with order numbers",
                                   "ar": "كشف بوابة الدفع برقم كل طلب"}, "optional": True,
                         "question": {"en": "What do payment fees really cost on each order?",
                                      "ar": "رسوم الدفع بتكلّف كام فعلاً في كل طلب؟"},
                         "alternative": {"en": "Without it fees are shared by order value (an estimate).",
                                         "ar": "من غيره الرسوم بتتقسم حسب قيمة الطلب (تقدير)."}},
    "d_fees": {"label": {"en": "Payment or marketplace fee statements", "ar": "كشوف رسوم الدفع أو عمولات المنصات"},
               "optional": True,
               "question": {"en": "How much do fees take from each order?", "ar": "الرسوم بتاخد كام من كل طلب؟"},
               "alternative": {"en": "Type the monthly fee total by hand.", "ar": "اكتب إجمالي الرسوم الشهري بإيدك."}},
    "d_returns": {"label": {"en": "Returns / refunds report", "ar": "تقرير المرتجعات"}, "optional": True,
                  "question": {"en": "How much money comes back after a sale, and why?",
                               "ar": "قد إيه فلوس بترجع بعد البيع، وليه؟"},
                  "alternative": {"en": "If your orders file marks returned orders, I use that instead (less precise).",
                                  "ar": "لو ملف الطلبات معلّم الطلبات المرتجعة هستخدمه بدل كده (أقل دقة)."}},
    "d_fixed": {"label": {"en": "Rent, salaries, subscriptions", "ar": "الإيجار والمرتبات والاشتراكات"}, "optional": True,
                "question": {"en": "How many orders do you need each month to cover your fixed costs?",
                             "ar": "محتاج كام طلب في الشهر عشان تغطي مصاريفك الثابتة؟"},
                "alternative": {"en": "Type the monthly totals by hand.", "ar": "اكتب الإجماليات الشهرية بإيدك."}},
}


def register(*, records: list[dict], m: dict, d: dict | None, orders: dict | None, files: list[dict],
             answers: dict, profile: dict, quotes: list[dict] | None = None) -> list[dict]:
    have = {r["type"] for r in records}
    cats = set(m["categories_present"])
    sells_products = profile.get("sells") in (None, "products", "both")
    online = profile.get("channels") is None or any(c in (profile.get("channels") or "") for c in
                                                    ("website", "social", "marketplaces"))
    findings = {f["driver"]: f for f in (d or {}).get("findings", [])} if d and d.get("comparable") else {}
    pending = _pending_confirmations(files, d, records)
    order_linked = {e["category"] for e in records if e["type"] == "expenses" and e.get("order_id")}
    loss_orders = (orders or {}).get("loss_order_count", 0)

    def item(key: str, needed: bool, provided: bool, trigger: dict | None = None, partial: str | None = None) -> dict | None:
        if not needed and not provided:
            return None
        a = answers.get(key, {}).get("status")
        status = ("processed" if provided and not pending.get(key) else "awaiting_confirmation" if provided
                  else "unavailable" if a == "dont_know" else "skipped" if a == "skipped"
                  else "missing")
        if partial and status == "processed":
            status, reason = "awaiting_confirmation", partial
        else:
            reason = pending.get(key)
        return {"key": key, "status": status, "optional": SPEC[key]["optional"], "label": SPEC[key]["label"],
                "question": SPEC[key]["question"], "alternative": SPEC[key]["alternative"],
                "trigger": trigger or {"en": "basic information for any profit analysis",
                                       "ar": "معلومة أساسية لأي تحليل ربح"},
                "confirmation_needed": reason}

    out = []
    out.append(item("d_sales", True, "sales" in have))
    cov = [p["cogs_coverage"] for p in m["periods"] if p["cogs_coverage"] is not None]
    partial_costs = None
    if m["has_product_costs"] and cov and min(cov) < 0.999:
        missing_products = sorted({p["product"] for p in m["products"] if p["cogs"] is None})
        partial_costs = "no unit cost for: " + ", ".join(missing_products[:8])
    out.append(item("d_costs", "sales" in have, m["has_product_costs"],
                    {"en": "product margins cannot be calculated without it", "ar": "مينفعش نحسب الهوامش من غيرها"},
                    partial_costs))
    out.append(item("d_shipping", "sales" in have and online, "shipping" in cats,
                    {"en": "online orders usually carry delivery costs", "ar": "الطلبات الأونلاين غالباً عليها شحن"}))
    out.append(item("d_packaging", "sales" in have and sells_products, "packaging" in cats,
                    {"en": "physical products need packaging", "ar": "المنتجات محتاجة تغليف"}))
    shipping_matters = "shipping" in findings or loss_orders > 0
    if "shipping" in cats and "shipping" not in order_linked and shipping_matters:
        trig = ({"en": "shipping cost per order rose", "ar": "تكلفة الشحن لكل طلب زادت"} if "shipping" in findings else
                {"en": f"{loss_orders} orders lose money and delivery is shared as an estimate",
                 "ar": f"{loss_orders} طلب بيخسروا والشحن متقسّم عليهم كتقدير"})
        out.append(item("d_courier_orders", True, False, trig))
    elif "shipping" in order_linked:
        out.append(item("d_courier_orders", False, True))
    if "payment_fees" in cats and "payment_fees" not in order_linked and ("payment_fees" in findings or loss_orders > 0):
        out.append(item("d_payment_orders", True, False,
                        {"en": "payment fees are only known as monthly totals", "ar": "رسوم الدفع معروفة كإجمالي شهري بس"}))
    out.append(item("d_fees", "sales" in have and online, bool({"payment_fees", "marketplace_fees"} & cats),
                    {"en": "online payments and marketplaces take a fee per order",
                     "ar": "الدفع الأونلاين والمنصات بياخدوا رسوم على كل طلب"}))
    out.append(item("d_returns", "sales" in have, m["has_returns_file"],
                    {"en": "refunds reduce what each sale leaves you", "ar": "المرتجعات بتقلّل اللي بيفضل من كل بيعة"}))
    out.append(item("d_fixed", "sales" in have, bool({"rent", "payroll", "subscriptions"} & cats),
                    {"en": "needed for break-even and operating profit", "ar": "محتاجينها للتعادل والربح التشغيلي"}))
    items = [i for i in out if i]
    items.sort(key=lambda i: ORDER.index(i["key"]))
    return items


CATEGORY_KEY = {"packaging": "d_packaging", "shipping": "d_shipping", "payment_fees": "d_fees",
                "marketplace_fees": "d_fees", "rent": "d_fixed", "payroll": "d_fixed", "subscriptions": "d_fixed"}


def _pending_confirmations(files: list[dict], d: dict | None, records: list[dict] | None = None) -> dict[str, str]:
    """Which evidence has data that still needs the owner's confirmation before it is fully trusted."""
    out: dict[str, str] = {}
    type_key = {"sales": "d_sales", "product_costs": "d_costs", "returns": "d_returns"}
    inferred: dict[str, int] = {}
    for r in records or []:  # only the categories that were actually inferred need confirming
        if r["type"] == "expenses" and "category_inferred" in r.get("flags", []):
            key = CATEGORY_KEY.get(r["category"])
            if key:
                inferred[key] = inferred.get(key, 0) + 1
    for key, n in inferred.items():
        out[key] = f"{n} rows were categorised from their description: confirm them with 'Fix columns' on the file"
    for f in files:
        if f["status"] != "imported":
            continue
        for t in f["summary"]["tables"]:
            if t["needs_confirmation"] and t["detected_type"] in type_key:
                out.setdefault(type_key[t["detected_type"]], "; ".join(t["needs_confirmation"])[:200])
    for g in (d or {}).get("gaps", []) if d and d.get("comparable") else []:
        key = {"packaging": "d_packaging", "shipping": "d_shipping", "payment_fees": "d_fees",
               "marketplace_fees": "d_fees"}.get(g["category"])
        if key:
            out[key] = f"no records for {g['missing_in']} (present in {g['present_in']})"
    return out


def requests(items: list[dict], answers: dict) -> list[dict]:
    """Document requests still worth asking, in priority order: required first, then by the register order."""
    req = [i for i in items if i["status"] == "missing" and i["key"] not in answers]
    req.sort(key=lambda i: (i["optional"], ORDER.index(i["key"])))
    return req
