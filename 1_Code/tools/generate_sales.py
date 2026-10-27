"""Generate sales invoices and credit notes for revenue cut-off and credit-note testing (deterministic, synthetic).

For each data set (group and standalone) writes next to its ledger:
  sales.csv         sales invoices and credit notes (document, dates, shipping date, amount, original invoice, reason)
  fiscal_config.csv per-company fiscal year-end, cut-off window, credit-note window and threshold
  sales_truth.csv   the flags each document should raise (computed here with an independent copy of the rules)

Rules (the workflow implements the same rules in C#):
  Invoice in the cut-off window (year-end -5 .. +5 days):
    NO_SHIP_DATE   no shipping date on file
    CUTOFF_EARLY   recorded on or before year-end but shipped after it (next year's revenue pulled into this year)
    CUTOFF_LATE    recorded after year-end but shipped on or before it
  Credit note issued in the credit window (day after year-end .. +15 days):
    CREDIT_AFTER_YE         amount at or above the company's threshold
    CREDIT_REVERSES_YE_SALE refers to an invoice dated in the last 5 days before year-end
All customers, names and addresses are synthetic.
"""
import csv, random
from datetime import date, timedelta
from pathlib import Path

random.seed(31)
ROOT = Path(__file__).resolve().parent.parent
FLOW = ROOT / "EthicalAuditSolution" / "EthicalAuditFlow"

# company -> org, currency, FxToGroup, fiscal year-end, credit threshold (local currency)
CO = {
    "CMP-US": ("ORG-001", "USD", 1.0, date(2026, 6, 30), 8000),
    "CMP-UK": ("ORG-001", "GBP", 1.27, date(2026, 3, 31), 6500),
    "CMP-DE": ("ORG-001", "EUR", 1.09, date(2026, 9, 30), 7500),
    "CMP-IN": ("ORG-001", "INR", 0.012, date(2026, 3, 31), 400000),
    "CMP-HB": ("ORG-002", "USD", 1.0, date(2026, 6, 30), 5000),
}
CUT_DAYS, CREDIT_DAYS = 5, 15
CUSTOMERS = ["Alder Retail", "Birch Wholesale", "Cedar Stores", "Dune Trading", "Elm Distribution", "Fern Supplies",
             "Grove Markets", "Heath Outlets"]
REASONS = ["Goods returned", "Pricing correction", "Volume discount", "Damaged on delivery", "Order cancelled"]
PII_REASONS = ["Refund requested by buyer k.nair@customer.example.com", "Order cancelled, customer called +44 207 555 0188",
               "Cancelled per request of d.lopez@customer.example.com"]


def build(cid, plan):
    org, cur, fx, ye, thr = CO[cid]
    code = cid[-2:]
    rows = []
    n_inv, n_crn = [0], [0]

    def amt_usd(lo, hi):
        return round(random.uniform(lo, hi) / fx, 2)

    def invoice(d, ship, amount):
        n_inv[0] += 1
        c = random.choice(CUSTOMERS)
        r = {"DocumentNo": f"SI-{code}-{n_inv[0]:04d}", "OrgId": org, "CompanyId": cid, "Type": "Invoice",
             "CustomerId": f"CUS-{code}-{CUSTOMERS.index(c) + 1:02d}", "CustomerName": c, "DocumentDate": d.isoformat(),
             "ShipDate": ship.isoformat() if ship else "", "Amount": f"{amount:.2f}", "Currency": cur,
             "OriginalInvoice": "", "Reason": ""}
        rows.append(r)
        return r

    def credit(d, original, amount, reason):
        n_crn[0] += 1
        r = {"DocumentNo": f"CN-{code}-{n_crn[0]:04d}", "OrgId": org, "CompanyId": cid, "Type": "CreditNote",
             "CustomerId": original["CustomerId"], "CustomerName": original["CustomerName"], "DocumentDate": d.isoformat(),
             "ShipDate": "", "Amount": f"{amount:.2f}", "Currency": cur, "OriginalInvoice": original["DocumentNo"],
             "Reason": reason}
        rows.append(r)
        return r

    def far_date():
        # a date well away from the year-end windows
        while True:
            d = date(2026, 1, 5) + timedelta(days=random.randint(0, 270))
            if abs((d - ye).days) > CREDIT_DAYS + 3:
                return d

    mid = []
    for _ in range(plan["normal"]):
        d = far_date()
        mid.append(invoice(d, d - timedelta(days=random.randint(0, 3)), amt_usd(1500, 15000)))
    # window invoices
    for _ in range(plan["clean_pre"]):          # recorded and shipped on or before year-end
        d = ye - timedelta(days=random.randint(0, CUT_DAYS))
        invoice(d, d - timedelta(days=random.randint(0, 3)), amt_usd(1500, 15000))
    for _ in range(plan["clean_post"]):         # recorded and shipped after year-end
        d = ye + timedelta(days=random.randint(1, CUT_DAYS))
        invoice(d, max(d - timedelta(days=random.randint(0, 3)), ye + timedelta(days=1)), amt_usd(1500, 15000))
    for _ in range(plan["early"]):
        d = ye - timedelta(days=random.randint(0, CUT_DAYS - 1))
        invoice(d, ye + timedelta(days=random.randint(1, 6)), amt_usd(2000, 15000))
    for _ in range(plan["late"]):
        d = ye + timedelta(days=random.randint(1, CUT_DAYS))
        invoice(d, ye - timedelta(days=random.randint(0, 4)), amt_usd(2000, 15000))
    noship = []
    for _ in range(plan["noship"]):
        d = ye - timedelta(days=random.randint(0, CUT_DAYS))
        noship.append(invoice(d, None, amt_usd(2000, 15000)))

    # credit notes
    for _ in range(plan["credit_normal"]):      # ordinary mid-year credit notes, small
        o = random.choice(mid)
        credit(far_date(), o, round(float(o["Amount"]) * random.uniform(0.05, 0.3), 2), random.choice(REASONS))
    for _ in range(plan["credit_small_post"]):  # small credit notes just after year-end, not linked to a year-end sale
        o = random.choice(mid)
        credit(ye + timedelta(days=random.randint(1, CREDIT_DAYS)), o, round(thr * random.uniform(0.1, 0.6), 2), random.choice(REASONS))
    for _ in range(plan["credit_large_post"]):  # large credit notes just after year-end, mid-year original
        c_amt = round(thr * random.uniform(1.05, 1.6), 2)
        o = invoice(far_date(), None, 0)
        o["ShipDate"] = (date.fromisoformat(o["DocumentDate"]) - timedelta(days=1)).isoformat()
        o["Amount"] = f"{c_amt * random.uniform(1.0, 1.4):.2f}"
        credit(ye + timedelta(days=random.randint(1, CREDIT_DAYS)), o, c_amt,
               random.choice(PII_REASONS) if random.random() < 0.4 else random.choice(REASONS))
    for _ in range(plan["credit_large_reverse"]):   # full reversal of a year-end sale, large
        a = round(thr * random.uniform(1.1, 1.7), 2)
        d = ye - timedelta(days=random.randint(0, CUT_DAYS))
        o = invoice(d, d - timedelta(days=random.randint(0, 2)), a)
        credit(ye + timedelta(days=random.randint(1, CREDIT_DAYS)), o, a, random.choice(PII_REASONS + REASONS))
    for _ in range(plan["credit_small_reverse"]):   # reversal of a year-end sale that was never shipped, small
        o = random.choice(noship)
        credit(ye + timedelta(days=random.randint(1, CREDIT_DAYS)), o, round(thr * random.uniform(0.3, 0.8), 2), "Order cancelled")
    for _ in range(plan["credit_large_outside"]):   # large credit note, but well outside the window: not flagged
        a = round(thr * random.uniform(1.1, 1.5), 2)
        o = invoice(far_date(), None, 0)
        o["ShipDate"] = o["DocumentDate"]; o["Amount"] = f"{a * 1.2:.2f}"
        credit(far_date(), o, a, random.choice(REASONS))
    random.shuffle(rows)
    return rows


