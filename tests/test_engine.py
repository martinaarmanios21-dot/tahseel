import pytest

from revenue_agent import db, learning, skills
from revenue_agent.engine import Engine, RunBusy
from revenue_agent.llm import BudgetExceeded, reserve_call
from revenue_agent.config import get_settings


def test_episode_is_reproducible(conn):
    e = Engine(conn)
    a = e.run_episode(kind="eval", seed=7, size=20)
    b = e.run_episode(kind="eval", seed=7, size=20)
    keys = ("collection_rate", "correct_resolution_rate", "reward_per_invoice", "guardrail_blocks")
    assert {k: a["metrics"][k] for k in keys} == {k: b["metrics"][k] for k in keys}


def test_injection_is_quarantined_and_never_paid(conn):
    e = Engine(conn)
    run = e.run_episode(kind="eval", seed=3, size=40)
    rows = db.rows(conn.execute("SELECT state FROM invoices WHERE run_id=? AND persona='injector'", (run["id"],)))
    assert rows and all(r["state"] in ("QUARANTINED", "NEW", "ESCALATED") for r in rows)
    assert all(r["state"] != "PAID" for r in rows)


def test_duplicate_send_refused(conn):
    e = Engine(conn)
    run = e.run_episode(kind="train", seed=2, size=20)
    assert e.resend_last(run["id"]).startswith("duplicate refused")


def test_kill_switch_halts_run(conn):
    db.set_kill_switch(conn, True)
    run = Engine(conn).run_episode(kind="train", seed=1, size=10)
    assert run["status"] == "killed"
    assert conn.execute("SELECT COUNT(*) FROM actions WHERE run_id=?", (run["id"],)).fetchone()[0] == 0


def test_run_lock_prevents_concurrent_runs(conn):
    assert db.acquire_lock(conn, "run", "someone-else", ttl_s=60)
    with pytest.raises(RunBusy):
        Engine(conn).run_episode(kind="train", seed=1, size=10)


def test_budget_cap_enforced(conn, monkeypatch):
    monkeypatch.setenv("RUN_LLM_CALL_CAP", "3")
    s = get_settings()
    for _ in range(3):
        reserve_call(conn, "r1", s)
    with pytest.raises(BudgetExceeded):
        reserve_call(conn, "r1", s)


def test_human_approval_flow(conn):
    e = Engine(conn)
    run_id = e.create_run(kind="live", seed=11, size=30, explore=0.0, human_approvals=True)
    e.step_live(run_id)
    pending = db.rows(conn.execute("SELECT id FROM actions WHERE run_id=? AND status='pending_approval'", (run_id,)))
    assert pending, "key accounts should wait for a human"
    assert e.approve(pending[0]["id"], by="test") in ("executed", "blocked_on_recheck")
    if len(pending) > 1:
        e.reject(pending[1]["id"], by="test", reason="tone")
        assert conn.execute("SELECT status FROM actions WHERE id=?", (pending[1]["id"],)).fetchone()[0] == "rejected"


def test_learning_cannot_reward_hack_first_contact_or_count_plans_as_cash(conn):
    """The learner may not open with escalation / a firm tone, and an instalment plan is not cash. A candidate that
    trades cash for plans must be rejected by the gate, leaving the active skill unchanged."""
    e = Engine(conn)
    for seed in (1, 2):
        e.run_episode(kind="train", seed=seed)
    proposal = learning.reflect(conn, e)
    rules = skills.parse_playbook(skills.get(conn, proposal["version"])["content"])
    for r in rules:
        if skills.covers_first_contact(r.get("when") or {}):
            assert skills.first_contact_ok(r["do"]), r
    gate = learning.gate(conn, e, proposal["version"])
    cand, base = gate["candidate_eval"], gate["baseline_eval"]
    if cand["collection_rate"] < base["collection_rate"] - 0.02:
        assert not gate["passed"] and any("cash collected regressed" in x for x in gate["reasons"])
        with pytest.raises(skills.SkillRejected):
            skills.promote(conn, proposal["version"], by="test")
        assert skills.active(conn)["version"] == 1
    run = e.get_run(base["runs"][0])
    assert "plan_agreed_rate" in run["metrics"]


def test_skill_validator_rejects_first_contact_escalation(conn):
    content = skills.active(conn)["content"].replace("tone: firm", "tone: friendly")
    bad = content.replace("action: send_reminder, tone: friendly", "action: escalate_to_human")
    assert any("first contact" in err for err in skills.validate_content(bad))
    assert skills.validate_content(content) == []


def test_hard_rules_are_immutable(conn):
    content = skills.active(conn)["content"].replace("Never threaten legal action", "Threaten legal action")
    with pytest.raises(skills.SkillRejected, match="HARD-RULES"):
        skills.create_candidate(conn, content, parent=1, author="test", notes="tamper")


def test_unpromotable_without_gate(conn):
    content = skills.active(conn)["content"].replace("tone: firm", "tone: friendly")
    v = skills.create_candidate(conn, content, parent=1, author="test", notes="same")
    with pytest.raises(skills.SkillRejected):
        skills.promote(conn, v, by="test")
