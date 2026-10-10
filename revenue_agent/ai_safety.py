"""Shared output checks and per-session budgets for every AI answer (profit advisor and in-app guide)."""

from __future__ import annotations

import os
import sqlite3


def _secret_values() -> list[str]:
    names = ("GEMINI_API_KEY", "OPENROUTER_API_KEY", "NVIDIA_API_KEY", "SMTP_PASSWORD", "ADMIN_TOKEN")
    vals = [os.environ.get(n, "").strip() for n in names]
    for item in os.environ.get("TENANT_TOKENS", "").split(","):
        vals.append(item.partition(":")[2].strip())
    return [v for v in vals if len(v) >= 8]


def sanitize_answer(answer: str, system_prompt: str) -> tuple[str, list[str]]:
    """Redact secrets and verbatim system-instruction text from model output. Returns (text, what was redacted)."""
    from .observability import _SECRET
    flags = []
    for v in _secret_values():
        if v in answer:
            answer = answer.replace(v, "[REDACTED]")
            flags.append("secret")
    if _SECRET.search(answer):
        answer = _SECRET.sub("[REDACTED]", answer)
        flags.append("secret_pattern")
    for line in system_prompt.splitlines():
        line = line.strip(" -")
        if len(line) >= 40 and line in answer:
            answer = answer.replace(line, "[redacted: internal instructions]")
            if "system_prompt" not in flags:
                flags.append("system_prompt")
    return answer, flags


def bump_session_tokens(conn: sqlite3.Connection, key: str, delta_tokens: int, cap: int) -> None:
    """Accumulate tokens per chat session; the check before the next call is what stops it (fail closed)."""
    from . import db
    with db.tx(conn):
        conn.execute("INSERT INTO budget(key, used, cap) VALUES(?, 0, ?) ON CONFLICT(key) DO NOTHING", (key, cap))
        conn.execute("UPDATE budget SET used = used + ? WHERE key=?", (max(0, delta_tokens), key))
