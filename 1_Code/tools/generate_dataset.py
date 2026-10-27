"""Generate the 500-row multi-company benchmark dataset (deterministic, seeded).

Outputs (relative to repo root):
  config/organization.json   organization -> companies hierarchy + per-company rules
  data/ledger.csv            500 internal ledger rows across all companies
  data/documents.csv         extracted invoice data (what Document Understanding would return)
  data/ground_truth.csv      expected outcome per ledger row, used to score the benchmark
All PII is synthetic.
"""
import csv, json, random
from datetime import date, timedelta
from pathlib import Path

SEED = 42
ROOT = Path(__file__).resolve().parent.parent
random.seed(SEED)

ORG = {
    "OrgId": "ORG-001",
    "OrgName": "Meridian Holdings Group",
    "GroupCurrency": "USD",
    "Companies": [
        {"CompanyId": "CMP-US", "Name": "Meridian Logistics Inc.", "Currency": "USD", "FxToGroup": 1.0,
         "AmountVarianceTolerancePct": 1.0, "RoutingVariancePct": 5.0, "MinConfidence": 0.85, "InherentRisk": "Medium"},
        {"CompanyId": "CMP-UK", "Name": "Meridian Retail Ltd.", "Currency": "GBP", "FxToGroup": 1.27,
         "AmountVarianceTolerancePct": 1.0, "RoutingVariancePct": 5.0, "MinConfidence": 0.85, "InherentRisk": "Medium"},
        {"CompanyId": "CMP-DE", "Name": "Meridian Manufacturing GmbH", "Currency": "EUR", "FxToGroup": 1.09,
         "AmountVarianceTolerancePct": 0.5, "RoutingVariancePct": 5.0, "MinConfidence": 0.90, "InherentRisk": "Low"},
        {"CompanyId": "CMP-IN", "Name": "Meridian Services Pvt. Ltd.", "Currency": "INR", "FxToGroup": 0.012,
         "AmountVarianceTolerancePct": 1.0, "RoutingVariancePct": 5.0, "MinConfidence": 0.85, "InherentRisk": "High"},
    ],
    "IntercompanyTolerancePct": 0.5,
    "MaterialityPct": 5.0,  # % of tested disbursements (benchmark for a transaction-population test)
}
CO = {c["CompanyId"]: c for c in ORG["Companies"]}
CIDS = list(CO)

# Master vendors per company; a few vendor IDs in documents will be deliberately unlinked.
VENDOR_NAMES = ["Northwind Supply", "Apex Freight", "BlueRidge Packaging", "Orion Components", "Helix Office",
                "Summit Cloud Services", "Kestrel Utilities", "Vantage Print", "Pioneer Tooling", "Lumen Energy"]
VENDORS = {cid: [(f"V-{cid[-2:]}-{i:03d}", n) for i, n in enumerate(VENDOR_NAMES, 1)] for cid in CIDS}

def amount_for(cid):
    base = random.uniform(120, 9500)
    return round(base / CO[cid]["FxToGroup"] if CO[cid]["Currency"] == "INR" else base, 2)

def pii():
    return {
        "VendorIban": "GB%02dBARC%014d" % (random.randint(10, 99), random.randint(10**13, 10**14 - 1)),
        "VendorEmail": f"ap{random.randint(100,999)}@vendor{random.randint(10,99)}.example.com",
        "VendorPhone": "+1-%03d-%03d-%04d" % (random.randint(200, 999), random.randint(200, 999), random.randint(0, 9999)),
        "TaxId": "%03d-%02d-%04d" % (random.randint(100, 899), random.randint(10, 99), random.randint(1000, 9999)),
        "CardLast": "4%03d-%04d-%04d-%04d" % tuple(random.randint(0, 9999) % m for m in (1000, 10000, 10000, 10000)),
    }

ledger, docs, truth = [], [], []
start = date(2026, 1, 5)
seq = 0

def add_ledger(cid, txn, vendor, amt, d, desc, ic=False, cp=""):
    global seq
    seq += 1
    lid = f"L-{seq:04d}"
    ledger.append({"LedgerId": lid, "OrgId": ORG["OrgId"], "CompanyId": cid, "TxnId": txn, "VendorId": vendor,
                   "Amount": f"{amt:.2f}", "Currency": CO[cid]["Currency"], "PostingDate": d.isoformat(),
                   "Description": desc, "IsIntercompany": str(ic).lower(), "CounterpartyCompanyId": cp})
    return lid

def add_doc(cid, txn, vendor_id, vendor_name, amt, d, conf_txn=None, conf_amt=None, conf_vendor=None):
    n = len(docs) + 1
    p = pii()
    docs.append({"DocId": f"D-{n:04d}", "OrgId": ORG["OrgId"], "CompanyId": cid, "TxnId": txn,
                 "VendorId": vendor_id, "VendorName": vendor_name, "Amount": f"{amt:.2f}",
                 "Currency": CO[cid]["Currency"], "InvoiceDate": d.isoformat(), **p,
                 "ConfTxnId": f"{conf_txn or random.uniform(0.93, 0.99):.2f}",
                 "ConfAmount": f"{conf_amt or random.uniform(0.93, 0.99):.2f}",
                 "ConfVendor": f"{conf_vendor or random.uniform(0.93, 0.99):.2f}",
                 "RawText": f"Invoice {txn} from {vendor_name} total {amt:.2f} {CO[cid]['Currency']} "
                            f"IBAN {p['VendorIban']} contact {p['VendorEmail']} {p['VendorPhone']} "
                            f"TaxID {p['TaxId']} card {p['CardLast']}"})

