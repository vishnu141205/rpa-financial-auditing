"""Generate the standalone-company dataset: one independent organization with a single company (no intercompany).

Outputs EthicalAuditSolution/EthicalAuditFlow/data_standalone/ (ledger, documents, ground truth, vendor master,
du_batch, companies and invoices/<DocId>.pdf). Run the workflow on it with in_DataFolder = data_standalone.
All names, banks and cards are synthetic.
"""
import csv, io, random
from datetime import date, timedelta
from pathlib import Path

from PIL import Image, ImageFilter
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

random.seed(2026)
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "EthicalAuditSolution" / "EthicalAuditFlow" / "data_standalone"
INV = OUT / "invoices"
INV.mkdir(parents=True, exist_ok=True)

ORG, CID, CNAME, CUR = "ORG-002", "CMP-HB", "Harbor Supplies Inc.", "USD"
TOL, MINCONF, RISK = 1.0, 0.85, "Medium"
NAMES = ["Redwood Timber", "Clearwater Logistics", "Ironbark Hardware", "Beacon Chemicals", "Coastal Packaging",
         "Falcon Fasteners", "Granite Paper Co", "Willow Stationery", "Harvest Foods", "Tidewater Fuel"]
VENDORS = [(f"V-HB-{i:03d}", n) for i, n in enumerate(NAMES, 1)]
start = date(2026, 2, 2)

ledger, docs, truth = [], [], []


def pii():
    return {
        "VendorIban": "GB%02dBARC%014d" % (random.randint(10, 99), random.randint(10**13, 10**14 - 1)),
        "VendorEmail": f"ap{random.randint(100,999)}@supplier{random.randint(10,99)}.example.com",
        "VendorPhone": "+1-%03d-%03d-%04d" % (random.randint(200, 999), random.randint(200, 999), random.randint(0, 9999)),
        "TaxId": "%03d-%02d-%04d" % (random.randint(100, 899), random.randint(10, 99), random.randint(1000, 9999)),
        "CardLast": "4%03d-%04d-%04d-%04d" % tuple(random.randint(0, 9999) % m for m in (1000, 10000, 10000, 10000)),
    }


def add_ledger(txn, vendor, amt, d, desc):
    lid = f"L-{len(ledger) + 1:04d}"
    ledger.append({"LedgerId": lid, "OrgId": ORG, "CompanyId": CID, "TxnId": txn, "VendorId": vendor,
                   "Amount": f"{amt:.2f}", "Currency": CUR, "PostingDate": d.isoformat(), "Description": desc,
                   "IsIntercompany": "false", "CounterpartyCompanyId": ""})
    return lid


def add_doc(txn, vendor_id, vendor_name, amt, d, conf_amt=None):
    p = pii()
    docs.append({"DocId": f"D-{len(docs) + 1:04d}", "OrgId": ORG, "CompanyId": CID, "TxnId": txn,
                 "VendorId": vendor_id, "VendorName": vendor_name, "Amount": f"{amt:.2f}", "Currency": CUR,
                 "InvoiceDate": d.isoformat(), **p,
                 "ConfTxnId": f"{random.uniform(0.93, 0.99):.2f}",
                 "ConfAmount": f"{conf_amt or random.uniform(0.93, 0.99):.2f}",
                 "ConfVendor": f"{random.uniform(0.93, 0.99):.2f}",
                 "RawText": f"Invoice {txn} from {vendor_name} total {amt:.2f} {CUR} IBAN {p['VendorIban']} "
                            f"contact {p['VendorEmail']} {p['VendorPhone']} TaxID {p['TaxId']} card {p['CardLast']}"})


SCEN = (["AUTO_MATCH"] * 68 + ["AUTO_MATCH_TOLERANCE"] * 10 + ["ROUTE_VARIANCE"] * 8 + ["ROUTE_UNLINKED_VENDOR"] * 5 +
        ["ROUTE_LOW_CONFIDENCE"] * 4 + ["UNMATCHED_NO_DOC"] * 3)
random.shuffle(SCEN)
clean = []
for i, sc in enumerate(SCEN, 1):
    vid, vname = random.choice(VENDORS)
    amt = round(random.uniform(150, 9000), 2)
    d = start + timedelta(days=random.randint(0, 200))
    txn = f"INV-HB-{i:05d}"
    lid = add_ledger(txn, vid, amt, d, f"Payment to {vname}")
    if sc == "AUTO_MATCH":
        add_doc(txn, vid, vname, amt, d); clean.append((vid, vname, amt, d))
    elif sc == "AUTO_MATCH_TOLERANCE":
        add_doc(txn, vid, vname, round(amt * (1 + random.uniform(-TOL, TOL) / 100 * 0.9), 2), d)
    elif sc == "ROUTE_VARIANCE":
        add_doc(txn, vid, vname, round(amt * (1 + random.choice([-1, 1]) * random.uniform(0.06, 0.25)), 2), d)
    elif sc == "ROUTE_UNLINKED_VENDOR":
        add_doc(txn, f"V-HB-9{random.randint(10, 99)}", vname, amt, d)
    elif sc == "ROUTE_LOW_CONFIDENCE":
        add_doc(txn, vid, vname, amt, d, conf_amt=round(random.uniform(0.40, 0.80), 2))
    truth.append({"LedgerId": lid, "CompanyId": CID, "ExpectedOutcome": sc})

for k, (vid, vname, amt, d) in enumerate(random.sample(clean, 2), 1):
    txn = f"INV-HB-D{k:03d}"
    lid = add_ledger(txn, vid, amt, d, f"Payment to {vname}")
    add_doc(txn, vid, vname, amt, d)
    truth.append({"LedgerId": lid, "CompanyId": CID, "ExpectedOutcome": "DUPLICATE_SUSPECT"})

