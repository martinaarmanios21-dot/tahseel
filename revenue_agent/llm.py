"""LLM client for free OpenAI-compatible providers.

Failure handling: timeouts, retries with exponential backoff + jitter, Retry-After on 429, provider
fallback chain, per-provider rate limiting, and hard per-run / per-day call and token budgets.
"""

from __future__ import annotations

import json
import random
import re
import sqlite3
import threading
import time
from dataclasses import dataclass
from datetime import date

import httpx

from . import db
from .config import PROVIDERS, Settings, get_settings
from .observability import emit


class BudgetExceeded(RuntimeError):
    pass


class KillSwitchOn(RuntimeError):
    pass


class LLMError(RuntimeError):
    pass


class DeadlineExceeded(LLMError):
    """The per-request wall-clock budget ran out (no further calls or sleeps are attempted)."""


@dataclass
class LLMResult:
    text: str
    provider: str
    model: str
    tokens_in: int
    tokens_out: int
    latency_s: float
    message: dict | None = None      # raw assistant message (needed to echo tool calls back)
    tool_calls: list | None = None


# ------------------------------------------------------------------ budgets

def _bump(conn: sqlite3.Connection, key: str, amount: float, cap: float) -> tuple[float, float]:
    with db.tx(conn):
        conn.execute("INSERT INTO budget(key, used, cap) VALUES(?, 0, ?) ON CONFLICT(key) DO UPDATE SET cap=excluded.cap",
                     (key, cap))
        used = conn.execute("SELECT used FROM budget WHERE key=?", (key,)).fetchone()[0]
        if amount > 0 and used + amount > cap:
            raise BudgetExceeded(f"budget '{key}' exhausted ({used:.0f}/{cap:.0f})")
        conn.execute("UPDATE budget SET used = used + ? WHERE key=?", (amount, key))
    return used + amount, cap


def reserve_call(conn: sqlite3.Connection, run_id: str | None, settings: Settings) -> None:
    """Reserve one LLM call against the daily and per-run caps *before* calling (fail closed)."""
    _bump(conn, f"day:{date.today().isoformat()}:calls", 1, settings.daily_llm_call_cap)
    if run_id:
        _bump(conn, f"run:{run_id}:calls", 1, settings.run_llm_call_cap)


def record_tokens(conn: sqlite3.Connection, run_id: str | None, tokens: int, settings: Settings) -> None:
    if run_id:
        # Recording never raises; the *next* reservation is what stops the run.
        with db.tx(conn):
            conn.execute("INSERT INTO budget(key, used, cap) VALUES(?, ?, ?) ON CONFLICT(key) DO UPDATE SET used = used + ?",
                         (f"run:{run_id}:tokens", tokens, settings.run_token_cap, tokens))


def check_token_budget(conn: sqlite3.Connection, run_id: str | None) -> None:
    if not run_id:
        return
    row = conn.execute("SELECT used, cap FROM budget WHERE key=?", (f"run:{run_id}:tokens",)).fetchone()
    if row and row["used"] >= row["cap"]:
        raise BudgetExceeded(f"token budget exhausted ({row['used']:.0f}/{row['cap']:.0f})")


# ------------------------------------------------------------------ rate limiting

_rate_lock = threading.Lock()
_last_call: dict[str, float] = {}


def _wait_for_slot(provider: str, rpm: int) -> None:
    interval = 60.0 / max(rpm, 1)
    with _rate_lock:
        now = time.monotonic()
        wait = _last_call.get(provider, 0.0) + interval - now
        _last_call[provider] = max(now, _last_call.get(provider, 0.0) + interval)
    if wait > 0:
        time.sleep(wait)


# ------------------------------------------------------------------ JSON helpers

def extract_json(text: str) -> dict:
    """Parse the first JSON object in a model response (tolerates ```json fences and chatter)."""
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    candidate = fenced.group(1) if fenced else text
    start, end = candidate.find("{"), candidate.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object in response")
    return json.loads(candidate[start : end + 1])


# ------------------------------------------------------------------ client

