"""Skill versioning: every skill change is a new immutable version with a parent, status and eval record.

The agent may *propose* versions. Only the promotion gate + a human can make one active.
"""

from __future__ import annotations

import difflib
import re
import sqlite3
import time

import yaml

from . import db
from .config import ROOT, Settings, get_settings
from .models import ACTIONS, HISTORIES, SIGNALS, TIERS, TONES, TOUCHES

SEED_PATH = ROOT / "skills" / "ar-collections" / "SKILL.md"
MAX_SKILL_BYTES = 20_000
MAX_RULES = 40

_PLAYBOOK = re.compile(r"```playbook\s*\n(.*?)\n```", re.S)
_HARD = re.compile(r"<!-- HARD-RULES:BEGIN -->(.*?)<!-- HARD-RULES:END -->", re.S)
_LESSONS = re.compile(r"(## Lessons learned\s*\n)(.*)$", re.S)
_VERSION_LINE = re.compile(r"^version:.*$", re.M)

WHEN_VALUES = {"signal": set(SIGNALS), "tier": set(TIERS), "history": set(HISTORIES), "touch": set(TOUCHES)}
DO_KEYS = {"action", "tone", "include_payment_link", "mention_due_date", "installments"}


class SkillRejected(ValueError):
    pass


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def seed_content() -> str:
    return SEED_PATH.read_text()


def hard_rules(content: str) -> str | None:
    m = _HARD.search(content)
    return _norm(m.group(1)) if m else None


def parse_playbook(content: str) -> list[dict]:
    m = _PLAYBOOK.search(content)
    if not m:
        raise SkillRejected("no ```playbook block found")
    try:
        data = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError as exc:
        raise SkillRejected(f"playbook is not valid YAML: {exc}") from exc
    rules = data.get("rules") if isinstance(data, dict) else None
    if not isinstance(rules, list) or not rules:
        raise SkillRejected("playbook must contain a non-empty 'rules' list")
    return rules


def validate_content(content: str, settings: Settings | None = None) -> list[str]:
    """Static checks a candidate skill must pass before it is even evaluated."""
    settings = settings or get_settings()
    errors: list[str] = []
    if len(content.encode()) > MAX_SKILL_BYTES:
        errors.append(f"skill larger than {MAX_SKILL_BYTES} bytes")
    if not re.search(r"^name:\s*ar-collections\s*$", content, re.M):
        errors.append("frontmatter must keep name: ar-collections")
    if hard_rules(content) != hard_rules(seed_content()):
        errors.append("HARD-RULES block was modified or removed (immutable)")
    try:
        rules = parse_playbook(content)
    except SkillRejected as exc:
        return errors + [str(exc)]
    if len(rules) > MAX_RULES:
        errors.append(f"too many rules ({len(rules)} > {MAX_RULES})")
    for i, rule in enumerate(rules):
        if not isinstance(rule, dict) or not isinstance(rule.get("when", {}), dict) or not isinstance(rule.get("do"), dict):
            errors.append(f"rule {i}: needs 'when' (mapping) and 'do' (mapping)")
            continue
        for key, value in (rule.get("when") or {}).items():
            if key not in WHEN_VALUES or value not in WHEN_VALUES[key]:
                errors.append(f"rule {i}: invalid when {key}={value!r}")
        do = rule["do"]
        if set(do) - DO_KEYS:
            errors.append(f"rule {i}: unknown do keys {sorted(set(do) - DO_KEYS)}")
        if do.get("action") not in ACTIONS:
            errors.append(f"rule {i}: invalid action {do.get('action')!r}")
        if "tone" in do and do["tone"] not in TONES:
            errors.append(f"rule {i}: invalid tone {do['tone']!r}")
        inst = do.get("installments")
        if inst is not None and (not isinstance(inst, int) or not 2 <= inst <= settings.max_installments):
            errors.append(f"rule {i}: installments must be 2..{settings.max_installments}")
        if covers_first_contact(rule.get("when") or {}) and not first_contact_ok(do):
            errors.append(f"rule {i}: first contact without a reply signal must not escalate or use a firm tone")
    return errors


def covers_first_contact(when: dict) -> bool:
    """True if a rule can fire on a first touch with no customer signal (the classic reward-hacking spot)."""
    return when.get("signal", "none") == "none" and when.get("touch", "first") == "first"


def first_contact_ok(do: dict) -> bool:
    """Anti reward-hacking constraint: never open with escalation or a firm tone. Deterministic, not learned."""
    return do.get("action") != "escalate_to_human" and do.get("tone") != "firm"


def with_version(content: str, version: int) -> str:
    return _VERSION_LINE.sub(f"version: {version}.0.0", content, count=1)


