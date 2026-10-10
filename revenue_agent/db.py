"""SQLite persistence: explicit state, outbox, traces, skill versions, budgets."""

from __future__ import annotations

import json
import sqlite3
import threading
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

-- ---------------------------------------------------------------- real data (user-uploaded ledger)
-- Completely separate from the simulator tables above: nothing here is ever generated or seeded.

CREATE TABLE IF NOT EXISTS datasets (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    source TEXT NOT NULL,            -- csv_upload
    kind TEXT NOT NULL,              -- live | sample (all invoice ids start with SAMPLE-: the test-only example file)
    filename TEXT,
    sha256 TEXT NOT NULL,
    imported_at REAL NOT NULL,
    rows_total INTEGER NOT NULL,
    rows_imported INTEGER NOT NULL,
    rows_rejected INTEGER NOT NULL,
    default_currency TEXT NOT NULL,
    date_format TEXT NOT NULL,
    mapping TEXT NOT NULL,           -- JSON: canonical field -> CSV header
    assumptions TEXT NOT NULL,       -- JSON list of dataset-level assumptions
    status TEXT NOT NULL             -- active | archived
);

CREATE TABLE IF NOT EXISTS ledger_invoices (
    dataset_id TEXT NOT NULL,
    invoice_id TEXT NOT NULL,
    source_row INTEGER NOT NULL,
    customer_id TEXT,
    customer_name TEXT,
    customer_key TEXT NOT NULL,      -- customer_id if present, else normalised name
    currency TEXT NOT NULL,
    amount_minor INTEGER NOT NULL,
    amount_paid_minor INTEGER,       -- NULL = not provided
    outstanding_minor INTEGER,       -- NULL = not provided
    status TEXT NOT NULL,            -- open | paid | partially_paid | void | unknown
    status_raw TEXT,
    issue_date TEXT,
    due_date TEXT NOT NULL,
    payment_date TEXT,
    last_contact_date TEXT,
    disputed INTEGER NOT NULL DEFAULT 0,
    do_not_contact INTEGER NOT NULL DEFAULT 0,
    contact_email TEXT,
    contact_phone TEXT,
    contact_name TEXT,
    language TEXT NOT NULL DEFAULT 'ar',
    notes TEXT,
    issues TEXT NOT NULL DEFAULT '[]',   -- JSON list of data-quality issue codes for this row
    PRIMARY KEY (dataset_id, invoice_id)
);

CREATE TABLE IF NOT EXISTS ledger_events (     -- outcomes recorded in the app (payments, replies, disputes...)
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dataset_id TEXT NOT NULL,
    invoice_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    occurred_on TEXT NOT NULL,
    amount_minor INTEGER,
    note TEXT,
    actor TEXT NOT NULL,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS followups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dataset_id TEXT NOT NULL,
    invoice_id TEXT NOT NULL,
    customer_key TEXT NOT NULL,
    channel TEXT NOT NULL DEFAULT 'email',
    recipient TEXT,
    language TEXT NOT NULL,
    tone TEXT NOT NULL,
    strategy TEXT NOT NULL,
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    outstanding_minor INTEGER NOT NULL,   -- balance the draft was written against
    currency TEXT NOT NULL,
    status TEXT NOT NULL,   -- draft | approved | sending | sent | send_failed | blocked | cancelled | manual_reported
    approval_hash TEXT,
    approved_by TEXT,
    approved_at REAL,
    provider TEXT,
    provider_result TEXT,
    block_code TEXT,
    block_reason TEXT,
    evidence TEXT NOT NULL,
    created_by TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    sent_at REAL
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    dataset_id TEXT,
    invoice_id TEXT,
    followup_id INTEGER,
    outcome TEXT NOT NULL,           -- ok | blocked | refused | failed
    detail TEXT
);

