"""Render every synthetic invoice as a PDF (461 documents).

Outputs
  EthicalAuditSolution/EthicalAuditFlow/data/invoices/<DocId>.pdf   the invoice documents
  EthicalAuditSolution/EthicalAuditFlow/data/du_batch.csv           manifest (what each PDF should contain)
  EthicalAuditSolution/EthicalAuditFlow/data/vendor_master.csv      approved vendors per company (name -> id)
  data/ (repo root) gets the same files so the generator output stays in one place.
Digital PDFs for most; the 'low confidence' invoices are rasterised, blurred, skewed and noisy (a poor scan).
All people, banks and cards are synthetic.
"""
import csv, io, random, shutil
from pathlib import Path

from PIL import Image, ImageFilter
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

random.seed(7)
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
FLOW = ROOT / "EthicalAuditSolution" / "EthicalAuditFlow" / "data"
OUT = FLOW / "invoices"
OUT.mkdir(parents=True, exist_ok=True)

docs = {(r["CompanyId"], r["TxnId"]): r for r in csv.DictReader(open(DATA / "documents.csv", encoding="utf-8"))}
truth = {r["LedgerId"]: r for r in csv.DictReader(open(DATA / "ground_truth.csv", encoding="utf-8"))}
ledger = {r["LedgerId"]: r for r in csv.DictReader(open(DATA / "ledger.csv", encoding="utf-8"))}
companies = {r["CompanyId"]: r for r in csv.DictReader(open(FLOW / "companies.csv", encoding="utf-8"))}

# vendor master: the ten approved vendors per company (same naming as the generator)
NAMES = ["Northwind Supply", "Apex Freight", "BlueRidge Packaging", "Orion Components", "Helix Office",
         "Summit Cloud Services", "Kestrel Utilities", "Vantage Print", "Pioneer Tooling", "Lumen Energy"]
master = []
for cid in companies:
    for i, n in enumerate(NAMES, 1):
        master.append({"CompanyId": cid, "VendorId": f"V-{cid[-2:]}-{i:03d}", "VendorName": n})
for d in (FLOW, DATA):
    with open(d / "vendor_master.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["CompanyId", "VendorId", "VendorName"])
        w.writeheader(); w.writerows(master)

# ---- every invoice gets a PDF; the scenario decides how it is rendered -------------------------------------
ledger_outcome = {(l["CompanyId"], l["TxnId"]): truth[lid]["ExpectedOutcome"] for lid, l in ledger.items()}
chosen = []   # (docrow, outcome)
for (cid, txn), d in sorted(docs.items(), key=lambda kv: kv[1]["DocId"]):
    outcome = "ORPHAN_DOCUMENT" if txn.startswith("ORPH-") else ledger_outcome.get((cid, txn), "AUTO_MATCH")
    chosen.append((d, outcome))

NAME_TO_ID = {(m["CompanyId"], m["VendorId"]): m["VendorName"] for m in master}


def render(d, outcome, path, scan):
    cid = d["CompanyId"]
    co = companies[cid]["Name"]
    vendor = d["VendorName"]
    amt = float(d["Amount"])
    cur = d["Currency"]
    # an 'unlinked vendor' invoice names a vendor that is not in the vendor master (spelling differs)
    if outcome == "ROUTE_UNLINKED_VENDOR":
        vendor = vendor.replace("Components", "Componentz").replace("Supply", "Supplies").replace("Print", "Prints") + " Ltd"
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
    c.setFont("Helvetica", 10); c.drawString(20 * mm, H - 86 * mm, co)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(20 * mm, H - 105 * mm, "Description"); c.drawString(140 * mm, H - 105 * mm, "Amount")
    c.line(20 * mm, H - 107 * mm, 190 * mm, H - 107 * mm)
    c.setFont("Helvetica", 10)
    c.drawString(20 * mm, H - 114 * mm, f"Goods and services supplied to {co}")
    c.drawString(140 * mm, H - 114 * mm, f"{amt:,.2f}")
    c.setFont("Helvetica-Bold", 12)
    c.drawString(105 * mm, H - 135 * mm, "Total due:")
    c.drawString(140 * mm, H - 135 * mm, f"{amt:,.2f} {cur}")
    c.setFont("Helvetica", 9)
    c.drawString(20 * mm, H - 160 * mm, "Payment details")
    c.drawString(20 * mm, H - 166 * mm, f"IBAN: {d['VendorIban']}")
    c.drawString(20 * mm, H - 172 * mm, f"Card on file: {d['CardLast']}")
    c.showPage(); c.save()
    pdf = buf.getvalue()
    if not scan:
        path.write_bytes(pdf)
        return
    # poor scan: rasterise, blur, skew, add noise, save as an image-only PDF
    try:
        import fitz  # PyMuPDF, optional
        pix = fitz.open(stream=pdf, filetype="pdf")[0].get_pixmap(dpi=110)
        img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("L")
    except Exception:
        raise SystemExit("PyMuPDF is required to rasterise the low-quality scans: pip install pymupdf")
    img = img.rotate(random.uniform(-2.5, 2.5), expand=True, fillcolor=255).filter(ImageFilter.GaussianBlur(1.4))
    px = img.load()
    for _ in range(img.width * img.height // 25):
        x, y2 = random.randrange(img.width), random.randrange(img.height)
        px[x, y2] = max(0, min(255, px[x, y2] + random.randint(-70, 70)))
    img.convert("RGB").save(path, "PDF", resolution=110)


rows = []
for d, outcome in chosen:
    scan = outcome == "ROUTE_LOW_CONFIDENCE"
    p = OUT / f"{d['TxnId']}.pdf"
    render(d, outcome, p, scan)
    rows.append({"DocId": d["DocId"], "CompanyId": d["CompanyId"], "TxnId": d["TxnId"], "Scenario": outcome,
                 "Scanned": str(scan).lower(), "ExpectedVendorName": d["VendorName"], "ExpectedAmount": d["Amount"],
                 "ExpectedCurrency": d["Currency"], "ExpectedDate": d["InvoiceDate"]})
for dst in (FLOW, DATA):
    with open(dst / "du_batch.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
shutil.copytree(OUT, DATA / "invoices", dirs_exist_ok=True)
from collections import Counter
print(len(rows), "invoices;", dict(Counter(r["Scenario"] for r in rows)))