class LLMClient:
    def __init__(self, conn: sqlite3.Connection, settings: Settings | None = None, run_id: str | None = None):
        self.conn = conn
        self.settings = settings or get_settings()
        self.run_id = run_id
        self.calls = 0
        self.tokens = 0
        self.tokens_in = 0
        self.tokens_out = 0

    def chat(self, messages: list[dict], *, purpose: str, trace_id: str | None = None,
             max_tokens: int = 12000, temperature: float = 0.2, tools: list[dict] | None = None,
             deadline: float | None = None) -> LLMResult:
        """`deadline` is a time.monotonic() value: no attempt starts, and no backoff sleeps, past it."""
        providers = self.settings.available_providers()
        if not providers:
            raise LLMError("no LLM provider key configured (set GEMINI_API_KEY or OPENROUTER_API_KEY in .env)")
        last_error = "unknown"
        routes = [(p, m) for p in providers for m in self.settings.provider_models(p)]
        for provider, model in routes:
            spec = PROVIDERS[provider]
            for attempt in range(1, self.settings.llm_max_retries + 1):
                if db.kill_switch_on(self.conn):
                    raise KillSwitchOn("kill switch is on")
                remaining = None if deadline is None else deadline - time.monotonic()
                if remaining is not None and remaining < 1.0:
                    raise DeadlineExceeded("request time budget exhausted")
                check_token_budget(self.conn, self.run_id)
                reserve_call(self.conn, self.run_id, self.settings)
                _wait_for_slot(provider, spec["rpm"])
                started = time.monotonic()
                body_json = {"model": model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
                if tools:
                    body_json["tools"] = tools
                try:
                    resp = httpx.post(
                        f"{spec['base_url']}/chat/completions",
                        headers={"Authorization": f"Bearer {self.settings.provider_key(provider)}"},
                        json=body_json,
                        timeout=self.settings.llm_timeout_s if remaining is None else min(self.settings.llm_timeout_s,
                                                                                         remaining),
                    )
                except httpx.HTTPError as exc:
                    last_error = f"{type(exc).__name__}: {exc}"
                    self._log_failure(provider, model, attempt, purpose, trace_id, last_error)
                    self._backoff(attempt, deadline=deadline)
                    continue
                latency = time.monotonic() - started
                self.calls += 1
                if resp.status_code == 429 or resp.status_code >= 500:
                    last_error = f"HTTP {resp.status_code}"
                    self._log_failure(provider, model, attempt, purpose, trace_id, last_error)
                    retry_after = resp.headers.get("retry-after")
                    self._backoff(attempt, float(retry_after) if retry_after and retry_after.isdigit() else None,
                                  deadline=deadline)
                    continue
                if resp.status_code >= 400:
                    last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
                    self._log_failure(provider, model, attempt, purpose, trace_id, last_error)
                    break  # auth / bad request: retrying the same provider will not help
                try:
                    body = resp.json()
                    message = body["choices"][0]["message"]
                    text = message.get("content") or ""
                except (ValueError, KeyError, IndexError, TypeError) as exc:
                    last_error = f"malformed response: {exc}"
                    self._log_failure(provider, model, attempt, purpose, trace_id, last_error)
                    self._backoff(attempt, deadline=deadline)
                    continue
                usage = body.get("usage") or {}
                t_in, t_out = int(usage.get("prompt_tokens") or 0), int(usage.get("completion_tokens") or 0)
                # total_tokens includes hidden "thinking" tokens on reasoning models; budget on the larger number.
                t_total = max(int(usage.get("total_tokens") or 0), t_in + t_out)
                self.tokens += t_total
                self.tokens_in += t_in
                self.tokens_out += max(t_out, t_total - t_in)
                record_tokens(self.conn, self.run_id, t_total, self.settings)
                cost = estimate_cost(self.settings, t_in, max(t_out, t_total - t_in))
                emit(self.conn, "llm_call", run_id=self.run_id, trace_id=trace_id, provider=provider, model=model,
                     purpose=purpose, attempt=attempt, latency_s=round(latency, 2), tokens_in=t_in, tokens_out=t_out,
                     tokens_total=t_total, est_cost_usd=cost)
                return LLMResult(text, provider, model, t_in, t_out, latency, message=message,
                                 tool_calls=message.get("tool_calls") or None)
            emit(self.conn, "provider_failed", run_id=self.run_id, trace_id=trace_id, level="warn",
                 provider=provider, model=model, error=last_error)
        raise LLMError(f"all providers failed; last error: {last_error}")

    def _log_failure(self, provider, model, attempt, purpose, trace_id, error) -> None:
        emit(self.conn, "llm_retry", run_id=self.run_id, trace_id=trace_id, level="warn", provider=provider,
             model=model, attempt=attempt, purpose=purpose, error=error)

    @staticmethod
    def _backoff(attempt: int, retry_after: float | None = None, deadline: float | None = None) -> None:
        delay = retry_after if retry_after is not None else min(30.0, 2 ** attempt) + random.uniform(0, 1)
        delay = min(delay, 60.0)
        if deadline is not None:
            delay = max(0.0, min(delay, deadline - time.monotonic() - 1.0))
        time.sleep(delay)


def estimate_cost(settings: Settings, tokens_in: int, tokens_out: int) -> float | None:
    """USD estimate from configured prices. None when prices are unknown (we never invent provider pricing)."""
    if settings.llm_price_in_per_1k <= 0 and settings.llm_price_out_per_1k <= 0:
        return None
    return round(tokens_in / 1000 * settings.llm_price_in_per_1k + tokens_out / 1000 * settings.llm_price_out_per_1k, 6)