# ---- 440 single-company rows with seeded scenarios --------------------------------
SCENARIOS = (["AUTO_MATCH"] * 292 + ["AUTO_MATCH_TOLERANCE"] * 40 + ["ROUTE_VARIANCE"] * 40 +
             ["ROUTE_UNLINKED_VENDOR"] * 25 + ["ROUTE_LOW_CONFIDENCE"] * 20 + ["UNMATCHED_NO_DOC"] * 15)
random.shuffle(SCENARIOS)
clean = []
for i, sc in enumerate(SCENARIOS, 1):
    cid = CIDS[i % len(CIDS)]
    vid, vname = random.choice(VENDORS[cid])
    amt = amount_for(cid)
    d = start + timedelta(days=random.randint(0, 200))
    txn = f"INV-{cid[-2:]}-{i:05d}"
    lid = add_ledger(cid, txn, vid, amt, d, f"Payment to {vname}")
    tol = CO[cid]["AmountVarianceTolerancePct"] / 100
    if sc == "AUTO_MATCH":
        add_doc(cid, txn, vid, vname, amt, d)
    elif sc == "AUTO_MATCH_TOLERANCE":
        add_doc(cid, txn, vid, vname, round(amt * (1 + random.uniform(-tol, tol) * 0.9), 2), d)
    elif sc == "ROUTE_VARIANCE":
        add_doc(cid, txn, vid, vname, round(amt * (1 + random.choice([-1, 1]) * random.uniform(0.06, 0.25)), 2), d)
    elif sc == "ROUTE_UNLINKED_VENDOR":
        add_doc(cid, txn, f"V-{cid[-2:]}-9{random.randint(10, 99)}", vname, amt, d)
    elif sc == "ROUTE_LOW_CONFIDENCE":
        add_doc(cid, txn, vid, vname, amt, d, conf_amt=round(random.uniform(0.40, 0.80), 2))
    truth.append({"LedgerId": lid, "CompanyId": cid, "ExpectedOutcome": sc})
    if sc == "AUTO_MATCH":
        clean.append((cid, vid, vname, amt, d))

# ---- 8 suspected duplicate payments: same company/vendor/amount/date, new invoice number ----
for k, (cid, vid, vname, amt, d) in enumerate(random.sample(clean, 8), 1):
    txn = f"INV-{cid[-2:]}-D{k:03d}"
    lid = add_ledger(cid, txn, vid, amt, d, f"Payment to {vname}")
    add_doc(cid, txn, vid, vname, amt, d)
    truth.append({"LedgerId": lid, "CompanyId": cid, "ExpectedOutcome": "DUPLICATE_SUSPECT"})

# ---- 6 orphan invoices: a document exists but the ledger has no matching entry (completeness) ----
for k in range(1, 7):
    cid = CIDS[k % len(CIDS)]
    vid, vname = random.choice(VENDORS[cid])
    d = start + timedelta(days=random.randint(0, 200))
    add_doc(cid, f"ORPH-{k:03d}", vid, vname, amount_for(cid), d)
    truth.append({"LedgerId": f"ORPHAN-{k:03d}", "CompanyId": cid, "ExpectedOutcome": "ORPHAN_DOCUMENT"})

# ---- 60 intercompany rows = 30 mirrored pairs (A sells to B) ------------------------
ic_kinds = ["IC_MATCH"] * 25 + ["IC_MISMATCH"] * 5
for k, kind in enumerate(ic_kinds, 1):
    a, b = random.sample(CIDS, 2)
    amt_a = amount_for(a)
    d = start + timedelta(days=random.randint(0, 200))
    txn = f"IC-{k:04d}"
    # B books the same group-currency value in its own currency; mismatches are off by 2-10 %
    amt_b = round(amt_a * CO[a]["FxToGroup"] / CO[b]["FxToGroup"], 2)
    if kind == "IC_MISMATCH":
        amt_b = round(amt_b * (1 + random.choice([-1, 1]) * random.uniform(0.02, 0.10)), 2)
    vid, vname = VENDORS[a][0]
    la = add_ledger(a, txn, vid, amt_a, d, f"Intercompany sale to {CO[b]['Name']}", True, b)
    lb = add_ledger(b, txn, f"V-{b[-2:]}-IC", amt_b, d, f"Intercompany purchase from {CO[a]['Name']}", True, a)
    add_doc(a, txn, vid, vname, amt_a, d)
    truth.append({"LedgerId": la, "CompanyId": a, "ExpectedOutcome": kind})
    truth.append({"LedgerId": lb, "CompanyId": b, "ExpectedOutcome": kind})

assert len(ledger) == 500, len(ledger)

def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader(); w.writerows(rows)

write_csv(ROOT / "data" / "ledger.csv", ledger)
write_csv(ROOT / "data" / "documents.csv", docs)
write_csv(ROOT / "data" / "ground_truth.csv", truth)
(ROOT / "config").mkdir(exist_ok=True)
(ROOT / "config" / "organization.json").write_text(json.dumps(ORG, indent=2), encoding="utf-8")

from collections import Counter
print("ledger", len(ledger), "documents", len(docs))
print(Counter(t["ExpectedOutcome"] for t in truth))
print(Counter(l["CompanyId"] for l in ledger))
