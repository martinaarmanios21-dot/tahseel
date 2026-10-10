"""Deterministic TEST-ONLY business fixtures (fictional). Used by automated tests only; never in the live workspace."""

import io


def sales_csv(months=("2026-08", "2026-09"), orders=(60, 72), price=500, discount=(0, 0)) -> bytes:
    out = io.StringIO()
    out.write("Order ID,Date,Product,Quantity,Unit Price,Discount,Channel,Status\n")
    n = 0
    for m, k, disc in zip(months, orders, discount):
        for i in range(k):
            n += 1
            prod = "Shirt" if i % 3 else "Dress"
            p = price if prod == "Shirt" else price * 2
            out.write(f"T{n:04d},{m}-{(i % 27) + 1:02d},{prod},1,{p},{disc},website,completed\n")
    return out.getvalue().encode()


def costs_csv() -> bytes:
    return b"Product,Unit Cost\nShirt,200\nDress,450\n"


def expenses_csv(months=("2026-08", "2026-09"), box_qty=(60, 72), box_price=(10, 25), shipping=(3000, 3600)) -> bytes:
    out = io.StringIO()
    out.write("Date,Supplier,Description,Category,Quantity,Amount,Paid,Due Date\n")
    for m, q, p, s in zip(months, box_qty, box_price, shipping):
        out.write(f"{m}-02,BoxCo,Mailer boxes,packaging,{q},{q * p},yes,\n")
        out.write(f"{m}-28,FastShip,Courier statement,shipping,,{s},no,{m}-30\n")
        out.write(f"{m}-01,Landlord,Shop rent,rent,,8000,yes,\n")
    return out.getvalue().encode()
