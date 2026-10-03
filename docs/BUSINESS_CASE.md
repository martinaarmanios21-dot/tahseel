# Business case

## The problem
Small and medium businesses commonly carry a meaningful share of their revenue as overdue receivables. Chasing it is
manual, awkward and inconsistent: the same generic reminder goes to a cash-strapped café, a key enterprise
account and a customer who already paid.

## How the agent saves time
- Drafts, validates and sends every routine reminder; humans only see the cases that need judgment
  (disputes, key accounts, large amounts, injection attempts).
- Verifies "we already paid" claims against the ledger automatically.

## How it saves money and makes money
- **More cash collected, sooner**: in simulation, the self-learned skill recovered 84% of collectible money
  vs 24% for a generic firm-reminder policy on the same holdout portfolio.
- **Fewer lost customers**: complaints went from 12 to 0 once it learned to stop sending firm emails to key accounts.
- **Near-zero running cost**: batched decisions (≈ 3 LLM calls per 40-invoice round set) on free-tier models,
  hard-capped by budgets.

## Revenue model
| Plan | Price | For |
|---|---|---|
| Starter | 1,500 EGP / month | up to 200 open invoices, email channel |
| Growth | 4,500 EGP / month + 1% of recovered cash over 60 days overdue | accounting integrations, approvals in Slack/Telegram |
| Enterprise | custom | SSO, audit export, custom guardrails, on-prem models |

## Go-to-market
Accounting firms and bookkeepers who manage receivables for many SMB clients: one integration covers many
businesses. Start in shadow mode (the agent drafts, humans send) to earn trust, then enable auto-send for the
low-risk tiers only.
