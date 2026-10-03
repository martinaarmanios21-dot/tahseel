"""Orchestrator: runs rounds, routes every decision through the guardrails, executes via the outbox.

Design-for-failure properties enforced here:
- explicit state machine with optimistic versioning (no lost updates)
- per-invoice leases + a global run lock (no two workers touch the same item)
- idempotency keys on every side effect (duplicate sends are impossible)
- kill switch checked before every LLM call and every action
- budget exhaustion halts the run cleanly; brain failure degrades to the offline brain
"""

from __future__ import annotations

import json
import random
import sqlite3
import time
import uuid

from pydantic import ValidationError

from . import db, simulator, skills
from .brains import BrainError, make_brain
from .brains.base import BrainContext, BrainResult, agent_view, render_message
from .brains.offline import OfflineBrain
from .config import Settings, get_settings
from .guardrails import Verdict, classify_reply, idempotency_key, precheck
from .llm import BudgetExceeded, KillSwitchOn, LLMError
from .models import CONTACT_ACTIONS, OPEN_STATES, TONES, TRANSITIONS, Decision
from .observability import emit, new_trace_id

ROUNDS = 3
BLOCK_PENALTY = -0.5
REJECT_PENALTY = -0.3
LEASE_S = 120

_RESULT_STATE = {"paid": "PAID", "plan_agreed": "PLAN_AGREED", "verified_paid": "PAID", "escalated": "ESCALATED"}
_BLOCK_SIDE_EFFECT = {
    "ledger_paid": ("PAID", "reconciled_by_guardrail"),
    "open_dispute": ("ESCALATED", "auto_escalated_dispute"),
    "opted_out": ("ESCALATED", "opted_out"),
    "max_touches": ("EXHAUSTED", "max_touches"),
}


class RunHalted(RuntimeError):
    def __init__(self, status: str, reason: str):
        super().__init__(reason)
        self.status = status


class RunBusy(RuntimeError):
    pass


class ConcurrencyConflict(RuntimeError):
    pass


