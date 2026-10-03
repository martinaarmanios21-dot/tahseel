"""Hermes brain: Hermes Agent runs headless (`hermes -z`) with the ar-collections skill preloaded and talks
to this project only through the `revenue_agent` MCP server (see mcp_server.py).

Hermes auto-approves tool calls in one-shot mode, which is exactly why every tool it can reach is
guardrailed server-side. Hermes can propose decisions and skill edits; it cannot execute or promote them.
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import tempfile
import time
from pathlib import Path

from .. import db
from ..config import ROOT, Settings
from ..llm import KillSwitchOn, record_tokens, reserve_call
from ..observability import emit
from .base import BrainContext, BrainError, BrainResult

DECIDE_PROMPT = """You are the accounts-receivable agent. Use the ar-collections skill.
Round {round} of run {run_id}.
1. Call the revenue_agent MCP tool `get_open_invoices` (no arguments needed).
2. Decide one action for EVERY invoice by applying the skill's playbook and hard rules.
3. Call `submit_decisions` once with all decisions. If some come back with status "block" and code
   "invalid_message", fix those messages and call `submit_decisions` again for just those invoices.
4. Reply with the single word DONE. Do not use any tools other than the revenue_agent ones."""

REFLECT_PROMPT = """You are improving your own ar-collections skill from evidence.
1. Call the revenue_agent MCP tool `get_learning_report` and `get_active_skill`.
2. Write an improved COMPLETE SKILL.md: keep the HARD-RULES block byte-for-byte identical, rewrite the
   ```playbook block from the evidence (suggested_playbook is a statistical analyst's proposal; adopt it unless
   the evidence clearly supports better), and update "## Lessons learned" with numbers.
3. Call `propose_skill` with the full content and short notes. If it returns errors, fix them and call it again.
4. Reply with the single word DONE."""


class HermesBrain:
    name = "hermes"

    def __init__(self, conn: sqlite3.Connection, settings: Settings):
        self.conn = conn
        self.settings = settings
        if not shutil.which(settings.hermes_bin):
            raise BrainError(f"Hermes binary {settings.hermes_bin!r} not found on PATH")
        if not settings.hermes_model:
            # Never fall through to the user's Hermes default model: it may be a paid one.
            raise BrainError("HERMES_MODEL is not set; refusing to use Hermes' default (possibly paid) model. "
                             "Set HERMES_MODEL (and HERMES_PROVIDER) to a free model in .env")

    def _run(self, prompt: str, ctx: BrainContext, purpose: str) -> dict:
        if db.kill_switch_on(self.conn):
            raise KillSwitchOn("kill switch is on")
        reserve_call(self.conn, ctx.run_id, self.settings)
        usage_file = Path(tempfile.mkstemp(prefix="hermes-usage-", suffix=".json")[1])
        cmd = [self.settings.hermes_bin]
        if self.settings.hermes_profile:
            cmd += ["-p", self.settings.hermes_profile]  # isolated profile pinned to a free model
        cmd += ["--skills", "ar-collections"]
        if self.settings.hermes_model:
            cmd += ["-m", self.settings.hermes_model]
        if self.settings.hermes_provider:
            cmd += ["--provider", self.settings.hermes_provider]
        cmd += ["--usage-file", str(usage_file), "-z", prompt]
        started = time.monotonic()
        try:
            env = {**os.environ, "GEMINI_API_KEY": self.settings.provider_key("gemini")}
            proc = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT, env=env,
                                  timeout=self.settings.hermes_timeout_s)
        except subprocess.TimeoutExpired as exc:
            emit(self.conn, "hermes_timeout", run_id=ctx.run_id, trace_id=ctx.trace_id, level="error", purpose=purpose)
            raise BrainError(f"Hermes timed out after {self.settings.hermes_timeout_s}s") from exc
        latency = round(time.monotonic() - started, 1)
        usage: dict = {}
        try:
            usage = json.loads(usage_file.read_text() or "{}")
        except (OSError, ValueError):
            pass
        finally:
            usage_file.unlink(missing_ok=True)
        tokens = _total_tokens(usage)
        record_tokens(self.conn, ctx.run_id, tokens, self.settings)
        emit(self.conn, "hermes_call", run_id=ctx.run_id, trace_id=ctx.trace_id, purpose=purpose,
             exit_code=proc.returncode, latency_s=latency, tokens=tokens, usage=usage,
             stdout_tail=proc.stdout[-400:], stderr_tail=proc.stderr[-400:])
        if proc.returncode != 0:
            raise BrainError(f"Hermes exited with {proc.returncode}: {proc.stderr[-300:]}")
        return {"tokens": tokens, "stdout": proc.stdout}

    def decide(self, views: list[dict], skill_content: str, ctx: BrainContext) -> BrainResult:
        with db.tx(self.conn):
            self.conn.execute("DELETE FROM proposals WHERE run_id=? AND round=?", (ctx.run_id, ctx.round))
            db.kv_set(self.conn, "hermes_task", {"run_id": ctx.run_id, "round": ctx.round})
        info = self._run(DECIDE_PROMPT.format(round=ctx.round, run_id=ctx.run_id), ctx, "decide")
        rows = db.rows(self.conn.execute(
            "SELECT payload FROM proposals WHERE run_id=? AND round=?", (ctx.run_id, ctx.round)))
        if not rows:
            raise BrainError("Hermes finished without submitting any decisions")
        return BrainResult(decisions=[json.loads(r["payload"]) for r in rows], engine=self.name,
                           llm_calls=1, tokens=info["tokens"])

    def reflect(self, report: dict, skill_content: str, ctx: BrainContext) -> str:
        with db.tx(self.conn):
            db.kv_set(self.conn, "hermes_proposal", None)
        self._run(REFLECT_PROMPT, ctx, "reflect")
        proposal = db.kv_get(self.conn, "hermes_proposal")
        if not proposal or not proposal.get("content"):
            raise BrainError("Hermes did not propose a valid skill")
        return proposal["content"]


def _total_tokens(usage: dict) -> int:
    for key in ("total_tokens", "tokens"):
        if isinstance(usage.get(key), (int, float)):
            return int(usage[key])
    parts = [usage.get(k) for k in ("input_tokens", "output_tokens", "prompt_tokens", "completion_tokens")]
    return int(sum(p for p in parts if isinstance(p, (int, float))))
