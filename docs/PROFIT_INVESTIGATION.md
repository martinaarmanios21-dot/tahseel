# Ribhiya profit investigation

**Positioning:** AI Profitability & Cost-Leakage Specialist for product-based SMEs.
"Discover where your profit is leaking, understand why it is happening, and measure whether your next decision
actually improves the business."

Overlap, stated honestly: accounting, expense-tracking, analytics and pricing agents on marketplaces such as Wesam.ai
(its public pages list Finance and Data & Analytics categories, and agents that reconcile uploaded exports) cover
parts of this. The marketplace was reviewed only from its public pages on 2026-10-10 and was not re-inspected in depth
for this release. The difference we aim for is the integrated workflow below and measured results, not any single
feature. We make no "no competitors" claim.

## The workflow that works today (UI → API → data → back)

1. **Start** (`/`): name and currency → `POST /api/investigations`.
2. **Guided questions** (`/investigation/<id>`, "Next step" card): one question at a time from
   `diagnosis.next_questions`. Options can be answered, skipped, or marked "I don't know". Questions that were
   answered or skipped are never asked again. Profile answers can be remembered (owner-confirmed memory).
3. **Files**: multiple CSV / XLSX (every worksheet) / text-based PDF files per upload → `POST .../files`.
   `profit/ingest.py` finds the header row, detects the record type (sales lines, product costs,
   expenses/supplier invoices, returns), maps columns, and validates each row. Bad rows are rejected with row-level
   reasons; duplicates are skipped; dates are parsed day-first with a warning when ambiguous; currencies are
   checked; expense categories are inferred from the description only when no category column exists (and flagged
   for review). The same file is never imported twice. Unclear tables ask the owner to choose the type and map
   columns ("Fix columns"). A confirmed mapping is remembered for that report layout. Scanned PDFs are refused with
   a clear message (no OCR), and the owner can type monthly totals instead (stored as `manual_entry`).
4. **Calculation**: `profit/metrics.py` is the single source of every formula (definitions at the top of the file and
   in `/api/investigations/<id>` → `definitions`): net sales, COGS with coverage, gross margin, variable costs
   (packaging, shipping, payment and marketplace fees), contribution and its margin, marketing, fixed costs,
   operating profit (flagged incomplete unless every input exists), per-order values, AOV, return rate, break-even
   orders, paid vs unpaid expenses, payables. Money is integer minor units, per currency, never combined. A ratio is
   `None` (not 0) when its input is missing or its denominator is zero.
5. **Diagnosis**: `metrics.contribution_bridge` splits the change in contribution per order between two months
   exactly into price/mix, discounts, refunds, product costs, packaging, shipping and fees (the residual is 0 by
   construction). A driver becomes a **finding** only if it is material (≥1% of net sales per order) and its data
   exists in both months. It is **supported** with ≥30 orders per month and complete data, and **preliminary**
   otherwise. When data exists in only one month (e.g. a missing September packaging invoice), it becomes a
   **data-gap question**, not a finding. Missing categories are listed as **untested**, never as causes.
6. **Explanation**: five parts per finding (what, why, evidence with record counts/files/rows and invoice unit prices,
   options, next step), templated in Egyptian Arabic and English from computed numbers only.
7. **Charts** (Recharts, palette validated for colour-vision deficiency): sales vs what you keep by month, cost per
   order by category, a waterfall of what changed each order's margin, and product margin. All read the same
   `metrics.compute` output; each shows period, currency, an "estimated" note and a table view.
8. **Recommendations**: quality-aware options per driver (verify the invoice, comparable quotes on the same
   specification, small pilot with quality measures, keep and reprice…). The projection is always labelled as an
   estimate with its assumptions. No supplier names, prices or quotes are ever generated.
9. **Baseline → verification** (`profit/tracking.py`): "I'll try this" saves the baseline (current month's per-order
   cost, orders, AOV, return rate, product mix). The owner marks the start date (owner-reported). After new files
   arrive, "Check the result" compares orders dated after the start with the baseline. Outcomes:
   `awaiting_data` (fewer than 30 orders), `inconclusive` (AOV moved more than 15%, the top product's share moved more
   than 15 points, missing cost records, or returns rose), `verified_improvement` (≥5% better with none of those), or
   `no_measurable_improvement`. Even when verified the wording is "observed after the change; causation not proven".
   Projections never become results.
