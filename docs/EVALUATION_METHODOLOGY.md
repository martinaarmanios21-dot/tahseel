# Evaluation methodology

> **Status (2026-10-10):** the collections workflow described in sections 1–4 (imported invoices, overdue
> metrics, strategy evaluation) was removed from the app. Those sections are kept as a record. The numbers Ribhiya
> shows now are defined in [PROFIT_INVESTIGATION.md](PROFIT_INVESTIGATION.md); section 5 (simulation lab) still applies.

This document defines every number Ribhiya shows, the data each one comes from, and what the numbers can and
cannot prove. There are two completely separate parts:

1. The real-data workflow: the user's imported invoices. This is what judges and users interact with.
2. The simulation lab: fictional customers used to test learning and guardrails. Its numbers are never shown in
   the main app and are never presented as business results.

---

## 1. Data sources and separation

| Source | Where it lives | Shown in the main app? |
|---|---|---|
| User-uploaded invoice CSV | `datasets`, `ledger_invoices` tables | Yes, this is the only data the app uses |
| Outcomes the user records in the app (payment confirmed, reply, dispute, complaint, opt-out, other-channel contact) | `ledger_events` | Yes |
| Follow-ups drafted, approved, sent or reported as sent | `followups` | Yes |
| Audit log of every import, draft, approval, block, send, outcome and kill-switch change | `audit_log` | Yes (Strategy & audit page) |
| Test-only sample file `docs/samples/sample_invoices_TEST_ONLY.csv` (every ID starts with `SAMPLE-`) | Imported like any CSV, but the dataset is marked `kind=sample` | Only if the user imports it. A banner then says "البيانات دي للاختبار فقط، ومش بتمثل معاملات حقيقية" and real email sending is disabled |
| Automated test fixtures | Inline in `tests/test_ledger.py`; each test gets its own temporary database (`tests/conftest.py`) | Never |
| Simulation lab (`simulator.py`, tables `runs`, `invoices`, `outcomes`, `actions`) | Same SQLite file, separate tables | No, only on `/judges`, labelled as synthetic |

Nothing in the real-data code path generates, seeds or imputes invoices. With no import, the app shows an empty
state that asks for a file.

## 2. Import validation (what is rejected and what is flagged)

A row is **rejected** (reported with row number, column, code and value, and never silently dropped) when:
- the invoice ID is empty or has unsupported characters;
- there is neither a customer name nor a customer ID;
- the amount is missing, not a number, negative, zero, or has more decimals than the currency allows;
- the due date is missing or unparseable, a year is implausible, or the due date is before the issue date;
- the currency or status is unknown;
- the amount paid or the balance is larger than the invoice amount;
- the same invoice ID appears again with different data (**all** occurrences are rejected because we cannot
  choose between them). An exact duplicate row is skipped with a warning.

A file with rejected rows is only imported if the user explicitly ticks "import only the valid rows". Otherwise
nothing is saved. A downloadable error CSV is produced, with formula-injection cells neutralised.

A row is **imported but flagged** (warning) for: contradictory status vs balance, amount − paid ≠ balance, empty
status, partially paid without amounts, a payment date on an unpaid invoice, an invalid email (not used), an
ambiguous day/month date, or a defaulted currency or language. Dataset-level assumptions (no currency column, no
payment-status columns, day-first dates) are stored with the dataset and shown in the UI.

## 3. Deterministic financial metrics

All implemented in `revenue_agent/ledger/analysis.py`. No LLM is involved in any number.

| Metric | Definition |
|---|---|
| **as_of** | Today in `BUSINESS_TZ` (default `Africa/Cairo`). It can be pinned with `AS_OF_DATE` for reproducibility. |
| **Outstanding (per invoice)** | The `outstanding` column if given; else `amount − amount_paid`; else 0 for status paid/void; else the full amount (recorded as an assumption). Payments confirmed in the app are then subtracted. Never below 0. Void invoices are always 0. |
| **Balance basis** | Which of the rules above produced the outstanding figure. Shown on every invoice. |
| **Uncertain** | Status/balance conflict, balance mismatch, empty status, or partially paid without amounts. Uncertain invoices are **excluded from all totals**, listed separately with their amounts, and cannot be contacted. |
| **Overdue** | Outstanding > 0 **and** due date < as_of. Due today is *not* overdue (it is counted under "due today"). |
| **Days overdue** | `as_of − due_date` in days for overdue invoices, else 0. |
| **Aging buckets** | not yet due (includes due today), 1–30, 31–60, 61–90, 90+ days, on outstanding amounts. |
| **Total outstanding / overdue** | Sum per currency over non-void, non-uncertain invoices. **Currencies are never added together** (no FX conversion is available). |
| **Disputed** | Included in the totals (still on the books) and also reported separately. Never recommended for collection contact. |
| **Customer balances** | Grouped by customer ID (else normalised name) **and** currency. |
| **Confirmed collections in a period** | Payments whose payment date falls in the period: the CSV `amount_paid` on its `payment_date` (or the full amount when status is paid with a payment date), plus payments confirmed in the app. Each payment record is counted once. Paid invoices without a payment date are reported separately, not guessed. An invoice amount is never counted as a collection, and a sent reminder is never counted as a payment. |
| **Priority score (0–100)** | days overdue (capped at 120)/120 × 50 + percentile of outstanding within the same currency × 30 + contact recency (never contacted 20, ≥14 days 15, 7–13 days 5, <7 days 0). Every component is shown. |