def replace_playbook(content: str, rules: list[dict], lessons: list[str]) -> str:
    body = yaml.safe_dump({"rules": rules}, sort_keys=False, default_flow_style=None, width=120).strip()
    content = _PLAYBOOK.sub(lambda _m: f"```playbook\n{body}\n```", content, count=1)
    lesson_text = "\n".join(f"- {line}" for line in lessons) + "\n"
    return _LESSONS.sub(lambda m: m.group(1) + lesson_text, content, count=1)


# ---------------------------------------------------------------- persistence

def ensure_seeded(conn: sqlite3.Connection) -> None:
    if conn.execute("SELECT 1 FROM skill_versions LIMIT 1").fetchone():
        return
    now = time.time()
    with db.tx(conn):
        conn.execute(
            "INSERT INTO skill_versions(version, content, parent, status, author, notes, created_at, updated_at) "
            "VALUES(1, ?, NULL, 'active', 'seed', 'untrained seed skill', ?, ?)",
            (with_version(seed_content(), 1), now, now),
        )


def active(conn: sqlite3.Connection) -> dict:
    ensure_seeded(conn)
    row = db.one(conn.execute("SELECT * FROM skill_versions WHERE status='active' ORDER BY version DESC LIMIT 1"))
    if row is None:  # should never happen, but recover instead of crashing
        row = db.one(conn.execute("SELECT * FROM skill_versions WHERE version=1"))
    return row


def get(conn: sqlite3.Connection, version: int) -> dict:
    row = db.one(conn.execute("SELECT * FROM skill_versions WHERE version=?", (version,)))
    if not row:
        raise KeyError(f"skill version {version} not found")
    return row


def list_versions(conn: sqlite3.Connection) -> list[dict]:
    ensure_seeded(conn)
    return db.rows(conn.execute(
        "SELECT version, parent, status, author, notes, eval, created_at, updated_at FROM skill_versions ORDER BY version"
    ))


def create_candidate(conn: sqlite3.Connection, content: str, *, parent: int, author: str, notes: str) -> int:
    errors = validate_content(content)
    if errors:
        raise SkillRejected("; ".join(errors))
    now = time.time()
    with db.tx(conn):
        version = conn.execute("SELECT COALESCE(MAX(version), 0) + 1 FROM skill_versions").fetchone()[0]
        conn.execute(
            "INSERT INTO skill_versions(version, content, parent, status, author, notes, created_at, updated_at) "
            "VALUES(?, ?, ?, 'candidate', ?, ?, ?, ?)",
            (version, with_version(content, version), parent, author, notes, now, now),
        )
    return version


def set_status(conn: sqlite3.Connection, version: int, status: str, eval_json: str | None = None) -> None:
    with db.tx(conn):
        if eval_json is None:
            conn.execute("UPDATE skill_versions SET status=?, updated_at=? WHERE version=?", (status, time.time(), version))
        else:
            conn.execute("UPDATE skill_versions SET status=?, eval=?, updated_at=? WHERE version=?",
                         (status, eval_json, time.time(), version))


def promote(conn: sqlite3.Connection, version: int, *, by: str, force: bool = False) -> None:
    row = get(conn, version)
    if row["status"] != "passed_gate" and not force:
        raise SkillRejected(f"version {version} has status {row['status']!r}; only 'passed_gate' can be promoted")
    with db.tx(conn):
        conn.execute("UPDATE skill_versions SET status='retired', updated_at=? WHERE status='active'", (time.time(),))
        conn.execute("UPDATE skill_versions SET status='active', updated_at=? WHERE version=?", (time.time(), version))
    sync_to_hermes(row["content"])


def rollback(conn: sqlite3.Connection, *, by: str) -> int:
    current = active(conn)
    target = current["parent"]
    if target is None:
        raise SkillRejected("active version has no parent to roll back to")
    with db.tx(conn):
        conn.execute("UPDATE skill_versions SET status='rejected', notes=COALESCE(notes,'') || ' [rolled back by ' || ? || ']', "
                     "updated_at=? WHERE version=?", (by, time.time(), current["version"]))
        conn.execute("UPDATE skill_versions SET status='active', updated_at=? WHERE version=?", (time.time(), target))
    sync_to_hermes(get(conn, target)["content"])
    return target


def diff(conn: sqlite3.Connection, version: int, against: int | None = None) -> str:
    row = get(conn, version)
    base_v = against if against is not None else row["parent"]
    base = get(conn, base_v)["content"] if base_v else ""
    return "".join(difflib.unified_diff(
        base.splitlines(keepends=True), row["content"].splitlines(keepends=True),
        fromfile=f"SKILL.md v{base_v}", tofile=f"SKILL.md v{version}",
    ))


def sync_to_hermes(content: str) -> str | None:
    """Install the active skill where Hermes loads skills from (so `hermes -s ar-collections` uses it)."""
    settings = get_settings()
    if not settings.hermes_skill_sync or not settings.hermes_profile_home.is_dir():
        return None
    target = settings.hermes_profile_home / "skills" / "finance" / "ar-collections" / "SKILL.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)
    return str(target)
