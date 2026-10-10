"""Generate the Ribhiya manual test pack: a FICTIONAL skincare brand ("Nour Naturals — TEST DATA").

Every file is made up and exists only to exercise the app end to end. Run:
    uv run python scripts/make_test_pack.py
Output: test-data/tahseela-test-pack/ and test-data/tahseela-test-pack.zip
"""

from __future__ import annotations

import csv
import io
import random
import shutil
import zipfile
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "test-data" / "tahseela-test-pack"
rng = random.Random(2026)

PRODUCTS = {  # name: (price EGP, unit cost EGP or None = deliberately missing)
    "Vitamin C Serum 30ml": (420, 115),
    "Hydrating Face Cream 50ml": (380, 98),
    "Lip Balm Trio": (95, 31),
    "Glow Gift Set": (950, 340),
    "Rosemary Hair Oil 100ml": (260, None),  # no unit cost on purpose -> "cost missing"
}
WEIGHTS = [30, 25, 20, 10, 15]
AREAS = {"Cairo": 45, "Giza": 45, "Alexandria": 60, "Upper Egypt": 85}


def text_pdf(lines: list[str]) -> bytes:
    """Minimal valid single-page text PDF (no extra libraries)."""
    def esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    content = "BT /F1 10 Tf 40 800 Td 14 TL " + " ".join(f"({esc(l)}) Tj T*" for l in lines) + " ET"
    objs = ["<< /Type /Catalog /Pages 2 0 R >>", "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
            f"<< /Length {len(content)} >>\nstream\n{content}\nendstream",
            "<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>"]
    out, offsets = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n{o}\nendobj\n".encode()
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += "".join(f"{o:010d} 00000 n \n" for o in offsets).encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode()
    return out


def write_csv(name: str, header: list[str], rows: list[list]) -> None:
    with open(OUT / name, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)


def make_orders(month: str, n: int, start: int, promo: bool) -> tuple[list[list], list[list], dict]:
    """Website/Instagram orders. Returns (sales rows, courier rows by order, order areas)."""
    sales, courier, areas = [], [], {}
    for k in range(n):
        oid = f"NN-{start + k:05d}"
        day = rng.randint(1, 28)
        channel = "website" if rng.random() < 0.6 else "instagram"
        items = rng.choices(list(PRODUCTS), weights=WEIGHTS, k=1 if rng.random() < 0.7 else 2)
        net_total = 0
        for prod in items:
            price = PRODUCTS[prod][0]
            disc = round(price * 0.15) if promo and rng.random() < 0.35 else 0
            net_total += price - disc
            sales.append([oid, f"{month}-{day:02d}", prod, 1, price, disc, channel, 0, "completed"])
        fee = 40 if channel == "website" and net_total < 600 else 0
        for row in sales:
            if row[0] == oid:
                row[7] = fee
        area = rng.choices(list(AREAS), weights=[45, 25, 20, 10])[0]
        areas[oid] = area
        courier.append([f"{month}-{min(day + 2, 28):02d}", oid, area, AREAS[area], "Bosta delivery"])
    return sales, courier, areas


