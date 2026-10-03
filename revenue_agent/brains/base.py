"""Shared brain interface plus the features/message helpers every brain uses."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from ..models import PAY_LINK, history_bucket, money


class BrainError(RuntimeError):
    """The brain could not produce decisions (the engine falls back or halts)."""


@dataclass
class BrainResult:
    decisions: list[dict]
    engine: str
    llm_calls: int = 0
    tokens: int = 0
    notes: list[str] = field(default_factory=list)


@dataclass
class BrainContext:
    run_id: str
    round: int
    trace_id: str


class Brain(Protocol):
    name: str

    def decide(self, views: list[dict], skill_content: str, ctx: BrainContext) -> BrainResult: ...

    def reflect(self, report: dict, skill_content: str, ctx: BrainContext) -> str: ...


def features(view: dict) -> dict:
    return {
        "signal": view["signal"],
        "tier": view["tier"],
        "history": view["history"],
        "touch": view["touch"],
    }


def agent_view(invoice: dict) -> dict:
    """What the agent is allowed to see. The hidden persona is never included."""
    reply = invoice.get("last_reply")
    return {
        "invoice_id": invoice["id"],
        "customer": invoice["customer"],
        "contact_name": invoice["contact_name"],
        "language": invoice.get("language", "en"),
        "business": invoice.get("business", "default"),
        "segment": invoice["segment"],
        "tier": invoice["tier"],
        "amount_display": money(invoice["amount_cents"], invoice.get("language", "en")),
        "due_date": invoice["due_date"],
        "days_overdue": invoice["days_overdue"],
        "late_payments_12m": invoice["late_payments_12m"],
        "history": history_bucket(invoice["late_payments_12m"]),
        "touches": invoice["touches"],
        "touch": "first" if invoice["touches"] == 0 else "followup",
        "signal": invoice.get("reply_signal") or "none",
        "last_reply": f"<untrusted_customer_reply>{reply}</untrusted_customer_reply>" if reply else None,
        "payment_link": PAY_LINK.format(invoice_id=invoice["id"]),
    }


_TEXT = {
    "en": {
        "open": {"friendly": "Hi {name}, I hope all is well!", "neutral": "Hello {name},", "firm": "Hello {name},"},
        "body": {
            "friendly": "Just a quick reminder that invoice {id} for {amount} is now {days} days past due.",
            "neutral": "Our records show that invoice {id} for {amount} remains unpaid ({days} days past due).",
            "firm": "Invoice {id} for {amount} is {days} days overdue and requires payment now.",
        },
        "due": "The original due date was {due}.",
        "plan": "If it helps, we can split the balance into {k} monthly installments.",
        "link": "You can pay securely here: {link}",
        "close": {"friendly": "Thanks so much, and let us know if anything is unclear!", "neutral": "Thank you.",
                  "firm": "Please arrange payment within 7 days."},
    },
    "ar": {
        "open": {"friendly": "أهلاً أستاذ/ة {name}، نتمنى أن تكونوا بخير!", "neutral": "السيد/ة {name}، تحية طيبة،",
                 "firm": "السيد/ة {name}، تحية طيبة،"},
        "body": {
            "friendly": "نود تذكيركم بلطف بأن الفاتورة رقم {id} بقيمة {amount} متأخرة منذ {days} يوماً.",
            "neutral": "تشير سجلاتنا إلى أن الفاتورة رقم {id} بقيمة {amount} لم تُسدد بعد (متأخرة {days} يوماً).",
            "firm": "الفاتورة رقم {id} بقيمة {amount} متأخرة منذ {days} يوماً ويجب سدادها الآن.",
        },
        "due": "كان تاريخ الاستحقاق الأصلي {due}.",
        "plan": "إذا كان ذلك يساعدكم، يمكننا تقسيم المبلغ على {k} أقساط شهرية.",
        "link": "يمكنكم السداد بأمان من هنا: {link}",
        "close": {"friendly": "شكراً جزيلاً، ولا تترددوا في التواصل معنا لأي استفسار!", "neutral": "مع خالص الشكر.",
                  "firm": "برجاء السداد خلال 7 أيام."},
    },
}


def render_message(view: dict, decision: dict) -> str:
    """Deterministic, policy-compliant email in the customer's language (offline brain + exploration)."""
    if decision["action"] not in {"send_reminder", "offer_payment_plan"}:
        return ""
    t = _TEXT["ar" if view.get("language") == "ar" else "en"]
    tone = decision.get("tone", "neutral")
    parts = [
        t["open"][tone].format(name=view["contact_name"]),
        t["body"][tone].format(id=view["invoice_id"], amount=view["amount_display"], days=view["days_overdue"]),
    ]
    if decision.get("mention_due_date"):
        parts.append(t["due"].format(due=view["due_date"]))
    if decision["action"] == "offer_payment_plan":
        parts.append(t["plan"].format(k=decision.get("installments") or 3))
    if decision.get("include_payment_link"):
        parts.append(t["link"].format(link=view["payment_link"]))
    parts.append(t["close"][tone])
    return " ".join(parts)


def match_rule(rules: list[dict], feats: dict) -> tuple[int, dict] | None:
    for i, rule in enumerate(rules):
        when = rule.get("when") or {}
        if all(feats.get(k) == v for k, v in when.items()):
            return i, rule
    return None