class Engine:
    def __init__(self, conn: sqlite3.Connection, settings: Settings | None = None, engine_name: str | None = None):
        self.conn = conn
        self.settings = settings or get_settings()
        self.engine_name = engine_name or self.settings.engine
        self._brain = None
        skills.ensure_seeded(conn)

    # ------------------------------------------------------------ brain

    @property
    def brain(self):
        if self._brain is None:
            try:
                self._brain = make_brain(self.engine_name, self.conn, self.settings)
            except BrainError as exc:
                emit(self.conn, "brain_unavailable", level="error", engine=self.engine_name, error=str(exc))
                self._brain = OfflineBrain()
        return self._brain

    def _decide(self, views: list[dict], skill_content: str, ctx: BrainContext) -> BrainResult:
        try:
            return self.brain.decide(views, skill_content, ctx)
        except BudgetExceeded as exc:
            raise RunHalted("halted_budget", str(exc)) from exc
        except KillSwitchOn as exc:
            raise RunHalted("killed", str(exc)) from exc
        except (BrainError, LLMError, ValueError) as exc:
            emit(self.conn, "brain_failed", run_id=ctx.run_id, trace_id=ctx.trace_id, level="error",
                 engine=self.brain.name, error=str(exc)[:500])
            if self.brain.name == "offline":
                raise RunHalted("failed", f"offline brain failed: {exc}") from exc
            emit(self.conn, "degraded_mode", run_id=ctx.run_id, trace_id=ctx.trace_id, level="warn",
                 detail="falling back to the deterministic offline brain for this round")
            result = OfflineBrain().decide(views, skill_content, ctx)
            result.engine = "offline-fallback"
            return result

    # ------------------------------------------------------------ runs

    def create_run(self, *, kind: str, seed: int, size: int, explore: float, human_approvals: bool,
                   skill_version: int | None = None) -> str:
        version = skill_version or skills.active(self.conn)["version"]
        run_id = f"{kind}-{seed}-{uuid.uuid4().hex[:6]}"
        now = time.time()
        with db.tx(self.conn):
            self.conn.execute(
                "INSERT INTO runs(id, kind, seed, size, skill_version, engine, explore, human_approvals, status, started_at) "
                "VALUES(?,?,?,?,?,?,?,?, 'running', ?)",
                (run_id, kind, seed, size, version, self.engine_name, explore, int(human_approvals), now),
            )
            for inv in simulator.generate_portfolio(seed, size):
                self.conn.execute(
                    "INSERT INTO invoices(run_id, id, customer, contact_name, contact_email, language, business, segment, "
                    "tier, amount_cents, due_date, days_overdue, late_payments_12m, persona) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (run_id, inv["id"], inv["customer"], inv["contact_name"], inv["contact_email"], inv["language"],
                     inv["business"], inv["segment"],
                     inv["tier"], inv["amount_cents"], inv["due_date"], inv["days_overdue"], inv["late_payments_12m"],
                     inv["persona"]),
                )
            emit(self.conn, "run_started", run_id=run_id, kind=kind, seed=seed, size=size,
                 skill_version=version, engine=self.engine_name, explore=explore)
        return run_id

    def run_episode(self, *, kind: str = "train", seed: int = 1, size: int | None = None, explore: float | None = None,
                    rounds: int = ROUNDS, skill_version: int | None = None, human_approvals: bool = False) -> dict:
        size = size or (self.settings.eval_size if kind == "eval" else self.settings.train_size)
        explore = (0.0 if kind == "eval" else self.settings.explore_rate) if explore is None else explore
        owner = uuid.uuid4().hex
        if not db.acquire_lock(self.conn, "run", owner, ttl_s=1800):
            raise RunBusy("another run is in progress")
        run_id = None
        try:
            run_id = self.create_run(kind=kind, seed=seed, size=size, explore=explore,
                                     human_approvals=human_approvals, skill_version=skill_version)
            for rnd in range(1, rounds + 1):
                self.run_round(run_id, rnd)
            self.finish(run_id, "completed")
        except RunHalted as halt:
            self.finish(run_id, halt.status, str(halt))
        except Exception as exc:
            if run_id:
                self.finish(run_id, "failed", f"{type(exc).__name__}: {exc}")
            raise
        finally:
            db.release_lock(self.conn, "run", owner)
        return self.get_run(run_id)

    def step_live(self, run_id: str, rounds: int = ROUNDS) -> dict:
        """Advance an interactive (human-approval) run by one round."""
        run = self.get_run(run_id)
        if run["status"] != "running":
            return run
        owner = uuid.uuid4().hex
        if not db.acquire_lock(self.conn, "run", owner, ttl_s=900):
            raise RunBusy("another run is in progress")
        try:
            rnd = run["round"] + 1
            self.run_round(run_id, rnd)
            open_left = self.conn.execute(
                "SELECT COUNT(*) FROM invoices WHERE run_id=? AND state IN ('NEW','CONTACTED','AWAITING_APPROVAL')",
                (run_id,)).fetchone()[0]
            if rnd >= rounds or open_left == 0:
                self.finish(run_id, "completed")
        except RunHalted as halt:
            self.finish(run_id, halt.status, str(halt))
        finally:
            db.release_lock(self.conn, "run", owner)
        return self.get_run(run_id)

    def finish(self, run_id: str | None, status: str, error: str | None = None) -> None:
        if not run_id:
            return
        metrics = compute_metrics(self.conn, run_id)
        with db.tx(self.conn):
            self.conn.execute("UPDATE runs SET status=?, finished_at=?, metrics=?, error=? WHERE id=?",
                              (status, time.time(), json.dumps(metrics), error, run_id))
            self.conn.execute("UPDATE invoices SET lease_owner=NULL, lease_until=0 WHERE run_id=?", (run_id,))
            emit(self.conn, "run_finished", run_id=run_id, level="info" if status == "completed" else "warn",
                 status=status, error=error, metrics=metrics)

    def get_run(self, run_id: str) -> dict:
        run = db.one(self.conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)))
        if run is None:
            raise KeyError(run_id)
        run["metrics"] = json.loads(run["metrics"]) if run["metrics"] else compute_metrics(self.conn, run_id)
        return run

    # ------------------------------------------------------------ rounds

    def run_round(self, run_id: str, rnd: int) -> None:
        run = self.get_run(run_id)
        if db.kill_switch_on(self.conn):
            raise RunHalted("killed", "kill switch is on")
        with db.tx(self.conn):
            self.conn.execute("UPDATE runs SET round=? WHERE id=?", (rnd, run_id))
        open_invoices = db.rows(self.conn.execute(
            "SELECT * FROM invoices WHERE run_id=? AND state IN ('NEW','CONTACTED') ORDER BY id", (run_id,)))
        if not open_invoices:
            return
        trace_id = new_trace_id()
        views = [agent_view(inv) for inv in open_invoices]
        skill_content = skills.get(self.conn, run["skill_version"])["content"]
        ctx = BrainContext(run_id=run_id, round=rnd, trace_id=trace_id)
        result = self._decide(views, skill_content, ctx)
        emit(self.conn, "round_decided", run_id=run_id, trace_id=trace_id, round=rnd, engine=result.engine,
             open=len(open_invoices), decisions=len(result.decisions), llm_calls=result.llm_calls, tokens=result.tokens)

        by_id: dict[str, dict] = {}
        for d in result.decisions:
            if isinstance(d, dict) and isinstance(d.get("invoice_id"), str):
                by_id.setdefault(d["invoice_id"], d)
        known = {inv["id"] for inv in open_invoices}
        if set(by_id) - known:
            emit(self.conn, "unknown_invoice_ids", run_id=run_id, trace_id=trace_id, level="warn",
                 ids=sorted(set(by_id) - known)[:10])

        others = [r["customer"] for r in self.conn.execute("SELECT customer FROM invoices WHERE run_id=?", (run_id,))]
        rng = random.Random(f"explore:{run['seed']}:{rnd}")
        tried: dict[tuple, int] = {}
        for r in self.conn.execute(
                "SELECT signal, tier, action, tone, COUNT(*) n FROM outcomes WHERE run_kind IN ('train','live') "
                "GROUP BY signal, tier, action, tone"):
            arm = (r["signal"], r["tier"], r["action"], r["tone"] if r["action"] in CONTACT_ACTIONS else None)
            tried[arm] = tried.get(arm, 0) + r["n"]
        for inv, view in zip(open_invoices, views):
            raw = by_id.get(inv["id"]) or {"invoice_id": inv["id"], "action": "wait",
                                           "rationale": "brain returned no decision for this invoice"}
            explored = bool(run["explore"]) and rng.random() < self._explore_prob(run["explore"], view, tried)
            if explored:
                raw = self._explore_arm(view, rng, tried)
            self.process(run, inv["id"], raw, rnd, trace_id, explored, result.engine, others)

    @staticmethod
    def _explore_prob(base: float, view: dict, tried: dict[tuple, int]) -> float:
        """Uncertainty-driven: rarely-seen situations are explored much more than well-understood ones."""
        seen = sum(n for arm, n in tried.items() if arm[:2] == (view["signal"], view["tier"]))
        return max(base, 0.9 * 0.5 ** (seen / 8))

    def _explore_arm(self, view: dict, rng: random.Random, tried: dict[tuple, int]) -> dict:
        """Count-based exploration over (action, tone) arms: least-tried arms in this situation go first."""
        situation = (view["signal"], view["tier"])
        actions = ["send_reminder", "offer_payment_plan", "verify_payment", "escalate_to_human"]

        def count(action: str, tone: str | None = None) -> int:
            return sum(n for arm, n in tried.items() if arm[:3] == (*situation, action) and (tone is None or arm[3] == tone))

        action = rng.choices(actions, weights=[1.0 / (1 + count(a)) ** 2 for a in actions])[0]
        tone = None
        if action in CONTACT_ACTIONS:
            tone = rng.choices(TONES, weights=[1.0 / (1 + count(action, t)) ** 2 for t in TONES])[0]
        tried[(*situation, action, tone)] = tried.get((*situation, action, tone), 0) + 1
        d = {
            "invoice_id": view["invoice_id"],
            "action": action,
            "tone": tone or "neutral",
            "include_payment_link": rng.random() < 0.5,
            "mention_due_date": rng.random() < 0.5,
            "installments": min(3, self.settings.max_installments) if action == "offer_payment_plan" else None,
            "rationale": "exploration (bounded, policy-compliant variation)",
        }
        d["message"] = render_message(view, d)
        return d

    # ------------------------------------------------------------ per-invoice processing

    def process(self, run: dict, invoice_id: str, raw: dict, rnd: int, trace_id: str, explored: bool,
                engine: str, others: list[str]) -> str:
        if db.kill_switch_on(self.conn):
            raise RunHalted("killed", "kill switch is on")
        run_id = run["id"]
        owner = f"{run_id}:{rnd}:{uuid.uuid4().hex[:8]}"
        if not self._acquire_lease(run_id, invoice_id, owner):
            emit(self.conn, "lease_conflict", run_id=run_id, trace_id=trace_id, invoice_id=invoice_id, level="warn")
            return "lease_conflict"
        try:
            inv = self._invoice(run_id, invoice_id)
            if inv["state"] not in OPEN_STATES:
                return "not_open"
            view = agent_view(inv)
            try:
                decision = Decision.model_validate(raw)
            except ValidationError as exc:
                self._record_block(run, inv, view, raw, rnd, Verdict("block", "schema_invalid", str(exc)[:300]),
                                   trace_id, explored, engine)
                return "blocked"
            verdict = precheck(inv, decision, rnd=rnd, is_ledger_paid=simulator.ledger_paid(inv, rnd),
                               other_customers=others, settings=self.settings)
            if verdict.status == "block":
                self._record_block(run, inv, view, decision.model_dump(), rnd, verdict, trace_id, explored, engine)
                return "blocked"
            needs_human = verdict.status == "approve" and bool(run["human_approvals"])
            status = "pending_approval" if needs_human else "queued"
            decided_by = engine if verdict.status == "allow" else (None if needs_human else "sim-approver")
            action_id = self._insert_action(run, inv, decision, rnd, status, verdict, trace_id, explored, engine, decided_by)
            if action_id is None:
                emit(self.conn, "duplicate_blocked", run_id=run_id, trace_id=trace_id, invoice_id=invoice_id,
                     level="warn", action=decision.action, round=rnd)
                return "duplicate"
            if needs_human:
                with db.tx(self.conn):
                    self._transition(inv, "AWAITING_APPROVAL")
                    emit(self.conn, "approval_requested", run_id=run_id, trace_id=trace_id, invoice_id=invoice_id,
                         action_id=action_id, code=verdict.code, reason=verdict.reason)
                return "pending_approval"
            self._execute(run, inv, decision, action_id, rnd, trace_id, explored)
            return "executed"
        finally:
            self._release_lease(run_id, invoice_id, owner)

    def _execute(self, run: dict, inv: dict, decision: Decision, action_id: int, rnd: int, trace_id: str,
                 explored: bool) -> None:
        """Perform the side effect (simulated email/API), then commit state + outcome atomically."""
        d = decision.model_dump()
        resp = simulator.respond(inv, d, rnd, run["seed"])
        fields: dict = {}
        new_state = inv["state"]
        if decision.action in CONTACT_ACTIONS:
            fields["touches"] = inv["touches"] + 1
            fields["last_contact_round"] = rnd
            new_state = "CONTACTED"
        if resp.result in _RESULT_STATE:
            new_state = _RESULT_STATE[resp.result]
            fields["resolution"] = resp.result
        if resp.reply:
            signal = classify_reply(resp.reply)
            fields["last_reply"] = resp.reply
            fields["reply_signal"] = signal
            if signal == "injection" and new_state not in ("PAID", "PLAN_AGREED"):
                new_state = "QUARANTINED"
                fields["resolution"] = "prompt_injection_quarantined"
        view = agent_view(inv)
        with db.tx(self.conn):
            self.conn.execute("UPDATE actions SET status='sent', updated_at=? WHERE id=?", (time.time(), action_id))
            self._transition(inv, new_state, **fields)
            self._record_outcome(run, inv, view, d, rnd, resp.result, resp.reward, resp.collected_cents, explored)
            emit(self.conn, "action_executed", run_id=run["id"], trace_id=trace_id, invoice_id=inv["id"],
                 action=decision.action, tone=decision.tone, result=resp.result, reward=resp.reward,
                 new_state=new_state, explored=explored)
            if fields.get("reply_signal") == "injection":
                emit(self.conn, "prompt_injection_quarantined", run_id=run["id"], trace_id=trace_id,
                     invoice_id=inv["id"], level="warn", reply=resp.reply[:200])

    def _record_block(self, run: dict, inv: dict, view: dict, payload: dict, rnd: int, verdict: Verdict,
                      trace_id: str, explored: bool, engine: str) -> None:
        action = payload.get("action") if isinstance(payload.get("action"), str) else "invalid"
        now = time.time()
        with db.tx(self.conn):
            self.conn.execute(
                "INSERT INTO actions(run_id, invoice_id, round, idem_key, kind, payload, status, code, reason, "
                "skill_version, engine, explored, decided_by, trace_id, created_at, updated_at) "
                "VALUES(?,?,?,?,?,?, 'blocked', ?,?,?,?,?,?,?,?,?)",
                (run["id"], inv["id"], rnd, f"blocked:{uuid.uuid4().hex}", action, json.dumps(payload, default=str),
                 verdict.code, verdict.reason, run["skill_version"], engine, int(explored), "guardrails",
                 trace_id, now, now),
            )
            if verdict.code in _BLOCK_SIDE_EFFECT:
                state, resolution = _BLOCK_SIDE_EFFECT[verdict.code]
                self._transition(inv, state, resolution=resolution)
            self._record_outcome(run, inv, view, payload, rnd, f"blocked:{verdict.code}", BLOCK_PENALTY, 0, explored)
            emit(self.conn, "guardrail_block", run_id=run["id"], trace_id=trace_id, invoice_id=inv["id"],
                 level="warn", action=action, code=verdict.code, reason=verdict.reason)

    # ------------------------------------------------------------ human approvals

    def approve(self, action_id: int, by: str) -> str:
        act = db.one(self.conn.execute("SELECT * FROM actions WHERE id=?", (action_id,)))
        if not act or act["status"] != "pending_approval":
            raise ValueError(f"action {action_id} is not pending approval")
        run = self.get_run(act["run_id"])
        inv = self._invoice(act["run_id"], act["invoice_id"])
        decision = Decision.model_validate(json.loads(act["payload"]))
        restored = "CONTACTED" if inv["touches"] else "NEW"
        with db.tx(self.conn):
            self._transition(inv, restored)
        inv = self._invoice(act["run_id"], act["invoice_id"])
        others = [r["customer"] for r in self.conn.execute("SELECT customer FROM invoices WHERE run_id=?", (run["id"],))]
        # Re-check: the world may have changed while the action sat in the queue.
        verdict = precheck(inv, decision, rnd=act["round"], is_ledger_paid=simulator.ledger_paid(inv, run["round"]),
                           other_customers=others, settings=self.settings)
        if verdict.status == "block":
            with db.tx(self.conn):
                self.conn.execute("UPDATE actions SET status='blocked', code=?, reason=?, updated_at=? WHERE id=?",
                                  (verdict.code, f"re-check at approval: {verdict.reason}", time.time(), action_id))
                emit(self.conn, "guardrail_block", run_id=run["id"], invoice_id=inv["id"], level="warn",
                     code=verdict.code, reason="re-check at approval time")
            return "blocked_on_recheck"
        with db.tx(self.conn):
            self.conn.execute("UPDATE actions SET status='approved', decided_by=?, updated_at=? WHERE id=?",
                              (f"human:{by}", time.time(), action_id))
            emit(self.conn, "approval_granted", run_id=run["id"], invoice_id=inv["id"], action_id=action_id, by=by)
        self._execute(run, inv, decision, action_id, act["round"], act["trace_id"] or new_trace_id(), bool(act["explored"]))
        return "executed"

    def reject(self, action_id: int, by: str, reason: str = "") -> None:
        act = db.one(self.conn.execute("SELECT * FROM actions WHERE id=?", (action_id,)))
        if not act or act["status"] != "pending_approval":
            raise ValueError(f"action {action_id} is not pending approval")
        run = self.get_run(act["run_id"])
        inv = self._invoice(act["run_id"], act["invoice_id"])
        with db.tx(self.conn):
            self.conn.execute("UPDATE actions SET status='rejected', decided_by=?, reason=?, updated_at=? WHERE id=?",
                              (f"human:{by}", reason or "rejected by human", time.time(), action_id))
            self._transition(inv, "CONTACTED" if inv["touches"] else "NEW")
            self._record_outcome(run, inv, agent_view(inv), json.loads(act["payload"]), act["round"],
                                 "rejected_by_human", REJECT_PENALTY, 0, bool(act["explored"]))
            emit(self.conn, "approval_rejected", run_id=run["id"], invoice_id=inv["id"], action_id=action_id,
                 by=by, reason=reason)

    # ------------------------------------------------------------ helpers

    def _invoice(self, run_id: str, invoice_id: str) -> dict:
        inv = db.one(self.conn.execute("SELECT * FROM invoices WHERE run_id=? AND id=?", (run_id, invoice_id)))
        if inv is None:
            raise KeyError(invoice_id)
        return inv

    def _acquire_lease(self, run_id: str, invoice_id: str, owner: str) -> bool:
        now = time.time()
        with db.tx(self.conn):
            cur = self.conn.execute(
                "UPDATE invoices SET lease_owner=?, lease_until=? WHERE run_id=? AND id=? "
                "AND (lease_owner IS NULL OR lease_until < ?)",
                (owner, now + LEASE_S, run_id, invoice_id, now))
        return cur.rowcount == 1

    def _release_lease(self, run_id: str, invoice_id: str, owner: str) -> None:
        with db.tx(self.conn):
            self.conn.execute("UPDATE invoices SET lease_owner=NULL, lease_until=0 WHERE run_id=? AND id=? AND lease_owner=?",
                              (run_id, invoice_id, owner))

    def _transition(self, inv: dict, new_state: str, **fields) -> None:
        current = db.one(self.conn.execute("SELECT state, version FROM invoices WHERE run_id=? AND id=?",
                                           (inv["run_id"], inv["id"])))
        if new_state != current["state"] and new_state not in TRANSITIONS[current["state"]]:
            raise ValueError(f"illegal transition {current['state']} -> {new_state} for {inv['id']}")
        sets = ", ".join(f"{k}=?" for k in fields)
        sql = f"UPDATE invoices SET state=?, version=version+1{', ' + sets if sets else ''} WHERE run_id=? AND id=? AND version=?"
        cur = self.conn.execute(sql, (new_state, *fields.values(), inv["run_id"], inv["id"], current["version"]))
        if cur.rowcount != 1:
            raise ConcurrencyConflict(f"invoice {inv['id']} changed concurrently")

    def _insert_action(self, run: dict, inv: dict, decision: Decision, rnd: int, status: str, verdict: Verdict,
                       trace_id: str, explored: bool, engine: str, decided_by: str | None) -> int | None:
        key = idempotency_key(run["id"], inv["id"], rnd, decision.action)
        now = time.time()
        try:
            with db.tx(self.conn):
                cur = self.conn.execute(
                    "INSERT INTO actions(run_id, invoice_id, round, idem_key, kind, payload, status, code, reason, "
                    "skill_version, engine, explored, decided_by, trace_id, created_at, updated_at) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (run["id"], inv["id"], rnd, key, decision.action, decision.model_dump_json(), status, verdict.code,
                     verdict.reason, run["skill_version"], engine, int(explored), decided_by, trace_id, now, now),
                )
            return cur.lastrowid
        except sqlite3.IntegrityError:
            return None

    def _record_outcome(self, run: dict, inv: dict, view: dict, d: dict, rnd: int, result: str, reward: float,
                        collected: int, explored: bool) -> None:
        self.conn.execute(
            "INSERT INTO outcomes(run_id, run_kind, invoice_id, round, skill_version, signal, tier, history, touch, "
            "action, tone, link, due, installments, result, reward, collected_cents, explored, created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (run["id"], run["kind"], inv["id"], rnd, run["skill_version"], view["signal"], view["tier"],
             view["history"], view["touch"], str(d.get("action")), d.get("tone"),
             int(bool(d.get("include_payment_link"))), int(bool(d.get("mention_due_date"))), d.get("installments"),
             result, reward, collected, int(explored), time.time()),
        )

    # ------------------------------------------------------------ demo helpers

    def resend_last(self, run_id: str) -> str:
        """Replay the most recent sent action with the same idempotency key: must be refused."""
        act = db.one(self.conn.execute(
            "SELECT * FROM actions WHERE run_id=? AND status='sent' ORDER BY id DESC LIMIT 1", (run_id,)))
        if not act:
            return "no sent action to replay"
        try:
            with db.tx(self.conn):
                self.conn.execute(
                    "INSERT INTO actions(run_id, invoice_id, round, idem_key, kind, payload, status, skill_version, "
                    "engine, created_at, updated_at) VALUES(?,?,?,?,?,?, 'queued', ?, 'replay', ?, ?)",
                    (act["run_id"], act["invoice_id"], act["round"], act["idem_key"], act["kind"], act["payload"],
                     act["skill_version"], time.time(), time.time()))
        except sqlite3.IntegrityError:
            with db.tx(self.conn):
                emit(self.conn, "duplicate_blocked", run_id=run_id, invoice_id=act["invoice_id"], level="warn",
                     idem_key=act["idem_key"], detail="replayed send refused by idempotency key")
            return f"duplicate refused: {act['kind']} to {act['invoice_id']} (idem_key {act['idem_key'][:12]}…)"
        return "UNEXPECTED: duplicate accepted"


