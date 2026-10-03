"""Self-improvement loop: experience -> report -> reflect (propose skill) -> eval gate -> human promotes.

The agent proposes; deterministic evals decide whether the proposal is better; a human flips the switch.
"""

from __future__ import annotations

import json
import sqlite3
import time
from collections import defaultdict

from . import db, skills
from .brains import BrainError
from .brains.base import BrainContext
from .config import Settings, get_settings
from .engine import Engine
from .evals import run_golden
from .llm import BudgetExceeded, KillSwitchOn, LLMError
from .models import HISTORIES, TIERS, TOUCHES
from .observability import emit, new_trace_id

CONTACT = {"send_reminder", "offer_payment_plan"}
_SIGNAL_GROUPS = ["paid_claim", "dispute", "opt_out", "angry", "cash_flow", "reply"]


def _score(total: float, n: int) -> float:
    """Shrunk mean (prior mean 0, weight 1): rewards evidence, distrusts tiny samples."""
    return total / (n + 1)


def _style_stats(rows: list[dict]) -> dict:
    styles: dict = {}
    for field, key in (("tone", "tone"), ("include_payment_link", "link"), ("mention_due_date", "due")):
        buckets: dict = defaultdict(list)
        for r in rows:
            value = r[key] if field == "tone" else bool(r[key])
            buckets[value].append(r["reward"])
        styles[field] = {str(k).lower(): {"n": len(v), "mean_reward": round(sum(v) / len(v), 3),
                                          "score": round(_score(sum(v), len(v)), 3)} for k, v in buckets.items()}
    return styles


def _summarize(rows: list[dict]) -> dict:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        grouped[r["action"]].append(r)
    actions: dict[str, dict] = {}
    for action, subset in grouped.items():
        rewards = [r["reward"] for r in subset]
        entry = {"n": len(rewards), "mean_reward": round(sum(rewards) / len(rewards), 3),
                 "score": round(_score(sum(rewards), len(rewards)), 3)}
        if action in CONTACT:
            # Judge a contact action by its best observed tone, not by the average of good and bad tones.
            entry["styles"] = _style_stats(subset)
            entry["score"] = max([entry["score"]] + [v["score"] for v in entry["styles"]["tone"].values()])
        actions[action] = entry
    best = max(actions, key=lambda a: actions[a]["score"]) if actions else None
    styles = actions[best].get("styles", {}) if best else {}
    return {"n": len(rows), "actions": actions, "best_action": best, "styles": styles}


def _do_from(summary: dict, settings: Settings) -> dict:
    action = summary["best_action"]
    do: dict = {"action": action}
    if action in CONTACT:
        def pick(field, default):
            options = summary["styles"].get(field) or {}
            return max(options, key=lambda k: options[k]["score"]) if options else default
        do["tone"] = pick("tone", "neutral")
        do["include_payment_link"] = pick("include_payment_link", "true") == "true"
        do["mention_due_date"] = pick("mention_due_date", "false") == "true"
        if action == "offer_payment_plan":
            do["installments"] = min(3, settings.max_installments)
    return do


def _lesson(when: dict, summary: dict) -> str:
    acts = sorted(summary["actions"].items(), key=lambda kv: -kv[1]["score"])
    best = acts[0]
    text = f"when {when or 'anything else'}: `{best[0]}` (mean reward {best[1]['mean_reward']}, n={best[1]['n']})"
    if len(acts) > 1:
        text += f" beats `{acts[1][0]}` ({acts[1][1]['mean_reward']}, n={acts[1][1]['n']})"
    return text


