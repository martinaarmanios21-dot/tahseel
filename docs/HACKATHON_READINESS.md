# Hackathon readiness: Ribhiya (ربحية)

## Setup and run

```bash
uv sync
uv run revenue-agent serve                  # app: http://127.0.0.1:8000
# optional: .env with GEMINI_API_KEY=… (free) for AI wording; SMTP_* + EMAIL_SENDING_ENABLED=1 for real email
uv run pytest -q                            # backend tests
cd frontend && npx vitest run && cd ..      # frontend routing test
bash scripts/build_frontend.sh              # only if you change frontend/ (built app is committed)
uv run python scripts/make_test_pack.py     # fictional test files + step-by-step guide (docs/TEST_GUIDE.md)
```

## Judge walkthrough (about 5 minutes)

Use the test pack (`test-data/tahseela-test-pack/`, files numbered 01–18 in the order you use them) and follow
[docs/TEST_GUIDE.md](TEST_GUIDE.md). In short:

1. Home → **Start a new investigation**. **Do this now** asks three short questions, then for the sales file.
2. Upload files 01–04 (CSV with Arabic headers, a text PDF, a 3-sheet Excel). Ribhiya notices September has no
   shipping invoice and **asks for it, with why**, instead of reporting a false saving.
3. Upload 05 (courier statement). **What I found** shows the biggest leak per order with one chart; **Explain** shows
   the evidence and options; the **Products** tab shows profit per product and the orders that lost money.
4. **Get cheaper prices** → a supplier quote request with `[[placeholders]]`; approve the exact text; send (SMTP) or
   copy. Add the supplier quotes (08–10) in **Suppliers**: only equivalent specs are compared, minimum-order extra
   units are costed.
5. **What if** → packaging 13.5 → a labelled projection; save it as an experiment. **Results** → after uploading
   October (11–13) it reports the observed change, without claiming the change caused it.
6. **Chat with Ribhiya** (bottom corner): tour, business concepts, solutions, feedback.
7. Header → **Emergency stop**: sending is refused while it is on. Toggle **EN / ع** at any time.

## Supported input

CSV, Excel (every sheet) and PDFs with a text layer (no OCR), up to 10 MB per file and 10 files at once. Sales or
orders (date, product, quantity, price), product costs, expense/supplier invoices, courier statements and returns
are detected from their columns (English or Arabic headers). Anything unclear asks the owner to confirm the columns,
and a confirmed layout is remembered.

## Acceptance criteria: status with evidence

| # | Criterion | Status | Evidence |
|---|---|---|---|
| 1 | Owner can upload real files in common formats | ✅ | `profit/ingest.py`; `test_csv_detection_and_validation`, `test_xlsx_multiple_worksheets_each_detected`, `test_text_pdf_table_extracted_and_scanned_pdf_refused`; browser-tested via the page's file input |
| 2 | Bad files and values are reported, never silently used | ✅ | `test_malformed_and_unsupported_files_fail_clearly`, `test_missing_ambiguous_duplicate_and_bad_values`, `test_same_file_twice_is_not_double_counted` |
| 3 | Figures are deterministic and traceable | ✅ | `profit/metrics.py`, `profit/orders.py`; `test_bridge_components_sum_exactly_to_change`, `test_reconciles_with_monthly_metrics_exactly`, `test_currencies_never_combined` |
| 4 | Missing evidence is requested in context, not guessed | ✅ | `test_missing_invoice_month_triggers_gap_question_not_a_false_finding`, `test_missing_shipping_triggers_request_with_question_and_alternative`, `test_dont_know_is_never_asked_again_and_analysis_continues` |
| 5 | Supplier outreach only when a finding justifies it, sent only with approval | ✅ | `test_packaging_finding_creates_quote_action_and_outreach_needs_a_reason`, `test_outreach_cannot_be_sent_without_explicit_approval_of_exact_text`, `test_without_email_integration_it_is_a_draft_not_a_send`, `test_with_smtp_sends_once_and_records_provider_result` |
| 6 | Quotes compared fairly | ✅ | `test_quotes_compare_only_confirmed_equivalent_specs_with_total_cost`, `test_reply_quotes_link_to_outreach_and_non_equivalent_specs_stay_apart` |
| 7 | Projections are never reported as savings | ✅ | `test_baseline_saved_and_projection_never_becomes_result`, `test_projection_never_becomes_observed_or_verified_without_new_records`, `test_mix_change_or_few_orders_is_not_attributed` |
| 8 | AI never invents figures or acts | ✅ | `test_advisor_rules_mode_and_grounding_checks`, `tests/test_security.py` (redaction, failures, invented figures, emergency stop) |
| 9 | Businesses are isolated | ✅ | `test_api_full_workflow_and_tenant_isolation`, `test_07_access_control_and_tenant_isolation_over_http` |
| 10 | Egyptian Arabic and English | ✅ | `frontend/src/i18n/*`; explanations checked in both languages (`test_explanation_numbers_match_calculations_in_both_languages`); RTL verified in screenshots |
| 11 | No remote Git operations | ✅ | No commits, pushes, PRs or deploys were made |

## Test and build results (2026-10-10)

- `uv run pytest -q` → **134 passed**.
- `npx tsc --noEmit` (frontend) → no errors. `npx vitest run` → 2 passed. `bash scripts/build_frontend.sh` → success.
- Headless-Chrome checks: home, investigation, upload through the page's file input (CSV, PDF, Excel), the guide's
  "Show me" navigation, and a 404 page for old collections URLs.

## Remaining risks and known limitations

- **Email:** SMTP tested only with fake servers. Send one test email to yourself before relying on it.
- **AI wording:** free tiers can rate-limit (the app then answers from the calculations and says so). Prose isn't
  fully verified; figures are checked.
- **Single-user:** no accounts. Set `ADMIN_TOKEN` before any shared deployment.
- **No connectors or OCR:** files are uploaded by hand; scanned PDFs are refused with a clear message.
- **Collections removed:** the former invoice-collections workflow was removed on 2026-10-10 (see README).
