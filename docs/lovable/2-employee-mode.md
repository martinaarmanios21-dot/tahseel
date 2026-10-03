## PROMPT 2: Collections employee mode (موظف التحصيل)

Add the **collections employee** mode. Navigation: **مهامي** (My tasks) · **العملاء** (Customers) · **المساعد** (Assistant).

**1. مهامي / My tasks (home)**
- Greeting card in the assistant's voice: "صباح الخير! راجعتُ {N} عميلاً اليوم. أحتاج قرارك في {needs_your_decision} رسائل."
- A big primary button **"دع المساعد يكمل عمله"** / "Let the assistant continue" → `POST /api/workspace/next-round`.
  If there is no workspace (`summary.workspace` is null), show instead **"ابدأ يوم عمل جديد"** / "Start a new work day" → `POST /api/workspace/new`.
  If the workspace `status` is `completed`, show "انتهت جولات اليوم ✓" with a button to start a new day.
- **Inbox of decisions** (`/api/decisions`), one card per item, designed for a non-technical person:
  - Header: customer name, amount (big), "متأخر {days_overdue} يوماً", business name, and a "عميل مهم ★" chip if `tier` = `key`.
  - Line in the assistant's voice explaining why it is asking (from `why_code`).
  - "ما أقترحه:" + action + tone in plain words (e.g. "رسالة تذكير بأسلوب رسمي مع رابط الدفع").
  - The **email preview** in a soft box, shown in the customer's language and direction (Arabic emails RTL, English LTR).
  - Two big buttons: **"موافق، أرسِل"** (primary) and **"لا ترسل"** (outline). Rejecting asks an optional reason in a small dialog.
  - After approval: a toast "تم الإرسال ✓". If the result is `blocked_on_recheck`: "لم أرسلها: تغيّر شيء منذ اقتراحي (مثلاً دفع العميل). لا داعي لفعل شيء."
- Empty inbox: friendly illustration + "لا شيء يحتاج قرارك الآن 🎉".

**2. العملاء / Customers**
- Search box + filter chips by status (with counts) + list/table: customer, amount, days overdue, status chip, language flag (ع / EN).
- Clicking a customer opens a side sheet: details + **timeline** from `/api/customers/{id}` (each step: what the
  assistant did, with message preview, and the customer's reply in a speech bubble). Customer replies that are
  `suspicious` show a red warning card: "هذه الرسالة تحاول خداع المساعد، لذلك أوقفتُ التعامل مع هذا العميل وأحلته لك."

**3. المساعد / Assistant**
- One big switch **"إيقاف المساعد مؤقتاً"** / "Pause the assistant" (`POST /api/kill`), with a confirmation, and a red banner across the app while paused: "المساعد متوقف. لن يرسل أي رسالة حتى تعيد تشغيله."
- "ما يمكنني فعله وما لا يمكنني فعله": a simple two-column list (green checks / red crosses):
  - Can: send polite reminders in the customer's language, offer payment in 2–3 installments, check if a payment arrived, hand difficult cases to you.
  - Cannot: threaten customers, give discounts or change amounts, contact a customer who disputes or asked us to stop, send to a key customer or any amount over 100,000 ج.م without your approval, change its own rules.
