# Ribhiya: hands-on test guide (with the test pack)

The test pack is a **fictional** skincare brand, *Nour Naturals (TEST DATA)*: no real customers, suppliers or
transactions. The numbers below are what the app showed in a dry run of this exact pack (the pack is generated with a
fixed seed, so you should see the same values).

## 0. Start the app

```bash
cd ~/revenue-agent          # the project folder
uv run revenue-agent serve  # open http://127.0.0.1:8000
```

- Questions about your numbers in **Chat with Ribhiya** use Hermes if the locked profile exists (answers take 1–3 minutes). For instant answers start with
  `PROFIT_ADVISOR_ENGINE=api uv run revenue-agent serve` (uses your Gemini key), or `=rules` (no AI).
- Switch **EN / ع** at any time (top right). Everything below works in both languages.
- Unzip `tahseela-test-pack.zip`. The files have short Arabic names, numbered 01–18 in the order you use them.

## The screen in 30 seconds

Top to bottom, an investigation page has only three parts:
1. **Progress bar:** About you → Files → The leak → Fix it → Result.
2. **Do this now:** one card, one task. Answer it, upload a file, or click its single button.
3. **What I found:** the biggest leak in one sentence, one chart, and one fix button (**Get cheaper prices** for
   packaging/shipping/product costs, **Try a fix** otherwise). **Explain** shows the details.
   Other leaks appear as chips under **Also found**.

Everything else sits in tabs: **Files · Products · What if · Suppliers · Results**. Questions go to **Chat with Ribhiya**
(bottom corner): inside an investigation it shows your step and next action, and answers from your numbers.

## 1. Start an investigation

1. Home: type **Nour Naturals (TEST)**, keep **EGP** (the test files are in Egyptian pounds), then **Start a new
   investigation**. The currency is the one your files are written in: Ribhiya never converts. Picked the wrong one?
   Click **Change** next to the currency at the top of the investigation; the same amounts get the right label.
2. **Do this now** asks three short questions. Answer them:
   - "What worries you most?" → **I sell, but little money is left**
   - "What do you sell?" → **Products**
   - "Where do you sell?" → **My website** + **Social media** + **Marketplaces** → **Save**
3. Next it asks for your sales report (click **Why?** to see why it matters).

## 2. Upload the first four files (all at once is fine)

`01_المبيعات.csv`, `02_تكلفة_المنتجات.csv` (Arabic column names),
`03_فواتير_التغليف.pdf` (a PDF), `04_المصاريف.xlsx` (an Excel file with 3 sheets).

You should see:
- **Do this now:** "I see **shipping** records for 2026-08 but none for 2026-09. Is an invoice missing?"
  **What I found** stays hidden until this is answered: the app won't compare a full month with an empty one.
- **Files tab:** each file is "Read". The Excel shows 3 sheets (Fees, Fixed costs, Courier Aug). The document list
  shows Product unit costs as *Needs your confirmation* (one product has no cost) and Returns as *Missing*.
- **Products tab:** Rosemary Hair Oil shows **Cost missing** (never shown as zero).

## 3. Fix the gap with the courier statement

1. In **Do this now** click **Yes, an invoice is missing**, then upload `05_الشحن_سبتمبر.csv`
   in the same card.
2. Confirm the inferred categories (**Files** tab). On **05_الشحن_سبتمبر** and on **03_فواتير_التغليف** click **Fix columns**,
   keep the type *Expenses / supplier invoices*, click **Confirm and remember this layout**, and choose the same file
   again. *Needs your confirmation* turns into *In the analysis*.

You should see:
- **What I found:** each order now leaves you EGP 23.74 less because of discounts, with the monthly amount under it.
  **Also found** shows packaging (EGP 10.00 less per order, 8.00 → 18.00 on the invoices; see **Explain**).
- **Products tab:** losing orders appear under **Orders that lost money**. Each cost says **Actual** (shipping from
  the courier statement) or **Allocated (estimate)** (packaging and fees from monthly invoices).

## 4. Upload returns and the missing product cost

Upload `06_المرتجعات.csv` and `07_تكلفة_زيت_الشعر.csv` (Files tab, or the
Do this now card if it asks for them).

You should see:
- **What I found:** discounts −EGP 23.74, with refunds −EGP 21.24 and packaging −EGP 10.00 under **Also found**.
- **Products tab:**
  - "Vitamin C Serum 30ml brings the most sales (EGP 37,863.00), but each unit leaves only EGP 222.48, while Glow Gift
    Set leaves EGP 506.06 per unit."
  - "14 of 260 orders lost money after all order costs."
  - **Sales channels:** Instagram has most of the loss-making orders (customers pay no delivery fee there).
  - **More charts** (bottom): sales vs what you keep, the waterfall of what changed, product margins. Click
    **Show the numbers** under any chart.

## 5. Answer the questions and see "I don't have it" in action

- Do this now asks **"Packaging now costs more per order. Did your supplier raise prices…?"** → **Supplier raised prices**.
- It asks for a **payment-gateway statement with order numbers** → click **I don't have this file**.
  It's never asked again, and the analysis continues (fees stay an allocated estimate).
- In **Products**, open **How monthly invoices are shared across orders** and switch Packaging to **Don't allocate**.
  The reconciliation line keeps its ✓. Switch it back.

**Chat with Ribhiya** (open it on this page): *"Why is my profit down?"*, then *"What can I do about it?"*. It answers from the September analysis:
discounts, refunds and packaging.

## 6. What if…? (simulator)

Open the **What if** tab. Try each one and click **Calculate**:

| Change | Expected result for 2026-09 |
|---|---|
| Packaging cost per order = **13.5** | +EGP 630.00 |
| Change price **5** % (all products) | +EGP 2,972.56, plus the assumption "customers keep buying the same quantities" |
| Price 5 % **and** "your guess for change in orders" = **−10** | −EGP 375.90 |
| Free shipping above **500**, fee below **40** | +EGP 1,720.00 |

Each result is labelled as a projection and lists what stays unchanged. Your files are never modified.

## 7. Ask a supplier for quotes

1. In **What I found** click the **packaging** chip under *Also found*, then **Get cheaper prices**. (Or, once the
   questions are done, **Do this now** says *Ask other suppliers for prices* with a **Prepare supplier request** button.)
2. The **Suppliers** tab opens with a draft. It has has `[[placeholders]]` and **Approve** is disabled. Fill in:
   - what you're sourcing: *printed mailer boxes*
   - specification: *18x12x6 cm kraft, 1-colour logo*
   - quantity: click **Use 140 (orders in 2026-09)**
   - business: *Nour Naturals*, name: *Nour*
   - supplier: *BoxCraft*, email: *sales@boxcraft.example*
   Choose the email language (العربية / English), then **Update draft from the brief**.
3. **Approve this message.** Without SMTP set up there is no Send button: you get **Copy message** and the note "It has
   NOT been sent". Click **I sent it myself**. The status becomes *You reported sending it (unverified)*.
4. **Do this now** now shows **Waiting for the supplier**.

## 8. Turn supplier replies into evidence (quotes)

In the **Suppliers** tab, under **Compare supplier quotes**, add four quotes in the same group, typing **mailer box 18x12x6** as the comparison
group each time:

| Quote | How to enter it | Ticks |
|---|---|---|
| **GlassPack** | **Read values from the quote document** → `08_عرض_جلاس_باك.pdf`. Fields fill in (unit price 11.00, MOQ 1,000, delivery 300, lead time 10, payment terms) and are marked "read from the document: check it". Add supplier and spec. | real quote ✔, same spec ✔ |
| **BoxCraft** | Read `09_عرض_بوكس_كرافت.txt` (13.50, MOQ 200, 7 days, 30 days). Set **Answers request: #… BoxCraft**. | real quote ✔, same spec ✔ |
| **PlastiPack** | Read `10_عرض_بلاستيك.txt` (a plastic bag, not a box). | real quote ✔, **leave "same spec" unticked** |
| **Online shop listing** | Type unit price **6**, source **Published web price (not a quote)**. | — |

Then click **Compare: mailer box 18x12x6**:
- **BoxCraft:** you'd buy 200 (+60 extra because of the minimum order), about EGP 19.29 per box you actually need.
  Delivery and setup fees are **Unknown**, so the total is a lower bound.
- **GlassPack:** you'd buy 1,000 (+860 extra), about EGP 80.71 per box you need.
- **Not compared:** PlastiPack ("specification not confirmed as equivalent") and the online listing ("published
  price, not a quote you received").
- The BoxCraft request now shows **Supplier reply added by you**.
- Click **Test in simulator** on a row to see a labelled projection.
- **Do this now** then offers **Ask about smaller quantities** for both suppliers: click one, and a short
  minimum-order question is drafted.

## 9. Save as an experiment and measure it with October data

1. In **What if** set packaging = **13.5**, Calculate, name it *Switch to BoxCraft boxes*, and click
   **Save as an experiment to measure**.
2. In the **Results** tab set **I started on 2026-10-01** and save. Click **Check the result** and you get
   *Awaiting updated data* (no October records yet).
3. Upload `11_مبيعات_أكتوبر.csv`, `12_مصاريف_أكتوبر.csv`, `13_شحن_أكتوبر.csv`.
4. Click **Check the result**. You should see **Verified improvement**: EGP 13.50 per order after the change vs 18.00
   (−25 %), with the note "Observed after the change; this does not prove the change caused it." The projection
   stays a projection.

## 10. Learning: a file layout the app doesn't know

1. Upload `14_ملف_غريب.csv` (columns *Ref, When, Item, Count, Each*). It isn't read
   and says "could not tell what this table contains".
2. **Fix columns:** type *Sales / orders*, then map
   - order_id = Ref
   - date = When
   - product = Item
   - quantity = Count
   - unit_price = Each
   Then **Confirm and remember this layout** and choose the file again: 65 rows are read.
3. Upload `15_ملف_غريب_أكتوبر.csv`. It's read automatically, with "Used the column mapping you
   confirmed before".
4. **What Ribhiya remembers about your business** (bottom of the Files tab) shows the learned layouts and how often they were reused, with a
   **Forget** button.

## 11. Ask Ribhiya again

In **Chat with Ribhiya**, ask the same question (or in Arabic: *ليه ربحي قلّ؟*). Now that October is uploaded, the
comparison moves to **September → October**. Packaging went *down*, so the answer and headline change accordingly.
That's expected: the app always compares the latest two months. The answer shows which engine was used (Hermes / AI /
straight from the calculations), and any figure that isn't in the calculations is flagged.

## 12. Error handling (use a second investigation)

Go **Home**, start a new investigation called *Error test*, and upload:
- `16_ملف_فيه_أخطاء.csv`: open **Issues** on the file to see
  - row 2: not a number
  - row 3: invalid date
  - row 4: unknown currency
  - row 6: duplicate
- `17_فاتورة_مصورة.pdf`: "no text found… probably a scanned image. OCR is not supported yet".
- `18_ملف_مش_مدعوم.docx`: "unsupported file type '.docx'".

## What is real vs. simulated in this test
- Every figure comes from these files and the app's own calculations. Projections are labelled as projections.
- **Email:** without SMTP in `.env` nothing is sent: you get a draft to copy. "I sent it myself" is recorded as
  unverified.
- **Supplier replies** are entered by you. There's no inbox connection and no OCR.