def build_report(conn: sqlite3.Connection, settings: Settings | None = None, max_runs: int = 20) -> dict:
    """Aggregate experience from training/live runs into per-situation evidence + a suggested playbook."""
    settings = settings or get_settings()
    run_ids = [r["id"] for r in conn.execute(
        "SELECT id FROM runs WHERE kind IN ('train','live') ORDER BY started_at DESC LIMIT ?", (max_runs,))]
    if not run_ids:
        return {"runs_used": [], "n_outcomes": 0, "groups": [], "suggested_playbook": {}}
    marks = ",".join("?" * len(run_ids))
    rows = db.rows(conn.execute(f"SELECT * FROM outcomes WHERE run_id IN ({marks})", run_ids))

    candidates: list[tuple[dict, list[dict], int]] = []  # (when, rows, min_n)
    for sig in _SIGNAL_GROUPS:
        candidates.append(({"signal": sig}, [r for r in rows if r["signal"] == sig], 2))
    for tier in TIERS:
        for hist in HISTORIES:
            for touch in TOUCHES:
                when = {"signal": "none", "tier": tier, "history": hist, "touch": touch}
                candidates.append((when, [r for r in rows if r["signal"] == "none" and r["tier"] == tier
                                          and r["history"] == hist and r["touch"] == touch], 4))
    for tier in TIERS:
        for touch in TOUCHES:
            when = {"signal": "none", "tier": tier, "touch": touch}
            candidates.append((when, [r for r in rows if r["signal"] == "none" and r["tier"] == tier
                                      and r["touch"] == touch], 4))
    candidates.append(({}, rows, 1))

    groups, rules, lessons = [], [], []
    general_do: dict[tuple, dict] = {}
    # Compute every group's best "do" first so specific rules that add nothing can be skipped.
    for when, subset, min_n in candidates:
        if len(subset) < min_n:
            continue
        summary = _summarize(subset)
        if summary["best_action"] is None:
            continue
        general_do[tuple(sorted(when.items()))] = _do_from(summary, settings)
    for when, subset, min_n in candidates:
        if len(subset) < min_n:
            continue
        summary = _summarize(subset)
        if summary["best_action"] is None:
            continue
        do = general_do[tuple(sorted(when.items()))]
        groups.append({"when": when, **summary})
        parent = None
        if "history" in when:
            parent = general_do.get(tuple(sorted({"signal": "none", "tier": when["tier"], "touch": when["touch"]}.items())))
        elif "tier" in when:
            parent = general_do.get(())
        if parent is not None and parent == do:
            continue  # the broader rule already says the same thing
        rules.append({"when": when, "do": do})
        lessons.append(_lesson(when, summary))

    blocks = defaultdict(int)
    for r in rows:
        if r["result"].startswith("blocked:"):
            blocks[r["result"].split(":", 1)[1]] += 1
    per_version = db.rows(conn.execute(
        f"SELECT skill_version, COUNT(*) n, ROUND(AVG(reward),3) mean_reward FROM outcomes "
        f"WHERE run_id IN ({marks}) GROUP BY skill_version", run_ids))
    return {
        "runs_used": run_ids,
        "n_outcomes": len(rows),
        "reward_meaning": "1.0 paid / correctly resolved, 0.85 payment plan, 0 no effect, -0.3 opt-out or "
                          "human rejection, -0.5 guardrail block, -1.0 complaint",
        "groups": groups,
        "guardrail_blocks_by_code": dict(blocks),
        "per_skill_version": per_version,
        "suggested_playbook": {"rules": rules, "lessons": lessons} if rules else {},
    }


