# Designed for failure before autonomy

Each reliability factor, how it is enforced, where it lives in the code, and the test that proves it.

| Factor | How it is enforced | Code | Test |
|---|---|---|---|
| **Explicit state** | Invoice state machine with an allowed-transition table; illegal transitions raise. Runs, actions, outcomes and skills are all rows, nothing is implicit in a prompt. | `models.TRANSITIONS`, `engine._transition` | `test_engine.py` (all) |
| **Validation** | Pydantic schema → message policy → world checks; re-checked again at approval time. | `guardrails.precheck`, `guardrails.validate_message`, `engine.approve` | `test_guardrails.py` (16 tests) |
| **Permissions** | Tiered actions: read (`verify`, `escalate`, `wait`) / contact (guardrailed) / human-only (key accounts, ≥ 100,000 EGP, big plans, promotion). MCP exposes no execute/promote/limit tools. | `guardrails.precheck`, `mcp_server.py` | `test_key_account_needs_human`, `test_human_approval_flow` |
| **Retries + timeouts** | httpx timeout per call; exponential backoff with jitter; honours `Retry-After`; provider fallback chain; Hermes subprocess timeout; one JSON repair attempt. | `llm.LLMClient.chat`, `brains/api._decide_batch`, `brains/hermes._run` | `test_retry_on_429_then_success`, `test_bad_json_is_repaired`, `test_provider_down_degrades_to_offline` |
| **Idempotency** | Every side effect gets `sha256(run, invoice, round, action)` in a UNIQUE column. The outbox row is written *before* the side effect. | `guardrails.idempotency_key`, `engine._insert_action` | `test_duplicate_send_refused` |
| **Observability** | Structured events with trace IDs for every LLM call, verdict, action, approval and gate; JSONL log + DB; PII/keys masked; dashboard trace view. | `observability.emit` | visible in dashboard §5 |
| **Evals** | Holdout portfolio (fixed seeds, no exploration) + 9 golden safety cases (English + Arabic), run on every candidate skill. | `learning.evaluate`, `evals.run_golden`, `evals/golden_cases.json` | `test_learning_improves_and_gate_promotes` |
| **Rate limits** | Per-provider request spacing (RPM); per-debtor max one contact per round; max 3 touches per invoice. | `llm._wait_for_slot`, `precheck` (`rate_limited`, `max_touches`) | `test_rate_limit_one_contact_per_round`, `test_max_touches` |
| **Cost limits** | Calls reserved *before* each request against per-run and per-day caps (fail closed); per-run token cap; halting is a clean terminal state. Tasks are batched (20 invoices per call) to minimise calls. | `llm.reserve_call`, `llm.check_token_budget`, `engine._decide` | `test_budget_cap_enforced`, `test_budget_exhaustion_halts_run` |
| **Versioning** | Skills are immutable numbered versions with parent, author, status and eval record. Every action records the skill version + engine that produced it. Rollback restores the parent. | `skills.py` | `test_hard_rules_are_immutable`, `test_unpromotable_without_gate` |
| **Security** | Untrusted replies are classified and wrapped; injection → quarantine; only the approved payment link allowed; no cross-customer data; secrets only from `.env`; least-privilege MCP tools; HARD-RULES block immutable. | `guardrails.classify_reply`, `brains/base.agent_view`, `skills.validate_content` | `test_injection_is_quarantined_and_never_paid`, `test_phishing_link_blocked` |
| **Concurrency** | Global run lock with expiry; per-invoice leases with expiry; optimistic version check on every state write; SQLite WAL + `BEGIN IMMEDIATE`. | `db.acquire_lock`, `engine._acquire_lease`, `engine._transition` | `test_run_lock_prevents_concurrent_runs` |

## Degradation ladder

1. Primary free LLM (Gemini) → 2. next provider (OpenRouter → NVIDIA) → 3. **offline brain** running the same
skill (logged as `degraded_mode`) → 4. halt with an explicit status. The system never "kind of" works: every run
ends in `completed`, `killed`, `halted_budget` or `failed`, with metrics.

## Stop conditions

Kill switch (checked before every model call and every action) · per-run and per-day LLM call caps · per-run token cap ·
max touches per invoice · max rounds per run · no candidate passing the gate · a human declining promotion.