10. **Ask Ribhiya** (in Chat with Ribhiya, inside the investigation): questions about the numbers are answered by Hermes,
    the API LLM, or the computed findings (see below); next-step, missing-evidence and fix questions come from the state.

## Order-level profit (`profit/orders.py`)

Each order (non-cancelled sales lines grouped by order ID, one currency):
`net sales + delivery fee the customer paid − refunds − product cost − packaging − shipping − payment fees − marketplace fees`.

| Cost | How it reaches an order | Label |
|---|---|---|
| Product cost | units × the product's unit cost | actual; **missing** if the product has no cost (the order's profit is shown as missing, never as zero) |
| Refunds | returns-file rows with this order ID (or lines marked returned when there is no returns file) | actual |
| Shipping / payment / marketplace / packaging rows **with an order ID** (courier or gateway statements) | to that order | **actual** |
| The same categories **without** an order ID (monthly invoices) | shared only across that month's orders with no actual cost in that category: packaging and shipping **equally per order** (one package or shipment per order); payment and marketplace fees **by order value** | **allocated (estimate)**, shown on each order; the owner can switch any category to "don't allocate" |
| Rent, salaries, subscriptions, other, marketing, material purchases | never allocated to orders (no per-order driver) | n/a |

- **No double counting:** orders with an actual cost aren't charged again from the monthly pool.
- **Exact splits:** allocations add up exactly to the invoice total (largest-remainder rounding).
- **Unmatched rows:** a cost or refund row whose order ID isn't in the sales file is listed and charged to no order.
- **Reconciliation:** shown in the UI and tested: Σ order profit (known costs) − unallocated costs − costs and refunds for unknown orders = the monthly contribution from `metrics.py`.
- **Product view:** an order's shared costs, delivery income and unassigned refunds are split across its lines by line value (labelled).
- **Channel view:** results grouped by sales channel.
- **Plain-language insights:** e.g. "your top-selling product leaves the least per unit", "N of M orders lost money", and an allocation notice.

## What-if simulator (`profit/simulator.py`)

The simulator re-runs one real month's complete orders on **copies** of the rows (stored records are never touched)
with the levers the data supports:
- price % (all products or one product)
- new product unit cost (e.g. another supplier)
- packaging per order and shipping per order (only when that cost exists in the month)
- discount % of price
- return rate %
- free-shipping threshold plus the fee below it (only when the sales file has customer delivery fees)
- the owner's own guess for order-volume change %

Unsupported levers are disabled with the reason. Every result is labelled a projection and lists its assumptions:
- demand is unchanged unless a volume change is set
- payment fees stay a percentage of order value
- which items stay unchanged
- whether allocated costs are involved
- how many orders were left out because a product cost is missing

A scenario can be saved, and "save as an experiment" turns it into a tracked intervention (baseline = that month's
actual per-order figure, projection = the scenario). The existing verification then decides the result from later
records.

## Supplier quote comparison (`profit/quotes.py`)

- **Inputs:** the owner enters quotes they received: comparison group, the specification as written, unit price,
  minimum order quantity, setup and delivery fees, payment terms, lead time, quality notes, source.
- **What is compared:** only quotes the owner confirmed as real *and* with the specification confirmed as equivalent.
  Web listings are shown as "published price, not a quote" and are never compared.
- **Equal basis:** every quote is costed for the same quantity (the latest month's orders for packaging and shipping,
  or a quantity the owner enters). The minimum order quantity can force extra units, and those are costed and flagged.
- **Unknown terms:** stay "unknown", and totals that lack delivery or setup fees are marked as lower bounds.
- **No winner by price alone:** results are ranked by cost per unit actually needed, with quality, lead time and terms
  shown next to it. "Test in simulator" feeds a quote's effective unit cost into a labelled projection.
- **No outside data:** nothing is fetched from the internet and no supplier detail is generated.

## Evidence, supplier outreach and quotes as evidence (one loop)

