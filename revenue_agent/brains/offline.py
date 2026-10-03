"""Offline brain: no API key needed.

`decide` executes the skill's playbook literally. `reflect` rewrites the playbook from outcome statistics
(a contextual-bandit style learner). It is deterministic, which makes it the reference implementation
for evals and the safety net when every LLM provider is down.
"""

from __future__ import annotations

from .. import skills
from .base import BrainContext, BrainResult, features, match_rule, render_message


class OfflineBrain:
    name = "offline"

    def decide(self, views: list[dict], skill_content: str, ctx: BrainContext) -> BrainResult:
        rules = skills.parse_playbook(skill_content)
        decisions = []
        for view in views:
            hit = match_rule(rules, features(view))
            if hit is None:
                decisions.append({"invoice_id": view["invoice_id"], "action": "wait", "rationale": "no rule matched"})
                continue
            idx, rule = hit
            do = dict(rule["do"])
            decision = {
                "invoice_id": view["invoice_id"],
                "action": do["action"],
                "tone": do.get("tone", "neutral"),
                "include_payment_link": bool(do.get("include_payment_link", False)),
                "mention_due_date": bool(do.get("mention_due_date", False)),
                "installments": do.get("installments") or (3 if do["action"] == "offer_payment_plan" else None),
                "rationale": f"playbook rule {idx}: when {rule.get('when') or {}}",
            }
            decision["message"] = render_message(view, decision)
            decisions.append(decision)
        return BrainResult(decisions=decisions, engine=self.name)

    def reflect(self, report: dict, skill_content: str, ctx: BrainContext) -> str:
        suggestion = report.get("suggested_playbook") or {}
        rules = suggestion.get("rules")
        if not rules:
            raise ValueError("not enough evidence to propose a new playbook")
        return skills.replace_playbook(skill_content, rules, suggestion.get("lessons") or ["(no lessons)"])
