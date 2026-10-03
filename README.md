# Tahseel (تحصيل): a self-improving, failure-first collections agent for SMBs

> An accounts-receivable agent that chases overdue invoices, **learns from every outcome which approach
> gets each kind of customer to pay**, and rewrites its own [Hermes Agent](https://github.com/NousResearch/hermes-agent)
> skill. Every self-edit has to pass an eval gate, and a human has to approve it before it goes live.
> Guardrails live in deterministic code the agent cannot change.

| | Untrained skill (v1) | Self-learned skill (v2) |
|---|---:|---:|
| Cash collected (holdout portfolio) | 23.8% | **84.0%** |
| Invoices correctly resolved | 52.5% | **80.0%** |
| Customer complaints | 12 | **0** |
| Attempted policy violations (blocked) | 6 | **0** |
| Golden safety cases (Arabic + English) | 4/9 | **9/9** |

*Reproduce with `uv run revenue-agent --engine offline demo --yes` (no API key, about 10 seconds). Details: [docs/EVALS.md](docs/EVALS.md).*

---

## Why this agent

Built for Egyptian SMBs: amounts in **EGP**, emails in **each customer's language (Arabic or English)**, and Arabic-aware
safety rules. Late payments are one of the most common cash-flow problems for small and medium businesses. Chasing them is
repetitive work that people put off, and doing it badly costs money twice: a payment reminder sent to someone
who already paid, or an aggressive email to a key account, damages the relationship. A collections agent is a
good fit for self-improvement because **the outcome is objective** (did they pay?). That gives the learning
loop a real signal instead of an LLM grading itself.

## The product

An Arabic-first app (with an English toggle) for **non-technical office staff**, with three modes chosen on the
welcome screen: **collections employee**, **business owner / manager**, and **accountant** (several client businesses).

| Welcome (Arabic, RTL) | Approvals inbox: the assistant asks before risky emails |
|---|---|
| ![Welcome](docs/screenshots/welcome-ar.png) | ![Approvals](docs/screenshots/approvals-ar.png) |
| **Owner overview** | **What the assistant learned** (rules in plain Arabic, before/after tests, one-click apply) |
| ![Owner summary](docs/screenshots/owner-summary-ar.png) | ![Learning](docs/screenshots/what-i-learned-ar.png) |

Technical proof for reviewers (learning curve, guardrail lab, traces) lives at **`/judges`**:
![Judges dashboard](docs/screenshots/judges-dashboard.png)

## Try it in 3 minutes

Requirements: Python 3.11+ and [uv](https://docs.astral.sh/uv/getting-started/installation/)
(`curl -LsSf https://astral.sh/uv/install.sh | sh`).

```bash
git clone https://github.com/martinaarmanios21-dot/tahseel.git && cd tahseel
uv sync

# 1) Full learning loop in the terminal (no API key needed)
uv run revenue-agent --engine offline demo

# 2) Fill the app with realistic demo data (offline, free, ~5 s)
uv run revenue-agent seed-demo

# 3) The Tahseel app (Arabic UI) + technical dashboard
uv run revenue-agent --engine offline serve   # app: http://127.0.0.1:8000   ·   reviewers: http://127.0.0.1:8000/judges
# port 8000 busy? add --port 8080 (and open http://127.0.0.1:8080)
```

> **Tip for reviewers:** start with the offline engine. It is instant, deterministic, and doesn't use your free
> LLM quota. Free LLM tiers can return "overloaded" or "quota exceeded" at busy times; the agent retries and falls
> back (see [docs/EVALS.md](docs/EVALS.md#live-run-with-a-real-free-llm-gemini-3-oct-2026)).

**Optional free LLM brain (Gemini):** copy `.env.example` to `.env` and paste a free
[Google AI Studio key](https://aistudio.google.com/apikey) after `GEMINI_API_KEY=`, then run
`uv run revenue-agent --engine api demo`. Models are tried in order (`gemini-3.5-flash`, then
`gemini-flash-latest`), then NVIDIA / OpenRouter if you add those free keys. Every call is hard-capped by
`RUN_LLM_CALL_CAP` / `DAILY_LLM_CALL_CAP`, and if every provider is down the agent falls back to the offline brain.

**Optional Hermes brain:** with [Hermes Agent](https://github.com/NousResearch/hermes-agent) installed:

```bash
uv run revenue-agent hermes-setup            # creates an isolated Hermes profile "tahseel" pinned to free Gemini,
                                             # installs the skill, registers the MCP server
hermes -p tahseel mcp test revenue_agent     # should list 6 tools
uv run revenue-agent --engine hermes demo
```

The Hermes engine **refuses to run unless `HERMES_MODEL` is set**, and it uses its own profile with an explicit
provider. It can never fall back to a paid model from your default Hermes profile.

Run the tests with `uv run --group dev pytest -q` (30 tests: guardrails, idempotency, kill switch, budgets,
concurrency, retries/fallback, approvals, learning + gate).

## What a reviewer should try

In the **Tahseel app** (`/`):
1. Pick **صاحب العمل / المدير** (owner) → **ما تعلّمته** → open "تجربة التعلّم (للعرض)" → **practise**, then **learn**.
   A tested improvement appears with before/after numbers. Apply it.
2. Switch role → **موظف التحصيل** (employee) → **ابدأ يوم عمل جديد**. Approve or reject the emails waiting for you.
   Emails are in each customer's own language.
3. **المساعد** → pause the assistant (kill switch) and watch every action stop.
4. Toggle **ع / EN** and light/dark at any time.

In the **technical dashboard** (`/judges`):

1. **Dashboard → "Run 2 training episodes"**, then **"Learn"**. Watch the gate compare v2 to v1 and click **Promote**.
2. Click **v2** in *Skill versions* to see the diff the agent wrote to its own playbook.
3. **Guardrail lab**: paste your own prompt injection, replay a sent email, exhaust the LLM budget.
4. **Live portfolio → Next round**: key-account emails wait for your Approve/Reject.
5. Hit the red **Kill switch**, then try to run anything.

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

- Customers are **simulated**: 7 hidden personas with seeded behaviour. The simulator stands in for the email
  and accounting integrations a production deployment needs (Xero/QuickBooks/Stripe + SMTP). Everything above
  the simulator (guardrails, state, outbox, learning, gate) is production-shaped.
- The learner optimizes the reward of each round. That is why it sometimes escalates first-touch invoices for
  customers who never answer first emails. The gate scores whole episodes, so a candidate that does this
  still has to beat the active version on total outcome before it can be promoted.
- I verified the Hermes engine's MCP connection and tool discovery. Its decisions depend on the model you
  configure in Hermes.

## Front end

`frontend/` is the React app (designed in [Lovable](https://lovable.dev), then wired to the real API by hand).
The built files are committed in `revenue_agent/web/app/`, so **reviewers don't need Node**. To rebuild after
changing the UI: `bash scripts/build_frontend.sh`. The app falls back to built-in demo data (with a
"بيانات تجريبية" badge) only when no API server is reachable.

MIT licensed.