**Before this change:**
- Document requests were a fixed list in `next_questions`.
- **No supplier outreach existed.** The only email feature was customer collections follow-ups (collections has since been removed).
- Quotes could only be typed in by hand, and weren't linked to findings or the simulator (except packaging and shipping).

**Evidence register (`profit/evidence.py`)**, derived from the investigation (never stored separately):
- **Each item:** label, business question it answers, what triggered it, alternative if unavailable, optional flag.
- **Statuses:** `missing`, `awaiting_confirmation` (unclear table, inferred categories, a month without invoices),
  `processed`, `unavailable` ("I don't have it") or `skipped`.
- **Document requests** in the Next-step card come only from `missing` items. Required items come first, and nothing
  is asked twice.
- **Triggered requests:**
  - a courier statement *by order number* only when shipping exists but isn't linked to orders **and** it matters
    (loss-making orders or a shipping finding)
  - a payment statement by order only when payment fees exist but aren't linked to orders **and** the same condition
    holds (loss-making orders or a payment-fee finding)
- **Unavailable or skipped evidence never blocks the analysis.** The affected figures stay "untested" or "estimated",
  never zero.

**Action plan (`profit/actions.py`)**: each action shows its trigger, why, expected evidence or outcome, impact (only
the finding's labelled projection), and the next step:
- missing evidence → upload
- cost finding (packaging, shipping, product costs) → request supplier quotes
- request sent or copied → add the supplier's quote
- two or more confirmed comparable quotes → compare, then test in the simulator
- MOQ forcing extra units → ask about smaller quantities
- saved scenario → track as an experiment
- started change → upload new records, then check the result

No finding and no evidence gap means no actions (tested).

**Supplier outreach (`profit/outreach.py`)**:
- **Only allowed** for a current cost finding (`quote_request`), or a quote whose MOQ forces extra units
  (`moq_question`). Otherwise the request is refused with `no_business_reason`.
- **Brief first:** what is sourced, specification, quality requirements, quantity (from orders, a suggestion only),
  terms to ask about, business and contact names, supplier name and email.
- **Draft text:** deterministic Egyptian Arabic or English. Unknown facts stay as `[[placeholders]]`, internal costs
  are never included, and every draft says "request for quotation, not a confirmed order".
- **Before approval:** placeholders and purchase-commitment wording block approval.
- **Approval:** binds the exact recipient, subject and body. Any edit drops the approval.
- **Sending:** uses the **existing SMTP mailer**, only with a configured server, a supplier email address, and the kill
  switch off. Each request can be sent only once, and a timeout mid-send is recorded as `send_unknown`.
- **No SMTP configured:** sending is refused with "it has NOT been sent". The owner copies the text and can record
  "I sent it myself" (`copied_manual`, unverified).
- **Replies:** never collected automatically. Adding a quote linked to the request sets `reply_reported`.

**Quotes as evidence (`profit/quotes.py`)**:
- **Read values from the quote document:** text-based PDF, CSV/TXT or XLSX. Suggests unit price, MOQ, setup and
  delivery fees, lead time and payment terms, each with the text it came from. **Nothing is saved** until the owner
  checks the values and adds the quote. A field kept as read is stored as `extracted_confirmed`, otherwise `typed`.
  Values not found stay unknown. No OCR.
- **Linking:** a quote can be linked to the request it answers, and (for product quotes) to the sold product it would
  replace. A linked product quote feeds the simulator's unit-cost lever; packaging and shipping quotes feed the
  per-order levers.
- **Comparison rules are unchanged:** only owner-confirmed quotes with a confirmed equivalent specification, and web
  prices are never quotes.

**Value types** stay distinct throughout:
- confirmed historical figures (from files)
- allocated estimates (marked on orders)
- supplier-quoted values ("Supplier-quoted" badge)
- projections (simulator and finding projections, always labelled)
- observed post-change results and verified improvements (tracking, "causation not proven")

## Arabic invoice OCR: evaluated, deferred

- **Tesseract:** not installed here. Arabic printed-invoice accuracy is poor without tuned models, and it gives no
  field structure.
- **A vision LLM (Gemini via the existing key):** structurally feasible, but:
  1. It sends customer documents to a third party (needs explicit owner consent).
  2. A model can produce plausible but wrong numbers, so every field needs one-by-one confirmation against the image
     before it can enter calculations.
  3. Free-tier quotas make it unreliable for a live demo.
  4. Its accuracy can't be measured with offline automated tests (only mocked).
- **Decision:** the confirmation UX plus a labelled accuracy test set is a sprint of its own, so building it now would
  risk destabilising the core workflow. Scanned PDFs keep being refused with a clear message and the manual-entry
  alternative.
- **Planned design:** extract into "unconfirmed" records that are excluded from every calculation; the owner confirms
  each field next to the image crop; only confirmed fields become records with `source=ocr_confirmed`; measure
  accuracy on a labelled set of real Egyptian invoices before claiming support.

## Hermes Agent integration (genuine, verified locally)

- **What runs:** Hermes Agent v0.21.5 (Nous Research), one-shot (`hermes -p tahseela --skills tahseela-profit -z …`),
  as a separate process invoked by `profit/advisor.py`. Hermes is the advisor runtime; the deterministic engine
  remains the source of every number.
- **Least privilege:** `uv run revenue-agent hermes-setup-profit [--tenant X]` clones the project's `tahseel`
  profile into `tahseela` (or `tahseela-X`). It disables **every built-in toolset except `skills`** (terminal, file,
  code execution, web, browser, memory, delegation, cron… are all off; `prompt-size` confirms 3 tool schemas) and
  excludes the write and simulation MCP tools. It refuses to mark the profile safe if anything is still enabled.
  The advisor uses Hermes only when that marker exists for the exact tenant.
- **Tools Hermes can call:** `profit_list_investigations`, `profit_get_investigation`, `profit_definitions`,
  `profit_business_context`. All read-only and served by `mcp_server.py`.
- **Isolation:** the tenant is pinned in the profile's MCP server `env` (`MCP_TENANT`), so neither the prompt nor the
  model can choose another business. One Hermes profile per business keeps Hermes' own state separate too. Hermes
  does not pass the caller's environment to MCP servers; a run before pinning returned "not found" (fail closed).
- **Skill:** `skills/tahseela-profit/SKILL.md`, installed into the profile by the setup command.
- **Verified:** a live run answered in Egyptian Arabic using `profit_get_investigation`, with no figure outside the
  computed state (grounding check). It took about 168 s and 3 Gemini calls on the free tier. Output is still
  sanitised (secrets, system text) and number-checked by Ribhiya.
- **Not used:** Hermes' built-in memory (`MEMORY.md`/`USER.md`) is disabled for this profile, because it would store
  model-written text without an approval gate. Persistent learning lives in Ribhiya's governed memory below.
- **Known issue (pre-existing):** the simulation lab's `tahseel` profile still has broad toolsets enabled. Lock it
  down or avoid `--engine hermes` for the simulation lab (see Remaining risks).

## Bounded learning (governed memory, `profit/memory.py`)

| Kind | Written by | Used for |
|---|---|---|
| `mapping` | owner confirming a column mapping | reused automatically for the same report layout (header signature); `uses`/`corrections` are counted, and a mapping corrected more often than it is reused is retired automatically |
| `fact` / `preference` | owner ("remember this") | business context for the advisor (`profit_business_context`) |
| `outcome` | a **verified** intervention result only | evidence of what worked here (accepted recommendations are not outcomes) |

Model output and uploaded text can never write memory (enforced in code: only `owner_confirmed` and
`verified_outcome` sources are accepted). Everything is per tenant and can be retired (rollback) from the UI.
The measurable signal is the mapping acceptance rate (`/api/memory` → `mapping_reliability`). The procedure itself
(the `tahseela-profit` skill and the diagnosis rules) does not self-modify: changes are code-reviewed and covered by
tests.

## Judge walkthrough (about 10 minutes, offline is fine)

```bash
uv sync && uv run revenue-agent serve       # http://127.0.0.1:8000
```
1. Click **Start a new investigation**. Answer or skip the first question.
2. Upload a sales/orders export, a product-cost list, and expense or supplier invoices (CSV/XLSX/PDF) for at least
   two months. Test-only fixture generators are in `tests/profit_fixtures.py`, e.g.
   `uv run python -c "import sys; sys.path.insert(0,'tests'); from profit_fixtures import *; open('/tmp/s.csv','wb').write(sales_csv()); open('/tmp/c.csv','wb').write(costs_csv()); open('/tmp/e.csv','wb').write(expenses_csv())"`.
3. Read the import summary and the next question (it will be about the actual finding). Open **Issues** on a file;
   try an unsupported file or a file with bad rows.
4. Read the finding (five parts), open **Show the numbers** under the charts, and try **Explain this more**.
5. Click **I'll try this**, set a start date, upload a later month, and click **Check the result**
   (`expenses_csv(months=("2026-10",), box_qty=(70,), box_price=(12,))` + `sales_csv(months=("2026-10",), orders=(70,))`).
6. **Order profit** section: read the insights, switch tabs (products, channels, orders that lost money; each cost on
   a losing order says *actual* or *allocated*), open "How monthly invoices are shared…", change packaging to
   "Don't allocate", and watch the reconciliation stay ✓.
7. **What if I change…?**: e.g. packaging per order = 12, then Calculate. Check the baseline vs projection table and
   the assumptions. Try "Change price +5%" with and without a volume guess, then "Save as an experiment to measure".
8. **Compare supplier quotes**: add two written quotes for the same group (one with a minimum order of 500), mark
   both confirmed, add a web price, then Compare and Test in simulator.
   For per-order actual costs, upload a courier statement with an `Order ID` column (see the order-profit
   test data in `tests/test_orders_sim.py`).
9. **Action plan → supplier request**: on a packaging (or shipping/product-cost) finding click "Prepare supplier
   request", fill in the brief (placeholders block approval), choose the email language, approve, then send (only with
   SMTP) or copy and "I sent it myself". Add the supplier's reply as a quote linked to the request ("Read values from the
   quote document" can prefill it). With two confirmed comparable quotes the plan offers Compare → Test in simulator; a
   minimum order quantity above your needs offers "Ask about smaller quantities".
