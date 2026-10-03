# Agent specification

## 1. What is the goal of the agent?
Turn overdue invoices into collected cash, or the correct resolution, as fast as possible **without hurting
customer relationships or breaking policy**. Measured by: % of collectible dollars recovered, % of invoices
correctly resolved, complaints, and attempted policy violations.

## 2. What may it decide?
Per invoice, per round, exactly one of:

| Decision | Options |
|---|---|
| `action` | `send_reminder` · `offer_payment_plan` · `verify_payment` · `escalate_to_human` · `wait` |
| `tone` | `friendly` · `neutral` · `firm` |
| `include_payment_link` | only the invoice's own `https://pay.example.com/<invoice_id>` |
| `mention_due_date` | yes / no |
| `installments` | 2–3 (anything above that is routed to a human) |
| its own playbook | it may *propose* a new SKILL.md, but never activate it |

It may **not**: change amounts, give discounts, threaten anyone, contact a customer who disputed, opted out or
already paid, email more than once per round or more than 3 times in total, or change its own permissions,
limits, evals or hard rules.

## 3. What tools may it use?
Only the MCP tools in `revenue_agent/mcp_server.py` (Hermes engine) or the same contract in-process (offline/api):

| Tool | Privilege |
|---|---|
| `get_open_invoices` | read (sanitized view; hidden fields removed, replies wrapped as untrusted) |
| `submit_decisions` | propose (validated + dry-run through guardrails; **does not execute**) |
| `get_learning_report`, `get_active_skill`, `get_status` | read |
| `propose_skill` | propose (static validation only; activation requires gate + human) |

There is deliberately **no** tool to send email, execute, approve, promote, or touch limits or the kill switch.

## 4. What state must persist? (SQLite, `revenue_agent/db.py`)
- `invoices`: explicit state machine (`NEW → CONTACTED → PAID | PLAN_AGREED | ESCALATED | QUARANTINED | EXHAUSTED`,
  plus `AWAITING_APPROVAL`), touches, last contact round, last reply + classified signal, optimistic `version`, lease.
- `actions`: the outbox. Every attempted side effect with its **idempotency key**, status, guardrail code/reason,
  skill version, engine, who decided, and trace ID.
- `outcomes`: what happened after every decision (the learning signal).
- `skill_versions`: every skill ever proposed, with parent, status, author and eval record.
- `runs`, `events` (traces), `budget` (per-run/per-day counters), `kv` (kill switch, locks).

## 5. How is the output validated?
Three layers, all before anything reaches a customer (`revenue_agent/guardrails.py`):
1. **Schema**: Pydantic `Decision` (types, enums, lengths). Invalid items are blocked one by one, not the whole batch.
2. **Policy**: exact invoice ID and exact EGP amount in the message; written in the customer's language (Arabic/English); no legal threats, discounts or instruction leaks;
   only the approved payment link; no other customer named; plan size limits.
3. **World checks**: accounting ledger re-check (already paid?), dispute/opt-out/paid-claim signals, rate limit,
   max touches, approval tiers (key accounts, ≥ 100,000 EGP, plans over policy).

Approved actions are **re-validated at execution time**, because the world can change while an action waits.

## 6. What can go wrong? (and what the agent does about it)
| Failure | Handling |
|---|---|
| LLM returns invalid JSON / missing invoices | one repair attempt; missing invoices default to `wait`; unknown IDs logged |
| LLM provider 429/5xx/timeout | exponential backoff + Retry-After, then next provider, then **offline brain** (degraded mode, logged) |
| Budget exhausted | run halts cleanly (`halted_budget`), state kept, nothing half-done |
| Prompt injection in a customer reply | classified before any model sees it, invoice **quarantined**, routed to a human |
| Duplicate send (retry, crash, double click) | idempotency key UNIQUE constraint refuses it |
| Two workers on the same invoice | per-invoice lease + optimistic version check + global run lock |
| Agent writes a worse or unsafe skill | static checks + eval gate reject it; it never becomes active |
| A bad skill was promoted anyway | one-click rollback to the parent version |
| Customer already paid | ledger re-check blocks contact and reconciles the invoice as PAID |

## 7. What requires a human?
- Any email to a **key account** or an invoice **≥ 100,000 EGP**
- Payment plans over 3 installments
- Every **dispute**, **opt-out**, quarantined (**injection**) invoice, and invoices that hit max touches
- **Promoting** any new skill version (the gate is necessary but not sufficient)
- Releasing the kill switch

## 8. How does it recover?
- **Crash mid-action**: the outbox row exists before the side effect, so replays are refused by the
  idempotency key. Leases expire after 120s, and the run lock expires too, so a dead worker never blocks forever.
- **Provider outage**: fallback chain, then the deterministic offline brain using the same skill.
- **Bad learning**: rollback (`revenue-agent rollback`, or the dashboard button) restores the parent skill in both the DB and Hermes.
- **Budget/kill stop**: runs end in an explicit terminal status. State is consistent, and a new run can start once the cause is fixed.

## 9. What makes it stop?
- Per invoice: paid, plan agreed, escalated, quarantined, or 3 touches reached
- Per run: all rounds done, no open invoices, **kill switch**, **LLM call/token budget** exhausted, or an unrecoverable brain failure
- Per learning cycle: no candidate passes the gate (the active skill stays unchanged), or a human declines to promote
