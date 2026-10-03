"""Structured events with trace IDs. PII (emails) is masked before anything is persisted."""

from __future__ import annotations

import json
import re
import sqlite3
import time
import uuid

from .config import get_settings

_EMAIL = re.compile(r"\b([A-Za-z0-9._%+-])[A-Za-z0-9._%+-]*@([A-Za-z0-9.-]+\.[A-Za-z]{2,})\b")
_SECRET = re.compile(r"\b(AIza[0-9A-Za-z_\-]{20,}|sk-[A-Za-z0-9_\-]{16,}|nvapi-[A-Za-z0-9_\-]{16,})\b")


def mask(text: str) -> str:
    text = _EMAIL.sub(r"\1***@\2", text)
    return _SECRET.sub("[REDACTED_KEY]", text)


def new_trace_id() -> str:
    return uuid.uuid4().hex[:16]


def emit(
    conn: sqlite3.Connection,
    event: str,
    *,
    run_id: str | None = None,
    trace_id: str | None = None,
    invoice_id: str | None = None,
    level: str = "info",
    **data,
) -> None:
    payload = mask(json.dumps(data, default=str))
    ts = time.time()
    conn.execute(
        "INSERT INTO events(ts, trace_id, run_id, invoice_id, kind, level, data) VALUES(?,?,?,?,?,?,?)",
        (ts, trace_id, run_id, invoice_id, event, level, payload),
    )
    log_dir = get_settings().data_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    line = {"ts": ts, "kind": event, "level": level, "run_id": run_id, "trace_id": trace_id,
            "invoice_id": invoice_id, "data": json.loads(payload)}
    with open(log_dir / "events.jsonl", "a") as fh:
        fh.write(json.dumps(line) + "\n")
