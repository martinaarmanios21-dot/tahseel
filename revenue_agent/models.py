"""Typed contracts shared by brains, guardrails and the MCP server."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Action = Literal["send_reminder", "offer_payment_plan", "verify_payment", "escalate_to_human", "wait"]
Tone = Literal["friendly", "neutral", "firm"]

ACTIONS: tuple[str, ...] = ("send_reminder", "offer_payment_plan", "verify_payment", "escalate_to_human", "wait")
CONTACT_ACTIONS = {"send_reminder", "offer_payment_plan"}
TONES: tuple[str, ...] = ("friendly", "neutral", "firm")
SIGNALS: tuple[str, ...] = ("none", "reply", "cash_flow", "dispute", "paid_claim", "angry", "opt_out", "injection")
TIERS: tuple[str, ...] = ("standard", "key")
HISTORIES: tuple[str, ...] = ("reliable", "occasional", "chronic")
TOUCHES: tuple[str, ...] = ("first", "followup")

OPEN_STATES = {"NEW", "CONTACTED"}
TERMINAL_STATES = {"PAID", "PLAN_AGREED", "ESCALATED", "QUARANTINED", "EXHAUSTED"}
TRANSITIONS: dict[str, set[str]] = {
    "NEW": {"CONTACTED", "AWAITING_APPROVAL"} | TERMINAL_STATES,
    "CONTACTED": {"CONTACTED", "AWAITING_APPROVAL"} | TERMINAL_STATES,
    "AWAITING_APPROVAL": {"NEW", "CONTACTED"} | TERMINAL_STATES,
    **{s: set() for s in TERMINAL_STATES},
}

PAY_LINK = "https://pay.example.com/{invoice_id}"


class Decision(BaseModel):
    """One decision for one invoice. Unknown extra fields are ignored; types are strict."""

    model_config = ConfigDict(extra="ignore")

    invoice_id: str = Field(min_length=1, max_length=40)
    action: Action
    tone: Tone = "neutral"
    include_payment_link: bool = False
    mention_due_date: bool = False
    installments: int | None = Field(default=None, ge=1, le=24)
    message: str = Field(default="", max_length=2000)
    rationale: str = Field(default="", max_length=600)

    @field_validator("tone", "include_payment_link", "mention_due_date", "message", "rationale", mode="before")
    @classmethod
    def _null_means_default(cls, value, info):
        """LLMs often send null for fields that don't apply (e.g. tone on an escalation): treat as 'not set'."""
        if value is None:
            return {"tone": "neutral", "include_payment_link": False, "mention_due_date": False}.get(info.field_name, "")
        return value


def history_bucket(late_payments_12m: int) -> str:
    if late_payments_12m <= 1:
        return "reliable"
    if late_payments_12m >= 4:
        return "chronic"
    return "occasional"


LANGUAGES: tuple[str, ...] = ("ar", "en")
CURRENCY_MARKERS = ("EGP", "ج.م", "جنيه")


def amount_number(cents: int) -> str:
    """The digits every customer message must contain, e.g. '12,450.00' (Western digits in both languages)."""
    return f"{cents / 100:,.2f}"


def money(cents: int, lang: str = "en") -> str:
    """Display amount in Egyptian pounds: 'EGP 12,450.00' or '12,450.00 ج.م'."""
    return f"{amount_number(cents)} ج.م" if lang == "ar" else f"EGP {amount_number(cents)}"