def expected(rows, cid):
    """Independent copy of the rules, used only to score the workflow's test."""
    org, cur, fx, ye, thr = CO[cid]
    by_no = {r["DocumentNo"]: r for r in rows}
    out = []
    for r in rows:
        d = date.fromisoformat(r["DocumentDate"])
        fl = set()
        if r["Type"] == "Invoice":
            if abs((d - ye).days) <= CUT_DAYS:
                ship = date.fromisoformat(r["ShipDate"]) if r["ShipDate"] else None
                if ship is None:
                    fl.add("NO_SHIP_DATE")
                elif d <= ye and ship > ye:
                    fl.add("CUTOFF_EARLY")
                elif d > ye and ship <= ye:
                    fl.add("CUTOFF_LATE")
        else:
            if ye < d <= ye + timedelta(days=CREDIT_DAYS):
                if float(r["Amount"]) >= thr:
                    fl.add("CREDIT_AFTER_YE")
                o = date.fromisoformat(by_no[r["OriginalInvoice"]]["DocumentDate"])
                if ye - timedelta(days=CUT_DAYS) <= o <= ye:
                    fl.add("CREDIT_REVERSES_YE_SALE")
        out.append({"DocumentNo": r["DocumentNo"], "CompanyId": cid, "ExpectedFlags": ";".join(sorted(fl))})
    return out


GROUP = dict(normal=30, clean_pre=5, clean_post=4, early=3, late=2, noship=2, credit_normal=5, credit_small_post=2,
             credit_large_post=2, credit_large_reverse=1, credit_small_reverse=1, credit_large_outside=1)
SOLO = dict(normal=24, clean_pre=4, clean_post=3, early=2, late=2, noship=2, credit_normal=4, credit_small_post=2,
            credit_large_post=2, credit_large_reverse=1, credit_small_reverse=1, credit_large_outside=1)


def write(folder, cids, plan):
    rows, truth, conf = [], [], []
    for cid in cids:
        r = build(cid, plan)
        rows += r; truth += expected(r, cid)
        org, cur, fx, ye, thr = CO[cid]
        conf.append({"CompanyId": cid, "FiscalYearEnd": ye.isoformat(), "CutOffDays": CUT_DAYS,
                     "CreditWindowDays": CREDIT_DAYS, "CreditThreshold": thr})
    for name, data in (("sales.csv", rows), ("sales_truth.csv", truth), ("fiscal_config.csv", conf)):
        with open(folder / name, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(data[0])); w.writeheader(); w.writerows(data)
    print(folder.name, "documents", len(rows), "expected flagged", sum(1 for t in truth if t["ExpectedFlags"]))


write(FLOW / "data", ["CMP-US", "CMP-UK", "CMP-DE", "CMP-IN"], GROUP)
write(FLOW / "data_standalone", ["CMP-HB"], SOLO)
