# Architecture

## Components

| Module | Responsibility |
|---|---|
| `revenue_agent/engine.py` | Orchestrates runs and rounds, leases, run lock, outbox, execution, approvals, metrics |
| `revenue_agent/guardrails.py` | Pure, deterministic policy: reply classification, message validation, permission tiers |
| `revenue_agent/brains/` | `offline` (playbook executor + statistical learner), `api` (free LLMs), `hermes` (Hermes Agent via MCP) |
| `revenue_agent/llm.py` | OpenAI-compatible client: timeouts, retries, Retry-After, provider fallback, rate limiting, budgets |
| `revenue_agent/skills.py` | Skill versioning, playbook parsing, HARD-RULES immutability, promotion/rollback, Hermes sync |
| `revenue_agent/learning.py` | Evidence report, reflection, eval + promotion gate |
| `revenue_agent/evals.py` + `evals/golden_cases.json` | Golden safety cases |
| `revenue_agent/simulator.py` | Seeded debtor personas (stand-in for email + accounting APIs) |
| `revenue_agent/mcp_server.py` | Least-privilege MCP tools for Hermes |
| `revenue_agent/web/` | FastAPI dashboard (single static page, no build step) |
| `skills/ar-collections/SKILL.md` | The seed skill (Hermes skill format) |

## One round, step by step

1. Check the kill switch; load open invoices (`NEW`, `CONTACTED`).
2. Build **sanitized views**: no hidden fields, customer replies wrapped in `<untrusted_customer_reply>`.
3. The brain decides for the whole batch (1 LLM call per 20 invoices; Hermes: one headless `hermes -z` session
   that calls `get_open_invoices` → `submit_decisions`).
4. For each invoice: acquire a lease → validate the schema → `precheck` → either **block** (record, side
   effects such as auto-escalation), **queue for a human**, or **insert the outbox row with its idempotency key**
   → execute → commit state + outcome + trace atomically → release the lease.
5. Replies are classified; injection → `QUARANTINED`.

## Why Hermes talks through MCP only

Hermes in one-shot mode auto-approves its tool calls. So the safety boundary has to be the tool server, not
the agent. The MCP server exposes reads and *proposals* only. The engine, which Hermes cannot reach, is the
only component that can execute anything.

## Production mapping

| Simulated here | Production replacement |
|---|---|
| `simulator.generate_portfolio` | Xero / QuickBooks / Stripe invoice sync |
| `simulator.ledger_paid` | accounting API payment status (re-checked before every send) |
| `simulator.respond` | SMTP/Gmail send + inbound reply webhook |
| SQLite | Postgres (same schema; leases via `SELECT … FOR UPDATE SKIP LOCKED`) |
| dashboard approvals | Slack/Telegram approvals via the Hermes gateway |
| training episodes | shadow mode on real invoices, then a gradual rollout |