-- ---------------------------------------------------------------- profit investigations (real uploaded data)
CREATE TABLE IF NOT EXISTS investigations (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    title TEXT NOT NULL,
    profile TEXT NOT NULL DEFAULT '{}',      -- owner answers about the business (JSON)
    objective TEXT,
    stage TEXT NOT NULL DEFAULT 'profile',  -- profile | documents | analysis | recommendations | tracking
    default_currency TEXT NOT NULL DEFAULT 'EGP',
    settings TEXT NOT NULL DEFAULT '{}',     -- JSON owner settings, e.g. cost allocation methods
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS inv_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    investigation_id TEXT NOT NULL,
    filename TEXT NOT NULL,
    kind TEXT,
    sha256 TEXT NOT NULL,
    summary TEXT NOT NULL,                  -- JSON parse summary (tables, issues, mapping)
    status TEXT NOT NULL,                   -- imported | failed | removed
    uploaded_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS inv_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    investigation_id TEXT NOT NULL,
    file_id INTEGER,                         -- NULL = typed in manually by the owner
    rtype TEXT NOT NULL,
    data TEXT NOT NULL                       -- JSON canonical record incl. sheet + row provenance
);
CREATE TABLE IF NOT EXISTS inv_questions (
    investigation_id TEXT NOT NULL,
    qid TEXT NOT NULL,
    status TEXT NOT NULL,                    -- answered | skipped | dont_know
    answer TEXT,
    answered_at REAL NOT NULL,
    PRIMARY KEY (investigation_id, qid)
);
CREATE TABLE IF NOT EXISTS interventions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    investigation_id TEXT NOT NULL,
    driver TEXT NOT NULL,                    -- metric key, e.g. packaging (per order)
    title TEXT NOT NULL,
    option_key TEXT NOT NULL,
    currency TEXT NOT NULL,
    baseline TEXT NOT NULL,                  -- JSON: period, per-order value, orders, aov, return_rate, mix
    projection TEXT NOT NULL,                -- JSON: projected saving + assumptions (never a realised figure)
    status TEXT NOT NULL,
    implemented_on TEXT,
    implementation_note TEXT,
    result TEXT,                             -- JSON: last verification
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS scenarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    investigation_id TEXT NOT NULL,
    name TEXT NOT NULL,
    params TEXT NOT NULL,                    -- JSON scenario inputs (assumptions)
    result TEXT NOT NULL,                    -- JSON projection at save time (never an actual result)
    intervention_id INTEGER,                 -- set when saved as an experiment
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS quotes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    investigation_id TEXT NOT NULL,
    item_key TEXT NOT NULL,                  -- owner-defined comparison group, e.g. "mailer box 30x20 printed"
    category TEXT NOT NULL,                  -- packaging | shipping | cogs_materials | product
    supplier TEXT NOT NULL,
    spec TEXT NOT NULL,                      -- the specification exactly as written on the quote
    currency TEXT NOT NULL,
    unit_price_minor INTEGER NOT NULL,
    moq REAL,                                -- NULL = unknown (never assumed)
    setup_fee_minor INTEGER,
    delivery_fee_minor INTEGER,
    payment_terms TEXT,
    lead_time_days INTEGER,
    quality_notes TEXT,
    source TEXT NOT NULL,                    -- written_quote | verbal | web_listing
    document_name TEXT,
    quote_date TEXT,
    owner_confirmed_quote INTEGER NOT NULL DEFAULT 0,  -- owner confirms this is a real quote they received
    spec_confirmed INTEGER NOT NULL DEFAULT 0,         -- owner confirms the spec matches the group's requirement
    created_at REAL NOT NULL,
    outreach_id INTEGER,                     -- the supplier request this quote answers (owner-linked)
    linked_product TEXT,                     -- for product-cost quotes: which sold product it would replace
    field_sources TEXT                       -- JSON {field: typed | extracted_confirmed}
);
CREATE TABLE IF NOT EXISTS outreach (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    investigation_id TEXT NOT NULL,
    purpose TEXT NOT NULL,                   -- quote_request | moq_question
    trigger TEXT NOT NULL,                   -- JSON: the finding / comparison that justified it
    category TEXT NOT NULL,
    item_key TEXT NOT NULL,                  -- quote comparison group replies will land in
    brief TEXT NOT NULL,                     -- JSON: what is sourced, spec, quality, quantity, terms, decision
    language TEXT NOT NULL,
    supplier_name TEXT,
    supplier_email TEXT,
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    status TEXT NOT NULL,                    -- draft | approved | sending | sent | send_failed | send_unknown |
                                             -- copied_manual | reply_reported | cancelled
    approval_hash TEXT,
    approved_by TEXT,
    provider_result TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    sent_at REAL
);
CREATE TABLE IF NOT EXISTS business_memory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id TEXT NOT NULL,
    kind TEXT NOT NULL,                      -- fact | preference | mapping | outcome
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    source TEXT NOT NULL,                    -- owner_confirmed | verified_outcome
    uses INTEGER NOT NULL DEFAULT 0,
    corrections INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'active',   -- active | retired
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    UNIQUE (tenant_id, kind, key)
);
CREATE TABLE IF NOT EXISTS guide_feedback (     -- reviews, bug reports and feature ideas from the in-app guide
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id TEXT NOT NULL,
    kind TEXT NOT NULL,                      -- review | idea | bug | other
    rating INTEGER,                          -- 1..5 or NULL
    text TEXT NOT NULL DEFAULT '',
    page TEXT,
    lang TEXT,
    actor TEXT,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_guide_feedback_tenant ON guide_feedback(tenant_id, id);
CREATE INDEX IF NOT EXISTS idx_inv_records ON inv_records(investigation_id, rtype);
CREATE INDEX IF NOT EXISTS idx_investigations_tenant ON investigations(tenant_id);

CREATE INDEX IF NOT EXISTS idx_ledger_customer ON ledger_invoices(dataset_id, customer_key);
CREATE INDEX IF NOT EXISTS idx_followups_inv ON followups(dataset_id, invoice_id);
CREATE INDEX IF NOT EXISTS idx_ledger_events_inv ON ledger_events(dataset_id, invoice_id);
CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_log(id);

CREATE INDEX IF NOT EXISTS idx_events_run ON events(run_id, id);
CREATE INDEX IF NOT EXISTS idx_actions_run ON actions(run_id, status);
CREATE INDEX IF NOT EXISTS idx_outcomes_kind ON outcomes(run_kind, run_id);
"""


_INIT_LOCK = threading.Lock()
_INITIALISED: set[str] = set()


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    """Open a connection. Schema creation/migration runs once per database file per process (under a lock), so
    concurrent first requests don't race on DDL or on switching the journal mode."""
    db_path = Path(path or get_settings().db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=15, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=15000")
    key = str(db_path.resolve())
    if key not in _INITIALISED or not db_path.exists():
        with _INIT_LOCK:
            if key not in _INITIALISED or not db_path.exists():
                conn.execute("PRAGMA journal_mode=WAL")
                conn.executescript(SCHEMA)
                _migrate(conn)
                _INITIALISED.add(key)
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    """Add columns introduced after a database was created (keeps old local data usable)."""
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(invoices)")}
    for name, ddl in (("language", "TEXT NOT NULL DEFAULT 'en'"), ("business", "TEXT NOT NULL DEFAULT 'default'")):
        if name not in cols:
            conn.execute(f"ALTER TABLE invoices ADD COLUMN {name} {ddl}")
    # Tenant scoping for the real-data tables (every query filters on it; see ledger/store.py).
    for table in ("datasets", "audit_log"):
        tcols = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
        if "tenant_id" not in tcols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN tenant_id TEXT NOT NULL DEFAULT 'default'")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_datasets_tenant ON datasets(tenant_id, status)")
    qcols = {r["name"] for r in conn.execute("PRAGMA table_info(quotes)")}
    for name, ddl in (("outreach_id", "INTEGER"), ("linked_product", "TEXT"), ("field_sources", "TEXT")):
        if qcols and name not in qcols:
            conn.execute(f"ALTER TABLE quotes ADD COLUMN {name} {ddl}")
    icols = {r["name"] for r in conn.execute("PRAGMA table_info(investigations)")}
    if icols and "settings" not in icols:
        conn.execute("ALTER TABLE investigations ADD COLUMN settings TEXT NOT NULL DEFAULT '{}'")


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
