# Tahsila metric reference (for the agent's reference files)

- **Outstanding** = balance column if present; else amount − amount paid; else 0 if paid/void; else full amount;
  minus payments confirmed in the app. Never below 0.
- **Overdue** = outstanding > 0 and due date before today (business time zone, default Africa/Cairo). Due today is
  not overdue.
- **Uncertain** = status contradicts balance, amount − paid ≠ balance, empty status, or partially paid without
  amounts. Excluded from totals and never contacted until verified.
- **Aging** = not yet due · 1–30 · 31–60 · 61–90 · 90+ days, on outstanding amounts.
- **Currencies** are always reported separately.
- **Disputed** invoices stay in totals (still owed on the books), are shown separately, and are never chased.
- **Confirmed collections** = payments dated inside the period (CSV amount_paid on its payment date, plus payments
  recorded in the app). Invoice amounts and sent reminders are never counted as collections.
- **Priority (0–100)** = days overdue (≤120)/120×50 + balance percentile within currency×30 + contact recency
  (never 20, ≥14 d 15, 7–13 d 5, <7 d 0).
- **Contact policy**: overdue only; not paid/void/disputed/do-not-contact/unclear; 7-day cool-down; maximum 3
  follow-ups; first contact always friendly; no legal threats, discounts, links or other customers' data; exact
  invoice ID and balance in the message; the customer's language; human approval of the exact text and recipient.
- **Strategy evaluation**: ≥30 contacts per arm with a completed 14-day window, two-proportion test at α=0.05,
  never automatic. Otherwise: insufficient evidence.