for k in range(1, 3):
    vid, vname = random.choice(VENDORS)
    add_doc(f"ORPH-{k:03d}", vid, vname, round(random.uniform(150, 9000), 2), start + timedelta(days=random.randint(0, 200)))
    truth.append({"LedgerId": f"ORPHAN-{k:03d}", "CompanyId": CID, "ExpectedOutcome": "ORPHAN_DOCUMENT"})

assert len(ledger) == 100, len(ledger)


def write_csv(name, rows, fields=None):
    with open(OUT / name, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields or list(rows[0])); w.writeheader(); w.writerows(rows)


write_csv("companies.csv", [{"OrgId": ORG, "CompanyId": CID, "Name": CNAME, "Currency": CUR, "FxToGroup": "1.0",
                             "TolerancePct": TOL, "MinConfidence": MINCONF, "IcTolerancePct": "0.5",
                             "InherentRisk": RISK, "MaterialityPct": "5.0"}])
write_csv("ledger.csv", ledger)
write_csv("documents.csv", docs)
write_csv("ground_truth.csv", truth)
write_csv("vendor_master.csv", [{"CompanyId": CID, "VendorId": v, "VendorName": n} for v, n in VENDORS])

outcome_of = {l["TxnId"]: next(t["ExpectedOutcome"] for t in truth if t["LedgerId"] == l["LedgerId"]) for l in ledger}


def render(d, outcome, path, scan):
    vendor = d["VendorName"]
    amt = float(d["Amount"])
    if outcome == "ROUTE_UNLINKED_VENDOR":
        vendor = vendor.replace("Hardware", "Hardwares").replace("Timber", "Timbers").replace("Foods", "Food") + " Ltd"
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    W, H = A4
    c.setFont("Helvetica-Bold", 22); c.drawString(20 * mm, H - 25 * mm, "INVOICE")
    c.setFont("Helvetica-Bold", 13); c.drawString(20 * mm, H - 40 * mm, vendor)
    c.setFont("Helvetica", 10)
    y = H - 47 * mm
    for line in (f"Email: {d['VendorEmail']}", f"Phone: {d['VendorPhone']}", f"Tax ID: {d['TaxId']}"):
        c.drawString(20 * mm, y, line); y -= 5 * mm
    c.setFont("Helvetica-Bold", 10); c.drawString(120 * mm, H - 40 * mm, "Invoice number:")
    c.setFont("Helvetica", 10); c.drawString(150 * mm, H - 40 * mm, d["TxnId"])
    c.setFont("Helvetica-Bold", 10); c.drawString(120 * mm, H - 46 * mm, "Invoice date:")
    c.setFont("Helvetica", 10); c.drawString(150 * mm, H - 46 * mm, d["InvoiceDate"])
    c.setFont("Helvetica-Bold", 10); c.drawString(20 * mm, H - 80 * mm, "Bill to:")
    c.setFont("Helvetica", 10); c.drawString(20 * mm, H - 86 * mm, CNAME)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(20 * mm, H - 105 * mm, "Description"); c.drawString(140 * mm, H - 105 * mm, "Amount")
    c.line(20 * mm, H - 107 * mm, 190 * mm, H - 107 * mm)
    c.setFont("Helvetica", 10)
    c.drawString(20 * mm, H - 114 * mm, f"Goods and services supplied to {CNAME}")
    c.drawString(140 * mm, H - 114 * mm, f"{amt:,.2f}")
    c.setFont("Helvetica-Bold", 12)
    c.drawString(105 * mm, H - 135 * mm, "Total due:")
    c.drawString(140 * mm, H - 135 * mm, f"{amt:,.2f} {CUR}")
    c.setFont("Helvetica", 9)
    c.drawString(20 * mm, H - 160 * mm, "Payment details")
    c.drawString(20 * mm, H - 166 * mm, f"IBAN: {d['VendorIban']}")
    c.drawString(20 * mm, H - 172 * mm, f"Card on file: {d['CardLast']}")
    c.showPage(); c.save()
    pdf = buf.getvalue()
    if not scan:
        path.write_bytes(pdf)
        return
    import fitz
    pix = fitz.open(stream=pdf, filetype="pdf")[0].get_pixmap(dpi=110)
    img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("L")
    img = img.rotate(random.uniform(-2.5, 2.5), expand=True, fillcolor=255).filter(ImageFilter.GaussianBlur(1.4))
    px = img.load()
    for _ in range(img.width * img.height // 25):
        x, y2 = random.randrange(img.width), random.randrange(img.height)
        px[x, y2] = max(0, min(255, px[x, y2] + random.randint(-70, 70)))
    img.convert("RGB").save(path, "PDF", resolution=110)


batch = []
for d in docs:
    oc = "ORPHAN_DOCUMENT" if d["TxnId"].startswith("ORPH-") else outcome_of.get(d["TxnId"], "AUTO_MATCH")
    scan = oc == "ROUTE_LOW_CONFIDENCE"
    render(d, oc, INV / f"{d['TxnId']}.pdf", scan)
    batch.append({"DocId": d["DocId"], "CompanyId": CID, "TxnId": d["TxnId"], "Scenario": oc, "Scanned": str(scan).lower(),
                  "ExpectedVendorName": d["VendorName"], "ExpectedAmount": d["Amount"], "ExpectedCurrency": CUR,
                  "ExpectedDate": d["InvoiceDate"]})
write_csv("du_batch.csv", batch)

from collections import Counter
print("ledger", len(ledger), "documents", len(docs), "pdfs", len(list(INV.glob('*.pdf'))))
print(Counter(t["ExpectedOutcome"] for t in truth))
