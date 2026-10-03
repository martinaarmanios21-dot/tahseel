"""Deterministic policy layer. The agent cannot change anything in this file.

Every decision passes through `precheck` before it can touch the outside world. The LLM is never trusted
to enforce these rules itself: permissions, validation, rate limits and stop conditions live here.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from .config import Settings
from .models import CONTACT_ACTIONS, CURRENCY_MARKERS, PAY_LINK, Decision, amount_number, money

# Inbound replies: classified deterministically (English + Arabic). Injection is checked first and wins.
_INJECTION = re.compile(
    r"ignore (all |any )?(previous|prior|above) instructions|system override|admin mode|you are now|"
    r"<!--|propose_skill|promote|kill_switch|mark (invoice )?\S* ?as paid|apply a \d+% discount|"
    r"تجاهل (كل |جميع )?التعليمات|تعليمات النظام|وضع المسؤول|أنت الآن|اعتبر الفاتورة مدفوعة|"
    r"سجل الفاتورة (كـ ?)?مدفوعة|خصم \d+ ?%",
    re.I,
)
_SIGNALS: list[tuple[str, re.Pattern]] = [
    ("opt_out", re.compile(r"stop (emailing|contacting)|unsubscribe|remove me|توقفوا عن (مراسلتنا|التواصل)|"
                           r"لا ترسلوا|إلغاء الاشتراك", re.I)),
    ("paid_claim", re.compile(r"already paid|payment was sent|we paid|bank ref|\bref TX-|دفعنا|تم الدفع|"
                              r"سددنا|تم السداد|تم التحويل|رقم التحويل|مرجع", re.I)),
    ("dispute", re.compile(r"\bdispute|invoice is wrong|incorrect|never delivered|billed for|نعترض|اعتراض|"
                           r"الفاتورة (غير صحيحة|خاطئة|خطأ)|لم يتم (تسليم|التسليم)|لم نستلم", re.I)),
    ("cash_flow", re.compile(r"cash flow|can't (pay|cover) the full|split it|installment|flexibility|السيولة|"
                             r"لا نستطيع (دفع|سداد) (المبلغ )?(كامل|بالكامل)|تقسيط|أقساط|مهلة", re.I)),
    ("angry", re.compile(r"unacceptable|account manager|complain|غير مقبول|سأشتكي|شكوى|مدير الحساب", re.I)),
]

# Outbound message rules (English + Arabic)
_LEGAL_THREAT = re.compile(
    r"\b(lawsuit|legal action|court|attorney|lawyer|sue|collections? agency|debt collector|credit (bureau|report)|police)\b|"
    r"محكمة|المحكمة|محامي|محامٍ|قضية|دعوى|إجراءات قانونية|الإجراءات القانونية|الشرطة|النيابة|"
    r"(شركة|مكتب|وكالة) تحصيل|القائمة السوداء",
    re.I,
)
_DISCOUNT = re.compile(
    r"\b(discount|waive|write[- ]?off|% off|reduce(d)? (the )?(amount|balance))\b|خصم|تخفيض|إعفاء|إسقاط|"
    r"تنازل عن",
    re.I,
)
_ARABIC_CHARS = re.compile(r"[\u0600-\u06FF]")
_LATIN_CHARS = re.compile(r"[A-Za-z]")
_URL = re.compile(r"https?://[^\s)>\]]+", re.I)
_INSTRUCTION_LEAK = re.compile(r"ignore (all )?previous instructions|system prompt|hard rules|تعليمات النظام", re.I)


def classify_reply(text: str | None) -> str:
    if not text:
        return "none"
    if _INJECTION.search(text):
        return "injection"
    for name, pattern in _SIGNALS:
        if pattern.search(text):
            return name
    return "reply"


@dataclass(frozen=True)
class Verdict:
    status: str  # allow | approve | block
    code: str
    reason: str


def idempotency_key(run_id: str, invoice_id: str, rnd: int, action: str) -> str:
    return hashlib.sha256(f"{run_id}|{invoice_id}|{rnd}|{action}".encode()).hexdigest()[:32]


def validate_message(invoice: dict, decision: Decision, other_customers: list[str], settings: Settings) -> list[str]:
    """Return a list of violations (empty == valid)."""
    if decision.action not in CONTACT_ACTIONS:
        return []
    msg = decision.message or ""
    errors: list[str] = []
    if not 40 <= len(msg) <= 1200:
        errors.append(f"length {len(msg)} outside 40..1200")
    if invoice["id"] not in msg:
        errors.append("missing invoice id")
    if amount_number(invoice["amount_cents"]) not in msg or not any(m in msg for m in CURRENCY_MARKERS):
        errors.append(f"missing exact amount {money(invoice['amount_cents'], invoice.get('language', 'en'))}")
    arabic = len(_ARABIC_CHARS.findall(msg))
    latin = len(_LATIN_CHARS.findall(_URL.sub("", msg).replace(invoice["id"], "").replace("EGP", "")))
    if invoice.get("language") == "ar" and arabic < 2 * latin:
        errors.append("customer prefers Arabic but the message is not in Arabic")
    if invoice.get("language", "en") == "en" and arabic > 0:
        errors.append("customer prefers English but the message contains Arabic")
    if _LEGAL_THREAT.search(msg):
        errors.append("legal threat language")
    if _DISCOUNT.search(msg):
        errors.append("discount / write-off language")
    if _INSTRUCTION_LEAK.search(msg):
        errors.append("prompt/instruction leak")
    allowed_link = PAY_LINK.format(invoice_id=invoice["id"])
    urls = [u.rstrip(".,;:!?") for u in _URL.findall(msg)]
    bad = [u for u in urls if u != allowed_link]
    if bad:
        errors.append(f"unapproved URL(s): {bad[:2]}")
    if decision.include_payment_link and allowed_link not in urls:
        errors.append("include_payment_link=true but approved link missing")
    if not decision.include_payment_link and urls:
        errors.append("link present but include_payment_link=false")
    lowered = msg.lower()
    leaked = [c for c in other_customers if c.lower() in lowered and c != invoice["customer"]]
    if leaked:
        errors.append(f"mentions other customers: {leaked[:2]}")
    if decision.action == "offer_payment_plan":
        if decision.installments is None or decision.installments < 2:
            errors.append("payment plan needs installments >= 2")
    return errors


def precheck(
    invoice: dict,
    decision: Decision,
    *,
    rnd: int,
    is_ledger_paid: bool,
    other_customers: list[str],
    settings: Settings,
) -> Verdict:
    """Policy decision for one action. Pure function: no I/O, fully unit-testable."""
    if decision.invoice_id != invoice["id"]:
        return Verdict("block", "id_mismatch", "decision invoice_id does not match")
    state = invoice["state"]
    if state not in {"NEW", "CONTACTED"}:
        return Verdict("block", "not_open", f"invoice is {state}")
    action = decision.action
    if action in {"wait", "verify_payment", "escalate_to_human"}:
        return Verdict("allow", "ok", "read-only / internal action")

    # Contact actions from here on: these reach a real customer.
    signal = invoice.get("reply_signal", "none")
    if is_ledger_paid:
        return Verdict("block", "ledger_paid", "accounting ledger shows this invoice is paid")
    if signal == "dispute":
        return Verdict("block", "open_dispute", "customer disputes the invoice; humans only")
    if signal == "opt_out":
        return Verdict("block", "opted_out", "customer asked us to stop contacting them")
    if signal == "paid_claim":
        return Verdict("block", "unverified_paid_claim", "customer says they paid; verify_payment first")
    if invoice["touches"] >= settings.max_touches:
        return Verdict("block", "max_touches", f"already contacted {invoice['touches']} times")
    if invoice.get("last_contact_round", 0) >= rnd:
        return Verdict("block", "rate_limited", "max one contact per debtor per round")
    errors = validate_message(invoice, decision, other_customers, settings)
    if errors:
        return Verdict("block", "invalid_message", "; ".join(errors))
    if action == "offer_payment_plan" and (decision.installments or 0) > settings.max_installments:
        return Verdict("approve", "plan_over_limit", f"{decision.installments} installments > policy max")
    if invoice["tier"] == "key":
        return Verdict("approve", "key_account", "key accounts always need human approval")
    if invoice["amount_cents"] >= settings.approval_threshold_cents:
        return Verdict("approve", "high_value", f"amount >= {money(settings.approval_threshold_cents)}")
    return Verdict("allow", "ok", "passed all checks")
