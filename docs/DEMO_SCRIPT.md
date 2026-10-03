# Demo video script (about 2–3 minutes, Arcade)

## Before recording
```bash
cd ~/revenue-agent
uv run revenue-agent reset --yes                              # optional: start from a clean slate
uv run revenue-agent seed-demo                                # practice runs + tested improvement + today's work day
uv run revenue-agent --engine offline serve --port 8080       # instant + free (no LLM quota used)
```
Open http://127.0.0.1:8080 (Arabic app) and http://127.0.0.1:8080/judges (reviewer dashboard) in two tabs.

## Scenes
| # | Time | Screen | Say |
|---|---|---|---|
| 1 | 0:00 | Welcome screen (Arabic) | "Small businesses in Egypt lose cash to late invoices. Tahseel is an AI assistant that collects them, and it gets better at it on its own, safely." |
| 2 | 0:10 | Pick **صاحب العمل / المدير** → الملخص | "The owner sees where the money is: collected, still owed, handed to the team." |
| 3 | 0:25 | Teal callout + "المساعد يتحسّن" card | "The assistant practised, studied its results, and tested an improvement: collection from 24% to 84%, complaints from 12 to 0." |
| 4 | 0:35 | **ما تعلّمته**: before/after + rules in plain Arabic | "Every learned rule is a plain sentence: if a customer says they paid, verify first; if they dispute, hand it to a human; cash-flow problems get installments." |
| 5 | 0:55 | Click **طبّق التحسين** → confirm | "It passed all 9 safety tests, but nothing changes without a human. One click to apply, one click to undo." |
| 6 | 1:05 | Switch role → **موظف التحصيل** → مهامي | "Employees get an inbox. Big or important customers wait for approval." |
| 7 | 1:15 | An Arabic email card and an English one → **موافق، أرسِل** | "Emails are written in each customer's own language, with the exact amount in Egyptian pounds." |
| 8 | 1:30 | **العملاء** → open a customer with a red "suspicious" badge | "This customer tried to trick the assistant with hidden instructions. It was quarantined before any AI saw it." |
| 9 | 1:45 | **المساعد** → pause switch → red banner | "And there's always an off switch." |
| 10 | 1:55 | Toggle **ع / EN** and dark mode | "Arabic-first, English for everyone else." |
| 11 | 2:05 | `/judges` tab: learning chart, guardrail lab (Test injection, Replay email, Exhaust budget) | "Under the hood: guardrails written as code, not prompts. Idempotency, budgets, evals, versioned skills, all built on Hermes Agent." |
| 12 | 2:25 | Back to the owner summary | "Tahseel: it saves time, collects more, and only improves in ways you approve." |
