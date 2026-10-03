"""Golden safety/behaviour cases: fixed situations with known-correct behaviour, replayed on every skill version."""

from __future__ import annotations

import json
import sqlite3
import time
from typing import TYPE_CHECKING

from pydantic import ValidationError

from . import skills
from .brains.base import BrainContext, agent_view
from .config import ROOT
from .guardrails import classify_reply, precheck
from .models import Decision
from .observability import new_trace_id

if TYPE_CHECKING:
    from .engine import Engine

GOLDEN_PATH = ROOT / "evals" / "golden_cases.json"


def load_cases() -> list[dict]:
    return json.loads(GOLDEN_PATH.read_text())


def _invoice(case: dict) -> dict:
    inv = {
        "run_id": "golden", "contact_name": "Sam", "contact_email": "ap@golden.example", "segment": "golden",
        "due_date": "2026-08-20", "days_overdue": 44, "persona": "golden", "state": "CONTACTED", "version": 0,
        "language": "en", "business": "nile-supplies",
        **case["invoice"],
    }
    if inv["touches"] == 0:
        inv["state"] = "NEW"
    inv["reply_signal"] = classify_reply(inv.get("last_reply"))
    return inv


def run_golden(conn: sqlite3.Connection, engine: "Engine", version: int) -> dict:
    cases = load_cases()
    content = skills.get(conn, version)["content"]
    results: list[dict] = []
    brain_cases = []
    for case in cases:
        inv = _invoice(case)
        if "classifier" in case["expect"]:
            got = inv["reply_signal"]
            ok = got == case["expect"]["classifier"]
            results.append({"id": case["id"], "passed": ok, "detail": f"classifier={got}"})
        else:
            brain_cases.append((case, inv))

    decisions: dict[str, dict] = {}
    if brain_cases:
        ctx = BrainContext(run_id=f"golden-v{version}-{int(time.time())}", round=2, trace_id=new_trace_id())
        views = [agent_view(inv) for _, inv in brain_cases]
        result = engine._decide(views, content, ctx)
        for d in result.decisions:
            if isinstance(d, dict) and isinstance(d.get("invoice_id"), str):
                decisions.setdefault(d["invoice_id"], d)

    others = [inv["customer"] for _, inv in brain_cases]
    for case, inv in brain_cases:
        exp = case["expect"]
        raw = decisions.get(inv["id"])
        problems: list[str] = []
        if raw is None:
            problems.append("no decision returned")
        else:
            try:
                d = Decision.model_validate(raw)
            except ValidationError as exc:
                problems.append(f"schema invalid: {exc.errors()[0]['msg']}")
                d = None
            if d is not None:
                if "action_in" in exp and d.action not in exp["action_in"]:
                    problems.append(f"action {d.action} not in {exp['action_in']}")
                if "tone_not_in" in exp and d.action in {"send_reminder", "offer_payment_plan"} and d.tone in exp["tone_not_in"]:
                    problems.append(f"tone {d.tone} not allowed")
                if "max_installments" in exp and d.action == "offer_payment_plan" and (d.installments or 0) > exp["max_installments"]:
                    problems.append(f"installments {d.installments} > {exp['max_installments']}")
                verdict = precheck(inv, d, rnd=case["round"], is_ledger_paid=False, other_customers=others,
                                   settings=engine.settings)
                if verdict.status in exp.get("verdict_not", []):
                    problems.append(f"guardrail {verdict.status}: {verdict.code} ({verdict.reason[:120]})")
        results.append({"id": case["id"], "passed": not problems,
                        "detail": "; ".join(problems) if problems else f"ok ({raw.get('action')})"})
    order = {c["id"]: i for i, c in enumerate(cases)}
    results.sort(key=lambda r: order[r["id"]])
    return {"passed": sum(r["passed"] for r in results), "total": len(results), "cases": results}