10. Ask Ribhiya a question (rules mode offline; LLM with `GEMINI_API_KEY`; Hermes after
   `uv run revenue-agent hermes-setup-profit` and `PROFIT_ADVISOR_ENGINE=hermes`).
11. Toggle EN/ع (RTL/LTR) at any time.

## Limitations

- No OCR. Old `.xls`, `.docx` and images are refused with a clear message. PDF tables are recovered only when
  text lines are consistently delimited.
- Monthly periods only. Expenses are attributed by invoice date (accrual); a supplier bill paid in bulk for several
  months will look like a one-month spike (the gap question helps catch this).
- COGS is not reduced for returned items (assumed not resold). Allocation of shared costs to products is not done;
  product margin is shown before packaging, shipping and fees.
- One currency is diagnosed at a time (the one with the most sales); others are still computed separately.
- Hermes answers are slow on free tiers (about 1–3 minutes). The API or rules engines answer in seconds.
- Verification uses fixed thresholds (30 orders, 5%, 15%) and is not a statistical test; it reports
  "inconclusive" rather than guessing.
- No supplier research or outreach, no continuous monitoring, and no forecasting.
- Order profit is computed for the main currency only. The simulator works on one month and has no demand model:
  volume changes are the owner's own assumption. Quote comparison assumes one packaging unit per order when it
  derives the quantity from orders (stated on screen).
- Customer delivery fees are counted once per order (the largest value on its lines), because exports differ.
- Supplier email is only as real as your SMTP configuration: without it everything is a copyable draft. Replies are
  added by the owner; there is no inbox integration. Quote-document reading is pattern-based on text (English/Arabic
  labels such as "Unit price", "سعر الوحدة", "MOQ", "أقل كمية") and will miss unusual layouts; scans need OCR (not
  supported).
- Sending a supplier email from a shared server uses that server's SMTP identity: decide whether supplier mail should
  go out under the business's own address before enabling it (product-owner decision).
