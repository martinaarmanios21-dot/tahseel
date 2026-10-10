"""The investigation's next actions: findings -> evidence -> supplier outreach -> quotes -> simulator -> experiment.

Every action carries the finding (or evidence gap) that triggered it, why it matters, the evidence or outcome it should
produce, an impact figure only when one exists in the data (always labelled as a projection), and the next step.
No action is generated without a trigger: no finding and no evidence gap means an empty list.
"""

from __future__ import annotations

from . import outreach as outreach_mod, quotes as quotes_mod

T = {
    "document": {"why": {"en": "This evidence is missing for a question that matters now.",
                         "ar": "المعلومة دي ناقصة وهي مهمة للسؤال اللي بنحاول نجاوبه دلوقتي."},
                 "next": {"en": "Upload it from the Next step card, or say you don't have it.",
                          "ar": "ارفعها من كارت «الخطوة الجاية»، أو قول إنها مش عندك."}},
    "request_quotes": {"why": {"en": "Real alternative prices show whether this cost can come down without losing quality.",
                               "ar": "أسعار بديلة حقيقية بتوضح هل التكلفة دي ممكن تقل من غير ما الجودة تقل."},
                       "expected": {"en": "2–3 written quotes for the same specification.",
                                    "ar": "٢-٣ عروض أسعار مكتوبة لنفس المواصفات."},
                       "next": {"en": "Fill in the supplier brief, review the email, approve it, then send or copy it.",
                                "ar": "اكتب تفاصيل الطلب للمورد، راجع الإيميل ووافق عليه، وبعدين ابعته أو انسخه."}},
    "await_reply": {"why": {"en": "A request went out (or you sent it yourself).", "ar": "الطلب اتبعت (أو إنت بعته بنفسك)."},
                    "expected": {"en": "The supplier's written quote.", "ar": "عرض السعر المكتوب من المورد."},
                    "next": {"en": "When the reply arrives, add it as a quote linked to this request.",
                             "ar": "لما الرد يوصل، ضيفه كعرض سعر مربوط بالطلب ده."}},
    "compare": {"why": {"en": "You have confirmed, comparable quotes.", "ar": "عندك عروض مؤكدة وقابلة للمقارنة."},
                "expected": {"en": "The cost per unit you actually need, with terms and quality side by side.",
                             "ar": "تكلفة الوحدة اللي محتاجها فعلاً، مع الشروط والجودة جنب بعض."},
                "next": {"en": "Compare, then test the best fit in the simulator.",
                         "ar": "قارن، وبعدين جرّب الأنسب في الحاسبة."}},
    "moq": {"why": {"en": "A minimum order quantity forces you to buy units you don't need yet.",
                    "ar": "أقل كمية للطلب بتخليك تشتري حاجات مش محتاجها دلوقتي."},
            "expected": {"en": "A smaller-quantity option or price tiers.", "ar": "كمية أقل أو أسعار حسب الكمية."},
            "next": {"en": "Prepare a short question to that supplier.", "ar": "جهّز سؤال قصير للمورد ده."}},
    "track": {"why": {"en": "A saved scenario is only an estimate until you measure it.",
                      "ar": "السيناريو المحفوظ تقدير لحد ما نقيسه."},
              "expected": {"en": "A baseline now, and a measured result after the change.",
                           "ar": "نقطة بداية دلوقتي، ونتيجة مقاسة بعد التغيير."},
              "next": {"en": "Save it as an experiment, then mark the start date when you make the change.",
                       "ar": "احفظه كتجربة، وبعدين سجّل تاريخ البداية لما تنفّذ التغيير."}},
    "verify": {"why": {"en": "You started a change; only new records can show what happened.",
                       "ar": "إنت بدأت تغيير؛ والسجلات الجديدة بس هي اللي هتوضح حصل إيه."},
               "expected": {"en": "An observed before/after comparison (not proof of cause).",
                            "ar": "مقارنة قبل وبعد (مش إثبات إن التغيير هو السبب)."},
               "next": {"en": "Upload records dated after the change, then click Check the result.",
                        "ar": "ارفع سجلات بعد تاريخ التغيير، واضغط «قيس النتيجة»."}},
}


