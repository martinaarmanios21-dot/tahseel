## PROMPT 1: Foundation, brand, Arabic RTL, data layer, welcome screen

Build the front end of **Tahseel (تحصيل)**, an AI assistant that collects overdue invoices for small and
medium businesses in Egypt. The assistant writes reminder emails to customers who owe money, learns from the
results which approach works, and asks a human before doing anything risky. **The people using this app are
non-technical office employees whose first language is Arabic.** Everything must be extremely simple,
calm, and self-explanatory. When in doubt, use fewer words, bigger buttons and fewer options per screen.

### Tech
React + Vite + TypeScript + Tailwind + shadcn/ui. No login. No external analytics. Build output must work when
served from the same origin as the API (`vite` base `/`). All API calls go through one module `src/lib/api.ts`.

### Brand
- Name: **تحصيل** (Arabic) / **Tahseel** (English).
- Logo: a **rounded square icon** (teal background, white abstract symbol: an arrow flowing into a simple
  wallet or coin, OR a stylised "T"), with the name **beside** it: "تحصيل" in Arabic mode, "Tahseel" in English mode.
  Make it an inline SVG component `<Logo />`, crisp at 24–40px.
- Feel: **calm and trustworthy, like a modern bank app.** Lots of white space, rounded cards (12–16px radius),
  soft shadows, no clutter, no gradients except a very subtle one on the logo.
- Font: **IBM Plex Sans Arabic** (Google Fonts, weights 400/500/600/700) for both Arabic and English.
- Colours (use CSS variables / Tailwind theme tokens, both modes required):

| Token | Light | Dark |
|---|---|---|
| background | `#F6F8FB` | `#0A1628` |
| surface (cards) | `#FFFFFF` | `#111F35` |
| border | `#E3E8EF` | `#1E2F4A` |
| text primary (navy) | `#0B1F3A` | `#E8EEF6` |
| text muted | `#5B6B82` | `#94A3B8` |
| primary (teal), buttons | `#0F766E` (white text) | `#2DD4BF` (navy `#0A1628` text) |
| primary soft background | `#E6F4F2` | `#123A3F` |
| navy (header/sidebar) | `#0B1F3A` | `#0D1B30` |
| success | `#15803D` | `#4ADE80` |
| warning | `#B45309` | `#FBBF24` |
| danger | `#B91C1C` | `#F87171` |

  All pairs above are tested at WCAG AA contrast. Status colours always come with an **icon + word**, never colour alone.

### Language, direction, numbers
- **Arabic is the default.** `<html dir="rtl" lang="ar">`. A toggle in the top bar switches to English
  (`dir="ltr"`, `lang="en"`). Remember the choice in localStorage.
- Use logical CSS (start/end, `ms-`/`me-`, `ps-`/`pe-`) so the layout mirrors correctly. Directional icons
  (arrows, chevrons) must flip in RTL.
- All UI text lives in `src/i18n/ar.ts` and `src/i18n/en.ts` (no hard-coded strings in components).
- **Numbers always use Western digits (0-9), even in Arabic.** Money: `195,375 ج.م` in Arabic, `EGP 195,375`
  in English (no decimals in the UI). Use `Intl.NumberFormat('en-US')` for digits in both languages.
- Arabic copy: simple Modern Standard Arabic, friendly and short. The assistant speaks in **first person like a
  helpful colleague** ("أرسلتُ تذكيراً لـ 3 عملاء وأحتاج موافقتك على اثنين").

### Theme
Light / dark toggle in the top bar (sun/moon icon), default = system preference, remembered in localStorage.

### Welcome screen ("who are you?")
First visit shows a centered welcome screen:
- Logo, then title **"أهلاً بك في تحصيل"** and subtitle **"مساعدك الذكي لتحصيل الفواتير المتأخرة. اختر دورك لنبدأ:"**
- **Three large cards** (icon + title + one-line description), easy to tap:
  1. 🧾 **موظف التحصيل**: "أراجع رسائل المساعد وأوافق عليها، وأتابع العملاء."
  2. 📈 **صاحب العمل / المدير**: "أتابع الأموال المحصّلة، وأوافق على تحسينات المساعد."
  3. 🗂️ **المحاسب**: "أتابع التحصيل لعدة شركات أتعامل معها."
- English: "Collections employee" / "Business owner / manager" / "Accountant / bookkeeper" with matching descriptions.
- Save the role in localStorage. A role switcher (small pill showing the current role) stays in the top bar.

### App shell (after choosing a role)
- Top bar: Logo · current role pill (click → switch role) · **assistant status pill** (green dot "المساعد يعمل" /
  red dot "المساعد متوقف") · language toggle (ع / EN) · theme toggle.