def compute_metrics(conn: sqlite3.Connection, run_id: str) -> dict:
    invoices = db.rows(conn.execute("SELECT * FROM invoices WHERE run_id=?", (run_id,)))
    if not invoices:
        return {}
    collectible = [i for i in invoices if i["persona"] in simulator.COLLECTIBLE]
    total_collectible = sum(i["amount_cents"] for i in collectible)
    collected = sum(i["amount_cents"] for i in collectible if i["state"] in ("PAID", "PLAN_AGREED"))
    outcome = conn.execute("SELECT COALESCE(SUM(reward),0), COUNT(*) FROM outcomes WHERE run_id=?", (run_id,)).fetchone()
    blocks = conn.execute("SELECT COUNT(*) FROM actions WHERE run_id=? AND status='blocked'", (run_id,)).fetchone()[0]
    complaints = conn.execute("SELECT COUNT(*) FROM outcomes WHERE run_id=? AND result='complaint'", (run_id,)).fetchone()[0]
    sends = conn.execute("SELECT COUNT(*) FROM actions WHERE run_id=? AND status='sent' AND kind IN "
                         "('send_reminder','offer_payment_plan')", (run_id,)).fetchone()[0]
    calls = conn.execute("SELECT used FROM budget WHERE key=?", (f"run:{run_id}:calls",)).fetchone()
    tokens = conn.execute("SELECT used FROM budget WHERE key=?", (f"run:{run_id}:tokens",)).fetchone()
    states: dict[str, int] = {}
    for i in invoices:
        states[i["state"]] = states.get(i["state"], 0) + 1
    return {
        "invoices": len(invoices),
        "collection_rate": round(collected / total_collectible, 4) if total_collectible else 0.0,
        "collected_cents": collected,
        "collectible_cents": total_collectible,
        "correct_resolution_rate": round(sum(simulator.correct_resolution(i) for i in invoices) / len(invoices), 4),
        "reward_per_invoice": round(outcome[0] / len(invoices), 4),
        "guardrail_blocks": blocks,
        "complaints": complaints,
        "emails_sent": sends,
        "human_escalations": states.get("ESCALATED", 0),
        "quarantined": states.get("QUARANTINED", 0),
        "llm_calls": int(calls[0]) if calls else 0,
        "tokens": int(tokens[0]) if tokens else 0,
        "states": states,
    }