### Recommendation rules (first match wins)

void → none · uncertain → verify payment status · paid → none · suspicious instruction-like text in notes → human
review · disputed → resolve dispute (no contact) · do-not-contact → none · not yet overdue → wait · contacted
less than `CONTACT_COOLDOWN_DAYS` (7) ago → wait · `MAX_TOUCHES` (3) follow-ups recorded → owner call · first
contact → **friendly** reminder (always, whatever the amount or age) · >60 days overdue after ≥2 follow-ups → firm
but polite · otherwise → neutral follow-up.

## 4. Strategy evaluation on real outcomes (`revenue_agent/ledger/strategy.py`)

- **Unit:** one contact attempt, meaning a follow-up with status `sent` (SMTP server accepted it) or
  `manual_reported` (the user says they sent it; counted but labelled unverified).
- **Outcome:** a confirmed payment dated within **14 days** after the contact (`paid_in_window`). If the window has
  not closed and nothing was paid yet, the outcome is **unknown** (`pending_window_open`) and excluded from rates.
  Complaints, opt-outs, disputes and replies recorded inside the window are counted per arm.
- **Arms:** `policy_v1` (baseline templates) and `candidate_v2` (the same, plus an explicit request for an expected
  payment date). Assignment is a stable hash of the invoice ID, and only when `STRATEGY_EXPERIMENT=1`. The LLM
  never chooses the arm.
- **Decision rules:**
  - fewer than **30** contacts with a completed window in either arm → `insufficient_evidence`;
  - otherwise a two-proportion z-test at α = 0.05; Wilson 95% intervals are shown per arm;
  - candidate significantly better **and** no higher complaint/opt-out rate → `candidate_better_needs_human_review`;
    this is never applied automatically;
  - significantly worse → `candidate_worse_rejected`; more harm → `candidate_rejected_harm`; else keep baseline.
- **Attribution:** a payment after a message is association, not causation. Without the randomised experiment the
  arms are not comparable. The imported `last_contact_date`/`payment_date` columns are shown descriptively only,
  because the file holds just one contact and one payment date per invoice.
- **Current state of evidence:** no real outcome history exists in this repository. On any freshly imported
  dataset the evaluation returns `insufficient_evidence` and says so in Egyptian Arabic and English. That is the
  correct answer.

Policy blocks (paid, disputed, cool-down, wrong recipient, legal-threat wording, kill switch…) are counted from
the audit log as **blocked attempts**. They are evidence that the guardrails fired, not customer-facing
violations. By construction no message reaches a customer without passing the same checks at approval *and*
again at send time.

## 5. Simulation lab: what changed and the honest result

The earlier README claimed "84% cash collected vs 23.8%" after self-learning. An audit found three reward-hacking
problems:

1. An **agreed instalment plan was counted as collected cash** (`collection_rate` included `PLAN_AGREED`).
2. The learner **escalated first contacts to a human**: escalation earned +0.1 reward even on collectible invoices.
3. The learner **opened with a firm tone** on first contact for some segments.

Fixes:
- `collection_rate` now counts `PAID` only; `plan_agreed_rate` is reported separately.
- Wasted escalation earns 0.
- A deterministic constraint (`skills.covers_first_contact` / `first_contact_ok`) forbids escalation or a firm tone
  for any rule that can fire on a first contact with no customer signal. It is enforced both when the learner
  picks actions and when any candidate skill is validated (including LLM/Hermes proposals).

Result with the fixed metrics (`uv run revenue-agent --engine offline demo --yes`, train seeds 1–2, holdout seed
101, 40 invoices):

| | v1 seed skill | Learned candidates (3 attempts) |
|---|---:|---:|
| Cash collected (PAID only) | 23.8% | 14.4%, 14.4%, 3.2% |
| Agreed plans (not cash) | 0% | 85.6%, 85.6%, 96.8% |
| Complaints | 12 | 0 |
| Golden safety cases | 4/9 | 9/9 |
| Gate | – | **rejected**: cash collected regressed |

The learner is safer (no complaints, every safety case passes) but it learned to offer plans to everyone. That
trades real cash for promises, and the gate refuses to promote it. The active skill stays unchanged. **No improvement
is claimed.**

Simulation limitations: personas and reply behaviour are hand-written; one holdout seed of 40 invoices is
evaluated repeatedly across reflection attempts (repeated use of the same holdout is itself a mild form of
overfitting); the results say nothing about real customers.

## 6. Reproduce

```bash
uv run pytest -q                                   # 97 tests (ledger, guardrails, engine, API brain)
uv run revenue-agent --engine offline demo --yes   # simulation lab, numbers above (writes to DATA_DIR)
```