- Simple navigation with at most 4 items, depending on role (defined in prompts 2–4). On mobile, use a bottom tab bar.
- A small, quiet link at the bottom of every page: **"للمحكّمين: لوحة التفاصيل التقنية"** / "For judges:
  technical dashboard" → opens `/judges` in a new tab.

### Data layer (very important)
`src/lib/api.ts` exposes typed functions for the endpoints below. **Two modes:**
- **Live mode**: calls the real API on the same origin (`/api/...`).
- **Demo mode**: if `/api/summary` fails (e.g. in the Lovable preview), automatically use the mock data in
  `src/mocks/` (copy the JSON at the end of this file) and simulate actions in memory: approving removes the
  item from the inbox and marks the customer as "in progress"; "next round" changes 2–3 customers to paid; etc.
  Show a small grey badge "وضع العرض التجريبي / Demo data" in the top bar when in demo mode.

Endpoints (JSON):
| Method | Path | Use |
|---|---|---|
| GET | `/api/summary?business=` | home screen numbers, see sample |
| GET | `/api/decisions?business=` | items waiting for a human decision |
| POST | `/api/approvals/{decision_id}/approve` body `{"by":"<role>"}` | approve → `{"result":"executed" or "blocked_on_recheck"}` |
| POST | `/api/approvals/{decision_id}/reject` body `{"by":"<role>","reason":""}` | reject |
| GET | `/api/customers?business=&status=` | customer list |
| GET | `/api/customers/{invoice_id}` | one customer with `timeline` |
| GET | `/api/insights` | what the assistant learned (rules + before/after test results) |
| POST | `/api/skills/{version}/promote` | owner approves a learned update |
| POST | `/api/skills/rollback` | undo the last update |
| POST | `/api/kill` body `{"on": true or false}` | pause / resume the assistant |
| POST | `/api/workspace/new` body `{"size":18}` | start a new working day (new set of overdue invoices) |
| POST | `/api/workspace/next-round` | let the assistant do its next round of work (background job) |
| POST | `/api/train` body `{"episodes":2}` | demo: let the assistant practise (background job) |
| POST | `/api/learn` | demo: the assistant studies its results and proposes an update (background job) |
| GET | `/api/job` | background job status `{"status":"idle or running or done or error","name":...,"error":...}` |
| GET | `/api/businesses` | the 3 client businesses (accountant mode) |

After any POST that starts a job, poll `/api/job` every 1.5 s until `status` is `done` or `error`, then refresh
the data. While a job runs, show a friendly inline message: **"المساعد يعمل الآن…"** with a small spinner.
Errors are shown as plain sentences, never raw codes or stack traces.

### Translate every code (never show raw codes to users)
Customer `status` →
| code | Arabic | English | style |
|---|---|---|---|
| `needs_you` | ينتظر قرارك | Needs your decision | warning, hand icon |
| `waiting` | لم نتواصل بعد | Not contacted yet | muted, clock |
| `in_progress` | تم التذكير، ننتظر الرد | Reminded, waiting | primary, mail |
| `paid` | تم الدفع | Paid | success, check |
| `paid_by_plan` | اتفقنا على تقسيط | Payment plan agreed | success, calendar-check |
| `with_team` | مُحال لفريقك | Handed to your team | warning, users |
| `suspicious` | رسالة مشبوهة، أوقفناها | Suspicious reply, stopped | danger, shield |

Reply type `reply_type` → `none` (لا يوجد رد), `reply` (ردّ عادي), `cash_flow` (يواجه صعوبة في السيولة),
`dispute` (يعترض على الفاتورة), `paid_claim` (يقول إنه دفع), `angry` (غاضب من الأسلوب), `opt_out` (طلب إيقاف
المراسلة), `injection` (رسالة مشبوهة تحاول خداع المساعد).

Decision `why_code` (why a human must decide) →
`key_account`: "عميل مهم، أفضّل أن تراجع الرسالة قبل الإرسال" / "Key customer, I'd like you to check this first";
`high_value`: "مبلغ كبير (أكثر من 100,000 ج.م)" / "Large amount (over EGP 100,000)";
`plan_over_limit`: "عدد أقساط أكبر من المسموح" / "More installments than policy allows".

Actions → `send_reminder` (رسالة تذكير), `offer_payment_plan` (عرض تقسيط), `verify_payment` (التحقق من
الدفع), `escalate_to_human` (إحالة لفريقك), `wait` (الانتظار). Tones → `friendly` (ودّي), `neutral` (رسمي),
`firm` (حازم).

Do **not** display the field `assistant_note` (it is technical).

### Mock data
Use the JSON at the bottom of this document (copied from the real API) for `src/mocks/*.json`.
