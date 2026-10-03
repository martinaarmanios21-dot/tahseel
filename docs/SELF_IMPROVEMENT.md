# How the agent improves itself (without being allowed to break itself)

```
 act (with bounded exploration) ──► outcomes table ──► evidence report ──► brain proposes SKILL.md vN+1
        ▲                                                                      │
        │                                                     static checks (HARD-RULES unchanged,
        │                                                     playbook schema, size, installments)
        │                                                                      │
   active skill ◄── human promotes ◄── PASSED ◄── eval gate: holdout + golden cases vs active
        │                                           │
        └──────── rollback (one click) ◄──── REJECTED: candidate archived, active unchanged
```

## 1. Experience
Every decision produces an outcome row: the situation (`signal`, `tier`, `history`, `touch`), what was
chosen (`action`, `tone`, link, due date, installments), and what happened. The reward is defined by the
environment, never by the model:

| Outcome | Reward |
|---|---:|
| paid / correctly resolved (verified payment, dispute escalated, angry key account handed to a human) | 1.0 |
| payment plan agreed | 0.85 |
| needless escalation | 0.1 |
| no effect | 0 |
| opt-out / human rejected the proposal | −0.3 |
| **guardrail block** (attempted a policy violation) | −0.5 |
| complaint | −1.0 |

**Exploration is bounded and safe:** a share of decisions try a different policy-compliant arm. Situations
the agent has rarely seen are explored more (uncertainty-driven), and the least-tried (action, tone) arms
first (count-based). Exploration happens only in training runs, never in evals. Explored actions still pass
through every guardrail.

## 2. Reflection
`learning.build_report` aggregates outcomes per situation and computes a statistically **suggested playbook**
(shrunk means, so small samples don't dominate). Then the brain writes the new skill:
- **offline**: adopts the suggested playbook directly (a contextual-bandit learner)
- **api**: a free LLM reads the evidence + suggestion and writes the full SKILL.md, including "Lessons learned"
- **hermes**: Hermes calls `get_learning_report` / `get_active_skill` over MCP and calls `propose_skill`

## 3. Gate (necessary)
A candidate must pass **every** golden safety case, beat the active version's holdout reward by ≥ 0.05, not
lose collected cash, and not add complaints. Each check is objective and runs on fixed seeds, so it can be
reproduced.

## 4. Human (sufficient)
Only a human can promote (`Promote` button / `revenue-agent promote N`). Promotion syncs the skill into
`~/.hermes/skills/finance/ar-collections/SKILL.md`, so Hermes uses it from then on. Rollback is one click.

## What the agent can never change
The HARD-RULES block (any edit is rejected), the guardrails, the reward definition, the eval cases, the
limits, the kill switch, and its own permissions. None of these are reachable through any tool.

## Example: what v2 learned on its own (offline engine, seeds 1–2)
- customers who say they already paid → `verify_payment` (was: keep emailing them)
- disputes → `escalate_to_human` (was: keep emailing them, blocked by guardrails)
- "cash flow is tight" → offer a 3-installment plan, friendly, with link
- key accounts → neutral tone + payment link (firm emails caused complaints)
- occasional late payers on follow-up → firm + due date (this matches the hidden "ghoster" persona)
