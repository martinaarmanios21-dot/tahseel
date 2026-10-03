# Demo video script (about 2 minutes, Arcade)

Before recording: `uv run revenue-agent reset --yes && uv run revenue-agent serve`, then open http://127.0.0.1:8000.

| # | Time | Screen | Say |
|---|---|---|---|
| 1 | 0:00 | Dashboard, empty | "SMBs lose cash to late invoices. This agent chases them, and it gets better at it on its own, safely." |
| 2 | 0:10 | Click **Run 2 training episodes** | "It starts with a generic, firm reminder skill. It works a portfolio of customers and explores safely." |
| 3 | 0:25 | Blue bars appear (~30–40%) | "The untrained skill collects about a third of the money and causes complaints." |
| 4 | 0:35 | Click **Learn** | "Now it reflects on the outcomes and rewrites its own Hermes skill." |
| 5 | 0:45 | Skill table: v2 `passed_gate`, cash 23.8% → 84.0%, safety tests 9/9 | "The new skill must beat the old one on a holdout portfolio and pass every safety case." |
| 6 | 0:55 | Click **v2** → diff | "Here's what it learned: verify payment claims, escalate disputes, offer plans to cash-strapped customers, go gentle with key accounts." |
| 7 | 1:10 | Click **Promote** | "A human approves every self-update. One click to roll back." |
| 8 | 1:20 | Guardrail lab: Test injection → quarantined; Replay → refused; Budget → stopped | "Guardrails are code, not prompts: injections are quarantined, duplicate emails refused, budgets enforced." |
| 9 | 1:40 | Live portfolio → Next round → approval queue → Approve | "Risky emails, such as key accounts, wait for a human." |
| 10 | 1:50 | Kill switch → red banner | "And there's always an off switch." |
| 11 | 1:58 | KPI tiles | "Collected: 24% → 84%. Complaints: 12 → 0. Built on Hermes Agent." |