def reflect(conn: sqlite3.Connection, engine: Engine) -> dict:
    """Ask the brain to propose a new skill version from evidence. Returns {'version': n} or {'error': ...}."""
    current = skills.active(conn)
    report = build_report(conn, engine.settings)
    if report["n_outcomes"] == 0:
        return {"error": "no experience yet: run a training episode first"}
    ctx = BrainContext(run_id=f"reflect-{int(time.time())}", round=0, trace_id=new_trace_id())
    try:
        content = engine.brain.reflect(report, current["content"], ctx)
    except (BrainError, LLMError, BudgetExceeded, KillSwitchOn, ValueError) as exc:
        emit(conn, "reflect_failed", level="error", engine=engine.brain.name, error=str(exc)[:400])
        if engine.brain.name == "offline":
            return {"error": str(exc)}
        emit(conn, "degraded_mode", level="warn", detail="reflection fell back to the offline statistical learner")
        from .brains.offline import OfflineBrain
        content = OfflineBrain().reflect(report, current["content"], ctx)
    try:
        version = skills.create_candidate(conn, content, parent=current["version"], author=engine.brain.name,
                                          notes=f"reflected from {report['n_outcomes']} outcomes")
    except skills.SkillRejected as exc:
        emit(conn, "skill_rejected_static", level="warn", error=str(exc))
        return {"error": f"proposed skill failed static validation: {exc}"}
    emit(conn, "skill_proposed", version=version, parent=current["version"], author=engine.brain.name)
    return {"version": version, "parent": current["version"]}


def evaluate(conn: sqlite3.Connection, engine: Engine, version: int) -> dict:
    """Holdout episodes (no exploration) + golden safety cases for one skill version."""
    runs = []
    for seed in engine.settings.eval_seeds:
        run = engine.run_episode(kind="eval", seed=seed, explore=0.0, skill_version=version)
        if run["status"] != "completed":
            return {"version": version, "error": f"eval run {run['id']} ended {run['status']}: {run.get('error')}"}
        runs.append(run)
    keys = ("collection_rate", "correct_resolution_rate", "reward_per_invoice", "guardrail_blocks", "complaints")
    avg = {k: round(sum(r["metrics"][k] for r in runs) / len(runs), 4) for k in keys}
    golden = run_golden(conn, engine, version)
    return {"version": version, "engine": engine.brain.name, "seeds": list(engine.settings.eval_seeds),
            "runs": [r["id"] for r in runs], **avg, "golden": golden}


def gate(conn: sqlite3.Connection, engine: Engine, candidate: int) -> dict:
    """Promotion gate. Candidate must pass every golden case and beat the active version on holdout reward."""
    active = skills.active(conn)
    cached = json.loads(active["eval"]) if active["eval"] else None
    if cached and "candidate_eval" in cached:  # promoted versions store their gate record
        cached = cached["candidate_eval"]
    if (cached and cached.get("seeds") == list(engine.settings.eval_seeds)
            and cached.get("engine") == engine.brain.name and "error" not in cached):
        base = cached
    else:
        base = evaluate(conn, engine, active["version"])
        if "error" not in base:
            skills.set_status(conn, active["version"], "active", json.dumps(base))
    cand = evaluate(conn, engine, candidate)
    reasons = []
    if "error" in base or "error" in cand:
        reasons.append(base.get("error") or cand.get("error"))
    else:
        if cand["golden"]["passed"] < cand["golden"]["total"]:
            failed = [c["id"] for c in cand["golden"]["cases"] if not c["passed"]]
            reasons.append(f"golden safety cases failed: {failed}")
        delta = round(cand["reward_per_invoice"] - base["reward_per_invoice"], 4)
        if delta < engine.settings.promotion_margin:
            reasons.append(f"reward delta {delta:+.3f} < required margin {engine.settings.promotion_margin:+.3f}")
        if cand["collection_rate"] < base["collection_rate"] - 0.02:
            reasons.append(f"cash collected regressed ({cand['collection_rate']:.1%} < {base['collection_rate']:.1%})")
        if cand["complaints"] > base["complaints"]:
            reasons.append(f"more complaints ({cand['complaints']} > {base['complaints']})")
    passed = not reasons
    result = {"candidate": candidate, "baseline": active["version"], "passed": passed, "reasons": reasons,
              "baseline_eval": base, "candidate_eval": cand, "checked_at": time.time()}
    skills.set_status(conn, candidate, "passed_gate" if passed else "rejected", json.dumps(result))
    emit(conn, "gate_result", level="info" if passed else "warn", candidate=candidate, baseline=active["version"],
         passed=passed, reasons=reasons)
    return result
