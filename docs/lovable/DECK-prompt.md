Build a short presentation website (a slide deck) in ARABIC for my hackathon project "تحصيل". The whole deck is right-to-left: <html dir="rtl" lang="ar">. One slide per screen, full-screen 16:9 slides, navigate with arrow keys (in RTL, the left arrow = next), click or swipe, slide counter at the bottom ("3 / 11"), a fullscreen button. No backend. Numbers always in Western digits (0-9).

STYLE: calm & trustworthy, like a modern bank. Font IBM Plex Sans Arabic (weights 400–700). Colours: navy #0B1F3A, teal #0F766E (accent #2DD4BF), background #F6F8FB, white cards, success green #15803D. Big bold headlines, very little text per slide, generous white space, subtle fade between slides, icons that mirror correctly in RTL. Logo: rounded-square teal icon (white arrow flowing into a wallet) with "تحصيل" beside it.

SCREENSHOTS (load from these URLs; show inside a soft browser-window frame with rounded corners and shadow):
- welcome: https://raw.githubusercontent.com/martinaarmanios21-dot/tahseel/main/docs/screenshots/welcome-ar.png
- inbox: https://raw.githubusercontent.com/martinaarmanios21-dot/tahseel/main/docs/screenshots/approvals-ar.png
- owner: https://raw.githubusercontent.com/martinaarmanios21-dot/tahseel/main/docs/screenshots/owner-time-saved-ar.png
- learned: https://raw.githubusercontent.com/martinaarmanios21-dot/tahseel/main/docs/screenshots/what-i-learned-ar.png
- judges: https://raw.githubusercontent.com/martinaarmanios21-dot/tahseel/main/docs/screenshots/judges-dashboard.png

SLIDES (use this Arabic text exactly):
1. العنوان: الشعار، "تحصيل"، والعنوان الفرعي: "مساعد ذكي يتابع الفواتير المتأخرة للشركات الصغيرة والمتوسطة، ويتحسّن من نفسه بأمان." وفي الأسفل الشعار: "تحصيل: فلوسك، في وقتها."
2. المشكلة: رقمان كبيران جنباً إلى جنب: "81 يوماً: متوسط انتظار الشركات في الشرق الأوسط لتحصيل أموالها" و"58%: نسبة المبيعات الآجلة بين الشركات التي تُدفع متأخرة في الإمارات". سطر صغير للمصادر: "دراسة PwC لرأس المال العامل في الشرق الأوسط 2025 · مؤشر Atradius لممارسات الدفع 2025 (الإمارات)".
3. لماذا يؤلم ذلك الشركات الصغيرة؟ ثلاث بطاقات بأيقونات: "أموال كسبتها لكن لا تستطيع استخدامها: رواتب، بضاعة، توسّع" · "المتابعة يدوية ومُرهقة، وغالباً تُنسى" · "رسالة واحدة قاسية قد تخسّرك عميلاً مهماً".
4. لماذا بنيتُ تحصيل؟ جملة واحدة: "أردتُ مساعداً يتابع الفواتير الروتينية بلغة كل عميل، ويستشير الإنسان قبل أي خطوة حساسة، ويتعلّم ما الذي يجعل كل عميل يدفع فعلاً." مع صورة شاشة الترحيب.
5. كيف يعمل؟ مخطط دائري بسيط من 6 خطوات: "يقرّر" ← "يتحقق (قواعد أمان مكتوبة كبرمجة)" ← "يُرسل أو يسأل الإنسان" ← "يتعلّم من النتائج" ← "يُختبر (9 اختبارات أمان)" ← "الإنسان يوافق". تحته: "لا يستطيع أي ذكاء اصطناعي تغيير قواعده بنفسه."
6. المنتج: صورة صندوق المهام في جانب، والنص في الجانب الآخر: "الموظف يتعامل فقط مع القرارات المهمة. كل رسالة بلغة العميل، عربية أو إنجليزية، وبالمبلغ الدقيق بالجنيه المصري. العملاء المهمون والمبالغ الكبيرة تنتظر الموافقة دائماً."
7. يتحسّن من نفسه: صورة صفحة "ما تعلّمته" مع أرقام كبيرة قبل/بعد: "نسبة التحصيل: 24% ← 84%" · "الشكاوى: 12 ← 0" · "اختبارات الأمان: 9/9". ملاحظة صغيرة: "نتائج من محفظة عملاء محاكاة."
8. القيمة للشركة: صورة ملخص صاحب العمل مع ثلاث بطاقات: الإيرادات "أموال أكثر تُحصَّل، وأسرع" · الوقت "حوالي 120 ساعة شهرياً لكل 200 فاتورة متأخرة (تقدير: 10 دقائق لكل متابعة يدوية)" · التكلفة "حوالي ثلاثة أرباع العمل الروتيني لموظف تحصيل، بنماذج ذكاء اصطناعي مجانية وحدود صارمة للتكلفة". هامش: "تقديرات مبنية على افتراضات معلنة."
9. مصمَّم ليكون موثوقاً: صورة لوحة المحكّمين مع قائمة بعلامات صح: "قواعد أمان مكتوبة كبرمجة" · "حجز الرسائل المشبوهة بالعربية والإنجليزية" · "لا رسائل مكررة" · "حدود للتكلفة والسرعة" · "زر إيقاف فوري" · "نسخ محفوظة لكل تحسين مع تراجع بضغطة" · "موافقة الإنسان" · "سجل كامل لكل خطوة".
10. التقنيات: "مهارة على منصة Hermes Agent مع أدوات MCP محمية · Python · React · نماذج Gemini وNVIDIA المجانية · 31 اختباراً تلقائياً". وتحتها ثلاثة أدوار: "موظف التحصيل" · "صاحب العمل" · "المحاسب".
11. الختام: "تحصيل: فلوسك، في وقتها." مع "github.com/martinaarmanios21-dot/tahseel" و"شكراً لكم".