def main() -> None:
    shutil.rmtree(OUT, ignore_errors=True)
    OUT.mkdir(parents=True)

    # ---- 1. sales (Aug + Sep): main orders file ----------------------------------------------------------------
    aug, c_aug, _ = make_orders("2026-08", 120, 1, promo=False)
    sep, c_sep, _ = make_orders("2026-09", 140, 1001, promo=True)
    # a few returned orders in September (also in the returns file)
    write_csv("01_المبيعات.csv",
              ["Order ID", "Date", "Product", "Quantity", "Unit Price", "Discount", "Channel", "Shipping Charged",
               "Status"], aug + sep)

    # ---- 2. product costs with ARABIC headers (one product deliberately missing) --------------------------------
    write_csv("02_تكلفة_المنتجات.csv", ["المنتج", "تكلفة الوحدة"],
              [[p, c] for p, (_, c) in PRODUCTS.items() if c is not None])

    write_csv("07_تكلفة_زيت_الشعر.csv", ["Product", "Unit Cost"], [["Rosemary Hair Oil 100ml", 72]])

    # ---- 3. packaging supplier invoices as a text PDF (unit price jumps from 8 to 18) ---------------------------
    n_aug, n_sep = len({r[0] for r in aug}), len({r[0] for r in sep})
    (OUT / "03_فواتير_التغليف.pdf").write_bytes(text_pdf([
        "BoxCo Packaging - Invoices (TEST DATA)",
        "Date | Supplier | Description | Quantity | Amount",
        f"2026-08-02 | BoxCo | Printed mailer boxes | {n_aug} | {n_aug * 8}",
        f"2026-09-02 | BoxCo | Printed mailer boxes | {n_sep} | {n_sep * 18}",
    ]))

    # ---- 4. Excel workbook with several sheets: fees, fixed costs, August courier invoice -----------------------
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Fees"
    ws.append(["Date", "Supplier", "Description", "Category", "Amount", "Paid"])
    ws.append(["2026-08-30", "Paymob", "Card processing fees", "payment_fees", round(n_aug * 7.5, 2), "yes"])
    ws.append(["2026-09-30", "Paymob", "Card processing fees", "payment_fees", round(n_sep * 7.6, 2), "yes"])
    ws2 = wb.create_sheet("Fixed costs")
    ws2.append(["Date", "Supplier", "Description", "Category", "Amount", "Paid", "Due Date"])
    for m in ("2026-08", "2026-09"):
        ws2.append([f"{m}-01", "Landlord", "Studio rent", "rent", 9000, "yes", None])
        ws2.append([f"{m}-28", "Staff", "Salaries", "payroll", 16000, "yes", None])
        ws2.append([f"{m}-05", "Meta", "Instagram ads", "marketing", 6000, "no", f"{m}-25"])
    ws3 = wb.create_sheet("Courier Aug")
    ws3.append(["Date", "Supplier", "Description", "Category", "Amount", "Paid"])
    ws3.append(["2026-08-31", "Bosta", "Monthly delivery invoice", "shipping", sum(r[3] for r in c_aug), "no"])
    wb.save(OUT / "04_المصاريف.xlsx")

    # ---- 5. September courier statement BY ORDER (resolves the missing-September question; actual per order) ----
    write_csv("05_الشحن_سبتمبر.csv", ["Date", "Order ID", "Area", "Delivery Fee", "Description"],
              [[d, o, a, amt, desc] for d, o, a, amt, desc in c_sep])
    # header needs a category hint: description says delivery; the app infers "shipping"

    # ---- 6. returns with reasons (September) ----------------------------------------------------------------------
    sep_orders = sorted({r[0] for r in sep})
    ret = []
    for oid in rng.sample(sep_orders, 9):
        line = next(r for r in sep if r[0] == oid)
        reason = rng.choice(["damaged in delivery", "damaged in delivery", "skin reaction", "wrong item sent"])
        ret.append([oid, "2026-09-27", line[2], 1, line[4] - line[5], reason])
    write_csv("06_المرتجعات.csv", ["Order ID", "Date", "Product", "Quantity", "Refund Amount", "Reason"],
              ret)

    # ---- 7. marketplace export with UNUSUAL column names (you map it once; October reuses it) -------------------
    def noon(month: str, n: int, start: int) -> list[list]:
        rows = []
        for k in range(n):
            prod = rng.choices(list(PRODUCTS)[:3], weights=[40, 35, 25])[0]
            rows.append([f"NOON-{start + k:04d}", f"{month}-{rng.randint(1, 28):02d}", prod, 1, PRODUCTS[prod][0]])
        return rows
    write_csv("14_ملف_غريب.csv", ["Ref", "When", "Item", "Count", "Each"],
              noon("2026-08", 30, 1) + noon("2026-09", 35, 101))

    # ---- 8. supplier quotes (for the comparison step) --------------------------------------------------------------
    (OUT / "08_عرض_جلاس_باك.pdf").write_bytes(text_pdf([
        "GlassPack Egypt - Quotation (TEST DATA)",
        "Item: printed mailer box 18x12x6 cm, kraft, 1-colour logo",
        "Unit price: 11.00 EGP", "MOQ: 1,000 pcs", "Delivery fee: 300 EGP",
        "Lead time: 10 days", "Payment terms: 50% advance, 50% on delivery"]))
    (OUT / "09_عرض_بوكس_كرافت.txt").write_text(
        "BoxCraft - Quotation (TEST DATA)\nItem: printed mailer box 18x12x6 cm, kraft, 1-colour logo\n"
        "Unit price: 13.50 EGP\nMinimum order: 200 pcs\nLead time: 7 days\nPayment terms: 30 days after delivery\n",
        encoding="utf-8")
    (OUT / "10_عرض_بلاستيك.txt").write_text(
        "PlastiPack - Quotation (TEST DATA)\nItem: plastic courier bag 25x35 cm (NOT a box)\nUnit price: 3.20 EGP\n"
        "MOQ: 2,000 pcs\n", encoding="utf-8")

    # ---- 9. October (after switching packaging supplier) for the before/after check ------------------------------
    octo, c_oct, _ = make_orders("2026-10", 150, 2001, promo=False)
    write_csv("11_مبيعات_أكتوبر.csv", ["Order ID", "Date", "Product", "Quantity", "Unit Price", "Discount",
                                           "Channel", "Shipping Charged", "Status"], octo)
    n_oct = len({r[0] for r in octo})
    write_csv("12_مصاريف_أكتوبر.csv", ["Date", "Supplier", "Description", "Category", "Quantity", "Amount", "Paid"], [
        ["2026-10-02", "BoxCraft", "Printed mailer boxes", "packaging", n_oct, round(n_oct * 13.5, 2), "yes"],
        ["2026-10-30", "Paymob", "Card processing fees", "payment_fees", "", round(n_oct * 7.5, 2), "yes"],
        ["2026-10-01", "Landlord", "Studio rent", "rent", "", 9000, "yes"],
        ["2026-10-28", "Staff", "Salaries", "payroll", "", 16000, "yes"]])
    write_csv("13_شحن_أكتوبر.csv", ["Date", "Order ID", "Area", "Delivery Fee", "Description"],
              [[d, o, a, amt, desc] for d, o, a, amt, desc in c_oct])
    write_csv("15_ملف_غريب_أكتوبر.csv", ["Ref", "When", "Item", "Count", "Each"],
              noon("2026-10", 40, 201))

    # ---- 10. files that SHOULD be rejected or flagged (error handling) ---------------------------------------------
    write_csv("16_ملف_فيه_أخطاء.csv", ["Order ID", "Date", "Product", "Quantity", "Unit Price", "Currency"], [
        ["BAD-1", "2026-09-05", "Vitamin C Serum 30ml", 1, "abc", "EGP"],
        ["BAD-2", "31/31/2026", "Lip Balm Trio", 1, 95, "EGP"],
        ["BAD-3", "2026-09-06", "Lip Balm Trio", 1, 95, "XYZ"],
        ["BAD-4", "2026-09-07", "Lip Balm Trio", 1, 95, "EGP"],
        ["BAD-4", "2026-09-07", "Lip Balm Trio", 1, 95, "EGP"]])
    (OUT / "17_فاتورة_مصورة.pdf").write_bytes(text_pdf([]))
    (OUT / "18_ملف_مش_مدعوم.docx").write_bytes(b"PK\x03\x04 this is not a real spreadsheet")

    (OUT / "اقرأني.txt").write_text(
        "Nour Naturals (TEST DATA): a fictional skincare brand made up for testing Ribhiya.\n"
        "No real customers, suppliers or transactions. See دليل_التجربة.md for the step-by-step test.\n"
        "بيانات تجريبية لبراند وهمي. مفيش عملاء أو موردين حقيقيين. الخطوات في دليل_التجربة.md\n", encoding="utf-8")
    shutil.copy(ROOT / "docs" / "TEST_GUIDE.md", OUT / "دليل_التجربة.md") if (ROOT / "docs" / "TEST_GUIDE.md").exists() else None
    zpath = OUT.parent / "tahseela-test-pack.zip"
    zpath.unlink(missing_ok=True)
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(OUT.iterdir()):
            z.write(f, f"tahseela-test-pack/{f.name}")
    print(f"wrote {len(list(OUT.iterdir()))} files to {OUT}\nzip: {zpath}")


if __name__ == "__main__":
    main()
