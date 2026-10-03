"""Command line: `uv run revenue-agent <command>`."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time

from . import db, learning, skills
from .config import ROOT, get_settings
from .engine import Engine, RunBusy
from .models import money
from .observability import emit

METRIC_ROWS = [
    ("Cash collected (holdout)", "collection_rate", "pct"),
    ("Correctly resolved", "correct_resolution_rate", "pct"),
    ("Reward per invoice", "reward_per_invoice", "num"),
    ("Guardrail blocks", "guardrail_blocks", "int"),
    ("Customer complaints", "complaints", "int"),
]


def _fmt(value, kind: str) -> str:
    if kind == "pct":
        return f"{value:.1%}"
    if kind == "int":
        return f"{value:.0f}"
    return f"{value:+.3f}"


def _print_run(run: dict) -> None:
    m = run["metrics"]
    print(f"  {run['id']:<22} v{run['skill_version']}  {run['status']:<10} collected {m['collection_rate']:.0%} "
          f"({money(m['collected_cents'])})  resolved {m['correct_resolution_rate']:.0%}  "
          f"blocks {m['guardrail_blocks']}  complaints {m['complaints']}  llm_calls {m['llm_calls']}")


def _print_gate(gate: dict) -> None:
    base, cand = gate["baseline_eval"], gate["candidate_eval"]
    if "error" in base or "error" in cand:
        print("  eval error:", base.get("error") or cand.get("error"))
        return
    print(f"\n  {'Metric':<28}{'v' + str(gate['baseline']) + ' (active)':>14}{'v' + str(gate['candidate']) + ' (candidate)':>18}")
    for label, key, kind in METRIC_ROWS:
        print(f"  {label:<28}{_fmt(base[key], kind):>14}{_fmt(cand[key], kind):>18}")
    print(f"  {'Golden safety cases':<28}{str(base['golden']['passed']) + '/' + str(base['golden']['total']):>14}"
          f"{str(cand['golden']['passed']) + '/' + str(cand['golden']['total']):>18}")
    verdict = "PASSED" if gate["passed"] else "REJECTED"
    print(f"\n  Gate: {verdict}" + ("" if gate["passed"] else f" -> {'; '.join(gate['reasons'])}"))


def cmd_demo(args) -> int:
    settings = get_settings()
    conn = db.connect()
    engine = Engine(conn, settings, args.engine)
    print(f"\n=== Revenue Agent demo  (engine: {engine.brain.name}, active skill v{skills.active(conn)['version']}) ===")
    print("\n[1] Training episodes: the agent works a simulated portfolio and explores safely")
    for seed in range(args.seed, args.seed + args.episodes):
        _print_run(engine.run_episode(kind="train", seed=seed))
    next_seed = args.seed + args.episodes
    for attempt in range(1, args.max_attempts + 1):
        print(f"\n[2] Reflection #{attempt}: the agent rewrites its own skill from the evidence")
        proposal = learning.reflect(conn, engine)
        if "error" in proposal:
            print("  reflection failed:", proposal["error"])
            return 1
        print(f"  proposed skill v{proposal['version']} (parent v{proposal['parent']})")
        print("\n[3] Eval gate: holdout portfolio + golden safety cases, candidate vs active")
        gate = learning.gate(conn, engine, proposal["version"])
        _print_gate(gate)
        if gate["passed"]:
            break
        print("\n  -> not promoted. Gathering more experience and trying again.")
        _print_run(engine.run_episode(kind="train", seed=next_seed))
        next_seed += 1
    else:
        print("\nNo candidate passed the gate; the active skill is unchanged (this is the safe outcome).")
        return 0

    v = gate["candidate"]
    if not args.yes:
        answer = input(f"\n[4] Human approval: promote skill v{v} to active? [y/N] ").strip().lower()
        if answer not in {"y", "yes"}:
            print("  Not promoted. Promote later with: uv run revenue-agent promote", v)
            return 0
    else:
        print(f"\n[4] Human approval: --yes given, promoting v{v}")
    skills.promote(conn, v, by="cli")
    print(f"  skill v{v} is now active" + (" and synced to Hermes" if skills.sync_to_hermes(skills.get(conn, v)["content"]) else ""))

    print("\n[5] Guardrail checks (these should all be refused)")
    last = db.one(conn.execute("SELECT id FROM runs WHERE kind='train' ORDER BY started_at DESC LIMIT 1"))
    print("  duplicate send   :", engine.resend_last(last["id"]))
    q = conn.execute("SELECT COUNT(*) FROM events WHERE kind='prompt_injection_quarantined'").fetchone()[0]
    print(f"  prompt injection : {q} malicious customer replies quarantined before any model saw them")
    db.set_kill_switch(conn, True)
    run = engine.run_episode(kind="train", seed=999, size=10)
    db.set_kill_switch(conn, False)
    print(f"  kill switch      : run {run['id']} -> status '{run['status']}' ({run['error']})")
    print("\nDiff of what the agent learned:  uv run revenue-agent diff", v)
    print("Dashboard:                       uv run revenue-agent serve  ->  http://127.0.0.1:8000\n")
    return 0


def cmd_train(args) -> int:
    conn = db.connect()
    engine = Engine(conn, engine_name=args.engine)
    for i in range(args.episodes):
        _print_run(engine.run_episode(kind="train", seed=args.seed + i, size=args.size))
    return 0


def cmd_learn(args) -> int:
    conn = db.connect()
    engine = Engine(conn, engine_name=args.engine)
    proposal = learning.reflect(conn, engine)
    if "error" in proposal:
        print("reflection failed:", proposal["error"])
        return 1
    print(f"proposed skill v{proposal['version']}")
    _print_gate(learning.gate(conn, engine, proposal["version"]))
    return 0


def cmd_promote(args) -> int:
    conn = db.connect()
    try:
        skills.promote(conn, args.version, by="cli", force=args.force)
    except skills.SkillRejected as exc:
        print("refused:", exc)
        return 1
    print(f"skill v{args.version} is active")
    return 0


def cmd_rollback(args) -> int:
    conn = db.connect()
    print(f"rolled back to v{skills.rollback(conn, by='cli')}")
    return 0


def cmd_diff(args) -> int:
    print(skills.diff(db.connect(), args.version, args.against) or "(no differences)")
    return 0


def cmd_eval(args) -> int:
    conn = db.connect()
    engine = Engine(conn, engine_name=args.engine)
    version = args.version or skills.active(conn)["version"]
    result = learning.evaluate(conn, engine, version)
    print(json.dumps({k: v for k, v in result.items() if k != "runs"}, indent=2))
    return 0


def cmd_status(args) -> int:
    conn = db.connect()
    s = get_settings()
    print(f"engine: {s.engine}   providers with keys: {s.available_providers() or 'none'}   "
          f"kill switch: {'ON' if db.kill_switch_on(conn) else 'off'}")
    for v in skills.list_versions(conn):
        print(f"  skill v{v['version']:<3} {v['status']:<12} by {v['author']:<8} {v['notes'] or ''}")
    for run in db.rows(conn.execute("SELECT id FROM runs ORDER BY started_at DESC LIMIT 8")):
        _print_run(Engine(conn).get_run(run["id"]))
    return 0


def cmd_kill(args) -> int:
    conn = db.connect()
    db.set_kill_switch(conn, args.state == "on")
    emit(conn, "kill_switch", level="warn", on=args.state == "on", by="cli")
    print(f"kill switch {args.state}")
    return 0


def cmd_reset(args) -> int:
    settings = get_settings()
    if not args.yes:
        print(f"This deletes all local demo data in {settings.data_dir}. Re-run with --yes to confirm.")
        return 1
    shutil.rmtree(settings.data_dir, ignore_errors=True)
    print("local data reset")
    return 0


def cmd_seed_demo(args) -> int:
    """Fill the app with a realistic state for demos/videos. Always uses the free, instant offline brain."""
    conn = db.connect()
    engine = Engine(conn, get_settings(), "offline")
    if conn.execute("SELECT COUNT(*) FROM runs WHERE kind='train'").fetchone()[0] == 0:
        print("1/3  the assistant practises on 2 training portfolios…")
        for seed in (1, 2):
            engine.run_episode(kind="train", seed=seed)
    else:
        print("1/3  practice runs already exist, skipping")
    waiting = conn.execute("SELECT version FROM skill_versions WHERE status='passed_gate'").fetchone()
    if waiting:
        print(f"2/3  improvement v{waiting[0]} is already waiting for approval, skipping")
    elif skills.active(conn)["version"] > 1:
        print(f"2/3  an improvement (v{skills.active(conn)['version']}) is already active, skipping")
    else:
        print("2/3  the assistant studies its results and tests an improvement…")
        proposal = learning.reflect(conn, engine)
        if "version" in proposal:
            gate = learning.gate(conn, engine, proposal["version"])
            print(f"     improvement v{proposal['version']}: {'PASSED, waiting for owner approval' if gate['passed'] else 'rejected'}")
    print("3/3  starting a new work day (first round done, emails waiting for approval)…")
    run_id = engine.create_run(kind="live", seed=int(time.time()) % 100_000, size=args.size, explore=0.0,
                               human_approvals=True)
    engine.step_live(run_id)
    pending = conn.execute("SELECT COUNT(*) FROM actions WHERE run_id=? AND status='pending_approval'", (run_id,)).fetchone()[0]
    print(f"\nDone: {args.size} customers in today's work day, {pending} emails waiting for approval.")
    print("Refresh the app in your browser.")
    return 0


def cmd_serve(args) -> int:
    import os
    import socket

    import uvicorn
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        if probe.connect_ex((args.host, args.port)) == 0:
            print(f"Port {args.port} is already used by another program.\n"
                  f"Run on a free port instead, e.g.:  uv run revenue-agent serve --port {args.port + 80}")
            return 1
    if args.engine:
        os.environ["ENGINE"] = args.engine  # the web app reads settings from the environment
    print(f"Brain: {args.engine or get_settings().engine}  (use --engine offline for instant, free demos)")
    print(f"Tahseel app:        http://{args.host}:{args.port}")
    print(f"Reviewer dashboard: http://{args.host}:{args.port}/judges")
    uvicorn.run("revenue_agent.web.app:app", host=args.host, port=args.port, log_level="warning")
    return 0


def cmd_hermes_setup(args) -> int:
    """Create an isolated Hermes profile pinned to free Gemini, install the skill, register the MCP server."""
    settings = get_settings()
    hermes = shutil.which(settings.hermes_bin)
    uv = shutil.which("uv")
    if not hermes:
        print("Hermes Agent not found. Install: https://github.com/NousResearch/hermes-agent")
        return 1
    if not settings.provider_key("gemini"):
        print("Set GEMINI_API_KEY in .env first (free key: https://aistudio.google.com/apikey).")
        return 1
    profile = settings.hermes_profile
    model = settings.hermes_model or "gemini-flash-latest"

    def run(cmd: list[str], stdin: str | None = None) -> subprocess.CompletedProcess:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=120, input=stdin)

    if not settings.hermes_profile_home.is_dir():
        print(f"creating isolated Hermes profile '{profile}' (your default profile is not touched)")
        run([hermes, "profile", "create", profile, "--no-skills", "--no-alias",
             "--description", "Tahseel AR collections agent (free Gemini only)"])
    # Pin the main provider explicitly: with no fallback declared, Hermes never bills side tasks elsewhere.
    for key, value in (("model.default", model), ("model.provider", "gemini"), ("model.base_url", "")):
        run([hermes, "-p", profile, "config", "set", key, value])
    env_path = settings.hermes_profile_home / ".env"
    lines = [l for l in (env_path.read_text().splitlines(keepends=True) if env_path.exists() else [])
             if not l.startswith("GEMINI_API_KEY=")]
    env_path.write_text("".join(lines) + f"GEMINI_API_KEY={settings.provider_key('gemini')}\n")
    env_path.chmod(0o600)
    conn = db.connect()
    print(f"skill installed: {skills.sync_to_hermes(skills.active(conn)['content'])}")
    cmd = [hermes, "-p", profile, "mcp", "add", "revenue_agent", "--command", uv or "uv",
           "--args", "run", "--directory", str(ROOT), "python", "-m", "revenue_agent.mcp_server"]
    proc = run(cmd, stdin="y\ny\n")
    print("MCP server:", "registered" if proc.returncode == 0 else proc.stdout[-800:] + proc.stderr[-800:])
    print(f"\nProfile '{profile}' uses {model} via the free gemini provider.")
    print(f"Test:  hermes -p {profile} mcp test revenue_agent")
    print("Run:   uv run revenue-agent --engine hermes demo")
    return proc.returncode


def cmd_doctor(args) -> int:
    s = get_settings()
    checks = [
        ("python", sys.version.split()[0]),
        ("engine", s.engine),
        ("LLM providers with keys", ", ".join(s.available_providers()) or "none (offline mode works without keys)"),
        ("hermes binary", shutil.which(s.hermes_bin) or "not found (only needed for ENGINE=hermes)"),
        ("data dir", str(s.data_dir)),
        ("limits", f"{s.run_llm_call_cap} LLM calls/run, {s.daily_llm_call_cap}/day, {s.run_token_cap} tokens/run"),
    ]
    for name, value in checks:
        print(f"  {name:<26} {value}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="revenue-agent", description="Self-improving, failure-first AR collections agent")
    p.add_argument("--engine", choices=["offline", "api", "hermes"], default=None,
                   help="brain to use (default: ENGINE env / auto)")
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("demo", help="full loop: train -> reflect -> gate -> promote -> guardrail checks")
    d.add_argument("--episodes", type=int, default=2)
    d.add_argument("--seed", type=int, default=1)
    d.add_argument("--max-attempts", type=int, default=3)
    d.add_argument("--yes", action="store_true", help="auto-approve promotion (non-interactive)")
    d.set_defaults(func=cmd_demo)

    t = sub.add_parser("train", help="run training episodes")
    t.add_argument("--episodes", type=int, default=1)
    t.add_argument("--seed", type=int, default=int(time.time()) % 10_000)
    t.add_argument("--size", type=int, default=None)
    t.set_defaults(func=cmd_train)

    sub.add_parser("learn", help="reflect on experience and run the eval gate").set_defaults(func=cmd_learn)

    pr = sub.add_parser("promote", help="promote a skill version that passed the gate")
    pr.add_argument("version", type=int)
    pr.add_argument("--force", action="store_true", help="human override (skips gate status check)")
    pr.set_defaults(func=cmd_promote)

    sub.add_parser("rollback", help="re-activate the parent of the active skill").set_defaults(func=cmd_rollback)

    df = sub.add_parser("diff", help="show what changed in a skill version")
    df.add_argument("version", type=int)
    df.add_argument("--against", type=int, default=None)
    df.set_defaults(func=cmd_diff)

    ev = sub.add_parser("eval", help="evaluate a skill version (holdout + golden cases)")
    ev.add_argument("--version", type=int, default=None)
    ev.set_defaults(func=cmd_eval)

    sub.add_parser("status", help="skills, runs, kill switch").set_defaults(func=cmd_status)

    k = sub.add_parser("kill", help="emergency stop on/off")
    k.add_argument("state", choices=["on", "off"])
    k.set_defaults(func=cmd_kill)

    r = sub.add_parser("reset", help="delete local demo data")
    r.add_argument("--yes", action="store_true")
    r.set_defaults(func=cmd_reset)

    s = sub.add_parser("serve", help="start the web dashboard")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8000)
    s.set_defaults(func=cmd_serve)

    sd = sub.add_parser("seed-demo", help="fill the app with realistic demo data (offline, free, ~5 seconds)")
    sd.add_argument("--size", type=int, default=24)
    sd.set_defaults(func=cmd_seed_demo)

    sub.add_parser("hermes-setup", help="install the skill into Hermes and register the MCP server").set_defaults(
        func=cmd_hermes_setup)
    sub.add_parser("doctor", help="check configuration").set_defaults(func=cmd_doctor)

    args = p.parse_args(argv)
    try:
        return args.func(args)
    except RunBusy as exc:
        print("busy:", exc)
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
