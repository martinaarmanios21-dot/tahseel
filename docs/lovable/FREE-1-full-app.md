Build "Tahseel (تحصيل)": a web app for an AI assistant that collects overdue invoices for small businesses in Egypt. Users are NON-TECHNICAL Arabic-speaking office staff: keep every screen extremely simple, calm and self-explanatory (few words, big buttons, max 4 nav items).

TECH: React + Vite + TS + Tailwind + shadcn/ui, no login. All data via src/lib/api.ts (fetch same-origin `/api/...`). If the API is unreachable, use local mock data from src/mocks/*.ts and show a small grey badge "بيانات تجريبية". Create realistic mocks yourself (Arabic + English customer names, EGP amounts) matching the types below.

BRAND: calm & trustworthy, like a modern bank app. Logo = rounded-square teal icon (white arrow flowing into a wallet) with the name beside it ("تحصيل" in Arabic UI, "Tahseel" in English). Font: IBM Plex Sans Arabic. Rounded cards (16px), soft shadows, lots of white space.
Colours (CSS variables, light / dark): bg #F6F8FB / #0A1628 · card #FFFFFF / #111F35 · border #E3E8EF / #1E2F4A · text #0B1F3A / #E8EEF6 · muted #5B6B82 / #94A3B8 · primary teal #0F766E (white text) / #2DD4BF (navy text) · primary-soft #E6F4F2 / #123A3F · success #15803D / #4ADE80 · warning #B45309 / #FBBF24 · danger #B91C1C / #F87171. Status colour always with icon + word.

LANGUAGE: Arabic default (dir="rtl"), toggle "ع / EN" in the top bar switches to English (ltr); all strings in src/i18n/{ar,en}.ts; use logical spacing so layout mirrors; flip directional icons. Numbers ALWAYS Western digits. Money: "195,375 ج.م" / "EGP 195,375". Theme toggle light/dark (default system). Save language, theme, role in localStorage. The assistant talks in first person like a helpful colleague.

WELCOME SCREEN (first visit): logo, "أهلاً بك في تحصيل", "مساعدك الذكي لتحصيل الفواتير المتأخرة. اختر دورك:", three big cards:
1) موظف التحصيل: "أراجع رسائل المساعد وأوافق عليها"  2) صاحب العمل / المدير: "أتابع الأموال وأوافق على تحسينات المساعد"  3) المحاسب: "أتابع التحصيل لعدة شركات".
Top bar after that: logo · role pill (click to switch) · assistant status ("المساعد يعمل" green / "المساعد متوقف" red) · ع/EN · theme. Footer link "للمحكّمين: التفاصيل التقنية" → /judges (new tab).

TYPES (from the real API):
Summary {workspace:{run_id,round,status}|null; assistant:{paused,skill_version,busy}; money:{collected_egp,outstanding_egp,with_team_egp,total_egp}; customers_by_status:Record<Status,number>; needs_your_decision:number; businesses:{id,name_ar,name_en,customers,collected_egp,outstanding_egp}[]; learning:{first_collection_rate,current_collection_rate,first_complaints,current_complaints,update_waiting_for_approval:number|null}}
Decision {decision_id,invoice_id,customer,contact_name,language:"ar"|"en",business,amount_egp,days_overdue,tier:"key"|"standard",action,tone,installments,message,why_code,last_reply}
Customer {invoice_id,customer,language,business,tier,amount_egp,days_overdue,status:Status,times_contacted,last_reply,reply_type, timeline?:{action,status,tone,message}[]}
Insights {active:{version,rules:Rule[]}, waiting_for_approval:{version,status,rules:Rule[],test_results:{passed,reasons:string[],before:Metrics,after:Metrics}}|null, history:{version,status}[]}
Rule {when:{signal?,tier?,history?,touch?}, do:{action,tone?,include_payment_link?,mention_due_date?,installments?}}; Metrics {collection_rate,complaints,safety_tests_passed,safety_tests_total}
Status = needs_you|waiting|in_progress|paid|paid_by_plan|with_team|suspicious

ENDPOINTS: GET /api/summary?business= · GET /api/decisions · POST /api/approvals/{id}/approve | /reject · GET /api/customers · GET /api/customers/{id} · GET /api/insights · POST /api/skills/{v}/promote · POST /api/kill {on} · POST /api/workspace/new · POST /api/workspace/next-round · POST /api/train {episodes:2} · POST /api/learn · GET /api/job → poll every 1.5s until status done|error, show "المساعد يعمل الآن…".

SCREENS
EMPLOYEE (nav: مهامي · العملاء · المساعد):
- مهامي: greeting "أحتاج قرارك في N رسائل"; big button "دع المساعد يكمل عمله" (next-round) or "ابدأ يوم عمل جديد" if no workspace. Inbox: one card per Decision: customer, big amount, "متأخر X يوماً", ★ "عميل مهم" if key, why it asks (key_account → "عميل مهم، أفضّل أن تراجع الرسالة"; high_value → "مبلغ كبير"; plan_over_limit → "أقساط أكثر من المسموح"), what it proposes in plain words, the email preview in its own language/direction, two big buttons "موافق، أرسِل" / "لا ترسل". Empty: "لا شيء يحتاج قرارك الآن 🎉".
- العملاء: search + status filter chips + list; click → side sheet with timeline (assistant actions + customer replies as bubbles). Status labels: needs_you ينتظر قرارك · waiting لم نتواصل بعد · in_progress ذكّرناه وننتظر · paid تم الدفع · paid_by_plan اتفقنا على تقسيط · with_team مُحال لفريقك · suspicious رسالة مشبوهة، أوقفناها (red, shield).
- المساعد: big "إيقاف المساعد مؤقتاً" switch (confirm; red banner while paused) + two simple lists "ما أستطيع فعله" (polite reminders in the customer's language, 2–3 installments, check payments, hand hard cases to you) / "ما لا أفعله أبداً" (threats, discounts, contacting disputing customers, sending to key customers or amounts over 100,000 ج.م without approval, changing my own rules).
OWNER (nav: الملخص · ما تعلّمته · العملاء · المساعد):
- الملخص: 4 stat cards (تم تحصيله, ما زال مستحقاً, مُحال لفريقك, ينتظر قرارك), one simple stacked bar "أين أموالك؟", card "المساعد يتحسّن": "كنت أحصّل X% والآن Y%، والشكاوى من A إلى B"; callout if an update waits.
- ما تعلّمته: one line explaining "أتعلّم من النتائج، وأي تحسين يُختبر أولاً ولا يُطبّق إلا بموافقتك". If waiting_for_approval: before/after comparison (collection %, complaints, safety tests X/Y), green badge if passed, button "طبّق التحسين" (promote) only if passed, else show reasons. Show rules as plain sentences "عندما … ← أقوم بـ …" (paid_claim يقول إنه دفع → verify_payment أتحقق من الدفع; dispute يعترض → escalate_to_human أحيله لفريقك; cash_flow صعوبة سيولة → offer_payment_plan أعرض التقسيط; key عميل مهم; reliable يدفع في موعده; chronic يتأخر كثيراً; first أول تواصل; followup متابعة; friendly ودّي/neutral رسمي/firm حازم; link مع رابط الدفع). Collapsible "تجربة التعلّم (للعرض)": buttons "دع المساعد يتدرّب" (train) then "دع المساعد يتعلّم" (learn).
ACCOUNTANT (nav: الشركات · مهامي · العملاء · المساعد): cards per business (name, collected, outstanding, progress bar, "افتح"); business switcher in top bar filters everything (?business=).
