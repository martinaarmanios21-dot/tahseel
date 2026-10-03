## PROMPT 4: Accountant mode (المحاسب) + polish

Add the **accountant** mode. Navigation: **الشركات** (Businesses) · **مهامي** · **العملاء** · **المساعد**.

**1. الشركات / Businesses**
- One card per client business (`summary.businesses`): name (name_ar / name_en), customers count, **collected**
  and **outstanding** amounts, a thin progress bar (collected / total), and a button "افتح" that sets the
  **business filter** for the whole app.
- A business switcher in the top bar (only in accountant mode): "كل الشركات" or one business. All API calls pass `?business=` when one is selected.

**2. مهامي / العملاء / المساعد**: reuse the employee screens, filtered by the selected business, and show the
business name on each card.

**Polish (all modes)**
- Every empty state, loading state (skeletons) and error state is designed and friendly, in Arabic and English.
- Every button has a clear verb. Confirm before: pause assistant, apply update, roll back, start new day.
- Large touch targets (min 44px), focus outlines, `aria-label`s, and the app must be fully usable by keyboard.
- Check every screen in **Arabic RTL + light**, **Arabic RTL + dark**, **English LTR + light**, **English LTR + dark**, and on mobile width.
- Subtle motion only (fade/slide 150–200 ms); respect `prefers-reduced-motion`.
