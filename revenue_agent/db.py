"""SQLite persistence: explicit state, outbox, traces, skill versions, budgets."""

from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .config import get_settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,              -- train | eval | live
    seed INTEGER NOT NULL,
    size INTEGER NOT NULL,
    skill_version INTEGER NOT NULL,
    engine TEXT NOT NULL,
    explore REAL NOT NULL DEFAULT 0,
    human_approvals INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL,            -- running | completed | killed | halted_budget | failed
    round INTEGER NOT NULL DEFAULT 0,
    started_at REAL NOT NULL,
    finished_at REAL,
    metrics TEXT,
    error TEXT
);

CREATE TABLE IF NOT EXISTS invoices (
    run_id TEXT NOT NULL,
    id TEXT NOT NULL,
    customer TEXT NOT NULL,
    contact_name TEXT NOT NULL,
    contact_email TEXT NOT NULL,
    language TEXT NOT NULL DEFAULT 'en',
    business TEXT NOT NULL DEFAULT 'default',
    segment TEXT NOT NULL,
    tier TEXT NOT NULL,
    amount_cents INTEGER NOT NULL,
    due_date TEXT NOT NULL,
    days_overdue INTEGER NOT NULL,
    late_payments_12m INTEGER NOT NULL,
    persona TEXT NOT NULL,           -- HIDDEN from the agent; simulator ground truth
    state TEXT NOT NULL DEFAULT 'NEW',
    touches INTEGER NOT NULL DEFAULT 0,
    last_contact_round INTEGER NOT NULL DEFAULT 0,
    last_reply TEXT,
    reply_signal TEXT NOT NULL DEFAULT 'none',
    resolution TEXT,
    version INTEGER NOT NULL DEFAULT 0,
    lease_owner TEXT,
    lease_until REAL NOT NULL DEFAULT 0,
    PRIMARY KEY (run_id, id)
);

CREATE TABLE IF NOT EXISTS actions (           -- the outbox
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    invoice_id TEXT NOT NULL,
    round INTEGER NOT NULL,
    idem_key TEXT NOT NULL UNIQUE,
    kind TEXT NOT NULL,
    payload TEXT NOT NULL,
    status TEXT NOT NULL,            -- blocked | pending_approval | approved | queued | sent | rejected | needs_reconcile
    code TEXT,
    reason TEXT,
    skill_version INTEGER NOT NULL,
    engine TEXT NOT NULL,
    explored INTEGER NOT NULL DEFAULT 0,
    decided_by TEXT,
    trace_id TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS outcomes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    run_kind TEXT NOT NULL,
    invoice_id TEXT NOT NULL,
    round INTEGER NOT NULL,
    skill_version INTEGER NOT NULL,
    signal TEXT NOT NULL,
    tier TEXT NOT NULL,
    history TEXT NOT NULL,
    touch TEXT NOT NULL,
    action TEXT NOT NULL,
    tone TEXT,
    link INTEGER,
    due INTEGER,
    installments INTEGER,
    result TEXT NOT NULL,
    reward REAL NOT NULL,
    collected_cents INTEGER NOT NULL DEFAULT 0,
    explored INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS proposals (          -- decisions submitted by Hermes via MCP
    run_id TEXT NOT NULL,
    round INTEGER NOT NULL,
    invoice_id TEXT NOT NULL,
    payload TEXT NOT NULL,
    created_at REAL NOT NULL,
    PRIMARY KEY (run_id, round, invoice_id)
);

CREATE TABLE IF NOT EXISTS skill_versions (
    version INTEGER PRIMARY KEY,
    content TEXT NOT NULL,
    parent INTEGER,
    status TEXT NOT NULL,            -- active | candidate | passed_gate | rejected | retired
    author TEXT NOT NULL,
    notes TEXT,
    eval TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    trace_id TEXT,
    run_id TEXT,
    invoice_id TEXT,
    kind TEXT NOT NULL,
    level TEXT NOT NULL,
    data TEXT
);

CREATE TABLE IF NOT EXISTS budget (
    key TEXT PRIMARY KEY,
    used REAL NOT NULL DEFAULT 0,
    cap REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS kv (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_events_run ON events(run_id, id);
CREATE INDEX IF NOT EXISTS idx_actions_run ON actions(run_id, status);
CREATE INDEX IF NOT EXISTS idx_outcomes_kind ON outcomes(run_kind, run_id);
"""


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    db_path = Path(path or get_settings().db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=15, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=15000")
    conn.executescript(SCHEMA)
    _migrate(conn)
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    """Add columns introduced after a database was created (keeps old local data usable)."""
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(invoices)")}
    for name, ddl in (("language", "TEXT NOT NULL DEFAULT 'en'"), ("business", "TEXT NOT NULL DEFAULT 'default'")):
        if name not in cols:
            conn.execute(f"ALTER TABLE invoices ADD COLUMN {name} {ddl}")


@contextmanager
def tx(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Write transaction. Nested use joins the outer transaction."""
    if conn.in_transaction:
        yield conn
        return
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")


def rows(cursor: sqlite3.Cursor) -> list[dict]:
    return [dict(r) for r in cursor.fetchall()]


def one(cursor: sqlite3.Cursor) -> dict | None:
    row = cursor.fetchone()
    return dict(row) if row else None


def kv_get(conn: sqlite3.Connection, key: str, default=None):
    row = conn.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
    return json.loads(row["value"]) if row else default


def kv_set(conn: sqlite3.Connection, key: str, value) -> None:
    conn.execute(
        "INSERT INTO kv(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, json.dumps(value)),
    )


def kill_switch_on(conn: sqlite3.Connection) -> bool:
    return bool(kv_get(conn, "kill_switch", False))


def set_kill_switch(conn: sqlite3.Connection, on: bool) -> None:
    kv_set(conn, "kill_switch", bool(on))


def acquire_lock(conn: sqlite3.Connection, name: str, owner: str, ttl_s: float) -> bool:
    """Process-safe mutex with expiry (so a crashed holder cannot block forever)."""
    now = time.time()
    with tx(conn):
        current = kv_get(conn, f"lock:{name}")
        if current and current["until"] > now and current["owner"] != owner:
            return False
        kv_set(conn, f"lock:{name}", {"owner": owner, "until": now + ttl_s})
    return True


def release_lock(conn: sqlite3.Connection, name: str, owner: str) -> None:
    with tx(conn):
        current = kv_get(conn, f"lock:{name}")
        if current and current["owner"] == owner:
            conn.execute("DELETE FROM kv WHERE key=?", (f"lock:{name}",))
