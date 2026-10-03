## PROMPT 3: Business owner / manager mode (صاحب العمل / المدير)

Add the **owner** mode. Navigation: **الملخص** (Overview) · **ما تعلّمه المساعد** (What it learned) · **العملاء** · **المساعد**.

**1. الملخص / Overview**
- Four large stat cards from `/api/summary.money` and counts: **تم تحصيله** (collected_egp, success colour) ·
  **ما زال مستحقاً** (outstanding_egp) · **مُحال لفريقك** (with_team_egp) · **ينتظر قرارك** (needs_your_decision, links to the inbox).
- A simple horizontal stacked bar "أين أموالك؟" showing collected / outstanding / with team, with labels and amounts (no complex charts).
- A highlight card **"المساعد يتحسّن"** using `summary.learning`: "عندما بدأتُ كنت أحصّل {first_collection_rate}% من
  الأموال في الاختبار، والآن أحصّل {current_collection_rate}%. والشكاوى انخفضت من {first_complaints} إلى {current_complaints}."
  Show as two big numbers with an arrow. If `update_waiting_for_approval` is not null, show a teal callout "لديّ تحسين جديد ينتظر موافقتك" → links to page 2.
- The inbox of decisions from the employee mode is also available here (reuse the component).

**2. ما تعلّمه المساعد / What the assistant learned**
- Uses `/api/insights`. Explain in one sentence at the top: "أتعلّم من نتائج رسائلي: ما الذي يجعل كل نوع من العملاء يدفع. أي تحسين أقترحه يُختبر أولاً، ولا يُطبّق إلا بموافقتك."
- **If `waiting_for_approval` exists**: a card "تحسين جديد مقترح (الإصدار {version})" with a **before/after comparison** from
  `test_results.before` / `.after`: نسبة التحصيل, الحالات المحلولة بشكل صحيح, الشكاوى, اختبارات الأمان ({passed}/{total}).
  Green check badge "نجح في كل اختبارات الأمان ✓" when `passed` is true; otherwise show the reasons in plain words and no approve button.
  Buttons: **"طبّق التحسين"** (`POST /api/skills/{version}/promote`, only when status = `passed_gate`) and "ليس الآن".
- **Current rules in plain language** (from `active.rules`): render each rule as a sentence card
  "عندما … ← أقوم بـ …". Translate `when` and `do`:
  - when.signal: `paid_claim` "يقول العميل إنه دفع", `dispute` "يعترض العميل على الفاتورة", `cash_flow` "يواجه العميل صعوبة في السيولة",
    `angry` "العميل غاضب من الأسلوب", `reply` "ردّ العميل ردّاً عادياً", `opt_out` "طلب العميل إيقاف المراسلة", `none` "لم يرد العميل بعد".
  - when.tier: `key` "عميل مهم", `standard` "عميل عادي". when.history: `reliable` "يدفع عادةً في موعده",
    `occasional` "يتأخر أحياناً", `chronic` "يتأخر كثيراً". when.touch: `first` "أول تواصل", `followup` "متابعة". Empty `when` = "في باقي الحالات".
  - do.action as above; plus tone, "مع رابط الدفع" if include_payment_link, "مع ذكر تاريخ الاستحقاق" if mention_due_date,
    "على {installments} أقساط" for payment plans.
- A small "سجل التحديثات" (history) list with versions and status chips (active "مُفعّل", passed_gate "جاهز للتطبيق",
  rejected "مرفوض في الاختبار", retired "إصدار سابق", candidate "قيد الاختبار"), and a button "تراجع عن آخر تحديث" (`POST /api/skills/rollback`, with confirm).

**3. Demo controls (for the hackathon video)**
On the "ما تعلّمه المساعد" page, add a collapsible card at the bottom **"تجربة التعلّم (للعرض)"**: button
"دع المساعد يتدرّب" (`POST /api/train` `{"episodes":2}`), then "دع المساعد يتعلّم من النتائج" (`POST /api/learn`). Show
progress with the job poller and refresh insights when done.
