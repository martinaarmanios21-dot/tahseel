# Ribhiya (ربحية): AI profitability & cost-leakage specialist for product-based SMEs

Upload your real sales, product-cost and supplier/expense files. Ribhiya asks you a few simple questions, works out
what each order really leaves you (deterministically, per currency, traceable to the file and row), finds which
cost changed it, explains it in plain Egyptian Arabic or English with charts, suggests quality-aware options, and then
measures whether your change actually helped, without ever calling a projection a saving. It also shows profit per
order, product and channel (actual vs allocated costs, reconciled to the monthly totals), lets you test "what if I
change price, packaging, shipping, discounts or a supplier?" on a real month, and compares supplier quotes on an
equal basis. When a cost problem is found, it asks for the evidence that matters next and can prepare a supplier
quote request (owner-approved, sent only via your SMTP server, otherwise a copyable draft) whose replies flow back
into the comparison, the simulator and experiment tracking.

Details: [docs/PROFIT_INVESTIGATION.md](docs/PROFIT_INVESTIGATION.md) (workflow, Hermes Agent integration, learning,
judge steps) · [docs/SECURITY.md](docs/SECURITY.md)

---

## Chat with Ribhiya (in-app guide)

The button at the bottom corner of every page opens a small panel with four tabs. Inside an investigation it knows
where you are: it shows the step and the next action (the same as **Do this now**), and answers from that
investigation ("Why is my profit down?" → the profit advisor; "What should I do now?" / "What's missing?" / "What can
I do about it?" → its computed state). On Home it helps you get started.
- **Ask:** your numbers (inside an investigation), using the app, or business concepts. Answers come from hand-written help content
  (`revenue_agent/guide/content.py`) and are instant. Only an unmatched question goes to the AI (if a key is set),
  and it gets the question and the help text, never your files or figures.
- **Tour:** each feature in short steps, with **Show me**, which opens the right page, tab or card.
- **Learn:** key business concepts (margin, break-even, cash flow, pricing…) with a simple example and YouTube /
  Coursera **search** links (no hand-picked videos).
- **Feedback:** a review with stars, a feature idea or a problem. It's stored in your local database
  (`guide_feedback` table, export at `/api/guide/feedback.csv`) and not sent anywhere.

## Run it

Requirements: Python 3.11+ and [uv](https://docs.astral.sh/uv/getting-started/installation/).

```bash
git clone https://github.com/martinaarmanios21-dot/tahseel.git && cd tahseel
uv sync
uv run revenue-agent serve          # → http://127.0.0.1:8000   (port busy? add --port 8080)
```

1. On Home, type your business name and click **Start a new investigation**.
2. **Do this now** asks a few short questions, then for your sales file. Upload it plus product costs and
   supplier/expense invoices (CSV, Excel or text PDF). It asks for anything else it needs, and says why.
3. **What I found** shows the biggest cost leak per order, with a chart and **Explain**. **Get cheaper prices**
   prepares a supplier quote request you approve.
4. The tabs hold the rest: **Files · Products · What if · Suppliers · Results**. Ask questions in **Chat with Ribhiya**
   (bottom corner); inside an investigation it answers from that investigation. A fictional test pack with a step-by-step guide: `uv run python scripts/make_test_pack.py`.

Optional configuration (`.env`, see `.env.example`): an LLM key (`GEMINI_API_KEY`, free from Google AI Studio),
SMTP for sending approved supplier requests (`EMAIL_SENDING_ENABLED=1`, `SMTP_*`), `ADMIN_TOKEN` for any shared
deployment.

Tests: `uv run pytest -q` (134 tests: profit investigation, in-app guide, evidence and supplier outreach, order profit, simulator, quotes, security, plus the simulation lab). Frontend: `cd frontend && npx vitest run`. MCP server with the read-only profit tools: `uv run python -m revenue_agent.mcp_server`.

> **Collections was removed (2026-10-10).** The former invoice-collections workflow (invoice import, overdue
> analysis, follow-up emails, its chat agent, pages and API) is gone. The shared pieces it had (value parsing,
> audit log, SMTP mailer) live on in `revenue_agent/ledger/` and are used by the profit investigation. Its database
> tables are left untouched, so no stored records were deleted.

## Simulation lab (synthetic data, for testing learning and guardrails)

Separate from the product and not linked from the app (it is the original collections-agent research harness):
fictional customers with hidden personas let the self-improvement loop and guardrails be stress-tested reproducibly. **البيانات دي للاختبار فقط، ومش بتمثل معاملات حقيقية.** Its numbers never appear
in the main app.

```bash
uv run revenue-agent --engine offline demo --yes     # train → reflect → eval gate → guardrail checks
# reviewer dashboard for the lab: http://127.0.0.1:8000/judges
```

An audit found the earlier headline ("84% cash collected") was inflated: agreed instalment plans were counted as
cash, and the learner was rewarded for escalating or using a firm tone on first contact. With those fixed (cash =
PAID only, plans reported separately, a deterministic first-contact constraint), the learned candidates are safer
(0 complaints, 9/9 safety cases) but collect **less** cash (14.4% vs 23.8%) because they offer plans to everyone,
so **the eval gate rejects them** and the active skill stays unchanged. See
[docs/EVALUATION_METHODOLOGY.md](docs/EVALUATION_METHODOLOGY.md#5-simulation-lab-what-changed-and-the-honest-result).

**Optional Hermes brain:** with [Hermes Agent](https://github.com/NousResearch/hermes-agent) installed:

```bash
uv run revenue-agent hermes-setup            # creates an isolated Hermes profile "tahseel" pinned to free Gemini,
                                             # installs the skill, registers the MCP server
hermes -p tahseel mcp test revenue_agent     # should list 6 tools
uv run revenue-agent --engine hermes demo
```

The Hermes engine **refuses to run unless `HERMES_MODEL` is set**, and it uses its own profile with an explicit
provider. It can never fall back to a paid model from your default Hermes profile.

## How it works

```
             ┌────────────────────── brains (decide only, never act) ───────────────────────┐
             │  offline: playbook executor   api: free LLM (Gemini→OpenRouter→NVIDIA)        │
             │  hermes: Hermes Agent + ar-collections skill, talking ONLY via MCP tools      │
             └──────────────────────────────┬────────────────────────────────────────────────┘
                                            │ decisions (JSON)
     ┌──────────────────────────────────────▼─────────────────────────────────────────────┐
     │ GUARDRAILS (deterministic, agent cannot modify): schema validation · permissions    │
     │ · exact-amount/ID checks · no legal threats/discounts/foreign links/other customers │
     │ · ledger re-check · disputes & opt-outs · rate limits · max touches · human approval│
     └──────────────────────────────────────┬─────────────────────────────────────────────┘
                                            │ allowed actions
     ┌──────────────────────────────────────▼─────────────────────────────────────────────┐
     │ ENGINE: state machine (optimistic versioning) · leases · run lock · outbox with     │
     │ idempotency keys · kill switch · budgets · trace IDs                               │
     └──────────────────────────────────────┬─────────────────────────────────────────────┘
                                            │ executes against
                       Debtor simulator (hidden personas)  ·  in production: email + accounting APIs
                                            │ outcomes (paid? complained? disputed?)
     ┌──────────────────────────────────────▼─────────────────────────────────────────────┐
     │ LEARNING: evidence report → brain proposes new SKILL.md → static checks (HARD-RULES │
     │ immutable) → eval gate (holdout + golden cases) → HUMAN promotes → versioned/rollback│
     └────────────────────────────────────────────────────────────────────────────────────┘
```

Read more:
- [docs/AGENT_SPEC.md](docs/AGENT_SPEC.md): goal, decisions, tools, state, validation, failure modes, human role, recovery, stop conditions
- [docs/FAILURE_MODES.md](docs/FAILURE_MODES.md): the 12 reliability factors and where each is enforced in code
- [docs/SELF_IMPROVEMENT.md](docs/SELF_IMPROVEMENT.md): how the agent learns without being allowed to break itself
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) · [docs/EVALS.md](docs/EVALS.md) · [docs/SECURITY.md](docs/SECURITY.md) · [docs/BUSINESS_CASE.md](docs/BUSINESS_CASE.md)

## Honest limitations

- No real outcome history ships with the project, so no measured saving on real data is claimed.
- Email sending uses SMTP and is covered by tests with a fake SMTP server; it has not been verified against a
  real provider in this repository. Without SMTP configured, Ribhiya only drafts and copies.
- Files are uploaded by hand (CSV, Excel, text PDF); there is no live accounting or store connector, and no OCR for
  scanned PDFs.
- Single-user app; set `ADMIN_TOKEN` before exposing it. The MCP HTTP transport has no built-in auth.
- The Wesam package in docs/WESAM_PACKAGE.md describes the removed collections agent and is out of date.

## Front end

`frontend/` is the React app. The built files are committed in `revenue_agent/web/app/`, so reviewers don't need
Node. Rebuild with `bash scripts/build_frontend.sh`. It talks only to the real API: there is no demo-data
fallback. The earlier role-based screens (simulator-only) remain in `frontend/src/routes/` but are excluded from
routing in `vite.config.ts`.

MIT licensed.