def build(conn, iid: str, st: dict, lang: str, tenant: str) -> list[dict]:
    acts: list[dict] = []
    d = st.get("diagnosis") or {}
    findings = {f["driver"]: f for f in d.get("findings", [])} if d.get("comparable") else {}
    outreach = outreach_mod.list_for(conn, iid)
    all_quotes = quotes_mod.list_for(conn, iid)

    for ev in [e for e in st.get("evidence", []) if e["status"] == "missing"][:2]:
        acts.append({"kind": "document", "evidence": ev["key"], "trigger": ev["trigger"][lang],
                     "title": ev["label"][lang], "why": T["document"]["why"][lang], "expected": ev["question"][lang],
                     "impact": None, "next": T["document"]["next"][lang], "if_unavailable": ev["alternative"][lang]})

    for opp in outreach_mod.opportunities(st):
        f = findings[opp["driver"]]
        mine = [o for o in outreach if o["trigger"].get("kind") == "finding" and o["trigger"].get("driver") == opp["driver"]
                and o["status"] != "cancelled"]
        groups = {o["item_key"] for o in mine} | {q["item_key"] for q in all_quotes if q["category"] == opp["category"]}
        comparable_groups = []
        for g in groups:
            try:
                c = quotes_mod.compare(conn, iid, tenant=tenant, item_key=g)
            except quotes_mod.QuoteError:
                continue
            if len(c["comparable"]) >= 2:
                comparable_groups.append(c)
            for r in c["comparable"]:
                if r["extra_units_due_to_moq"] and not any(o["purpose"] == "moq_question" and
                                                           o["trigger"].get("quote_id") == r["quote_id"] for o in outreach):
                    acts.append({"kind": "moq", "quote_id": r["quote_id"], "trigger":
                                 f"{r['supplier']}: {r['extra_units_due_to_moq']:g} extra units", "title": r["supplier"],
                                 "why": T["moq"]["why"][lang], "expected": T["moq"]["expected"][lang], "impact": None,
                                 "next": T["moq"]["next"][lang]})
        label = f.get("label") or opp["driver"]
        trigger = f"{label}: {f['explanation']['what']}" if f.get("explanation") else label
        impact = f["recommendation"]["projection"]["text"] if f.get("recommendation") else None
        if comparable_groups:
            for c in comparable_groups:
                acts.append({"kind": "compare", "item_key": c["item_key"], "driver": opp["driver"], "trigger": trigger,
                             "title": c["item_key"], "why": T["compare"]["why"][lang],
                             "expected": T["compare"]["expected"][lang], "impact": impact, "next": T["compare"]["next"][lang]})
        elif any(o["status"] in ("sent", "copied_manual") for o in mine):
            acts.append({"kind": "await_reply", "driver": opp["driver"], "trigger": trigger, "title": label,
                         "why": T["await_reply"]["why"][lang], "expected": T["await_reply"]["expected"][lang],
                         "impact": None, "next": T["await_reply"]["next"][lang],
                         "outreach_ids": [o["id"] for o in mine if o["status"] in ("sent", "copied_manual")]})
        else:
            acts.append({"kind": "request_quotes", "driver": opp["driver"], "trigger": trigger, "title": label,
                         "why": T["request_quotes"]["why"][lang], "expected": T["request_quotes"]["expected"][lang],
                         "impact": impact, "next": T["request_quotes"]["next"][lang],
                         "draft_ids": [o["id"] for o in mine if o["status"] in ("draft", "approved")]})

    for s in st.get("scenarios", []):
        if not s["intervention_id"]:
            acts.append({"kind": "track", "scenario_id": s["id"], "trigger": s["name"], "title": s["name"],
                         "why": T["track"]["why"][lang], "expected": T["track"]["expected"][lang],
                         "impact": s["summary"], "next": T["track"]["next"][lang]})
    for x in st.get("interventions", []):
        if x["status"] in ("in_progress", "awaiting_data"):
            acts.append({"kind": "verify", "intervention_id": x["id"], "trigger": x["title"], "title": x["title"],
                         "why": T["verify"]["why"][lang], "expected": T["verify"]["expected"][lang], "impact": None,
                         "next": T["verify"]["next"][lang]})
    return acts
