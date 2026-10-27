"""Generate the general-ledger journal data for journal-entry testing (deterministic, synthetic).

For each data set (group and standalone) writes four files next to its ledger:
  journal.csv      manual and system journal entries (JournalId, posting date-time, preparer, description, amount ...)
  jv_config.csv    per-company settings: approval limit, night hours, round-number rule
  holidays.csv     public holidays per company (illustrative calendar)
  jv_truth.csv     which risk flags each entry should raise (used only to score the test)
Manual entries are tested; system entries (scheduled runs) are not.
All names, addresses and numbers are synthetic.
"""
import csv, random
from datetime import date, datetime, timedelta
from pathlib import Path

random.seed(11)
ROOT = Path(__file__).resolve().parent.parent
FLOW = ROOT / "EthicalAuditSolution" / "EthicalAuditFlow"

# company -> (org, currency, approval limit, round unit, round minimum, holiday calendar, user code)
CONFIG = {
    "CMP-US": ("ORG-001", "USD", 15000, 5000, 5000, "US"),
    "CMP-UK": ("ORG-001", "GBP", 12000, 5000, 5000, "UK"),
    "CMP-DE": ("ORG-001", "EUR", 14000, 5000, 5000, "DE"),
    "CMP-IN": ("ORG-001", "INR", 800000, 100000, 100000, "IN"),
    "CMP-HB": ("ORG-002", "USD", 10000, 2500, 2500, "US"),
}
HOLIDAYS = {
    "US": [("2026-01-01", "New Year's Day"), ("2026-01-19", "Martin Luther King Jr. Day"), ("2026-05-25", "Memorial Day"),
           ("2026-09-07", "Labor Day"), ("2026-11-26", "Thanksgiving"), ("2026-12-25", "Christmas Day")],
    "UK": [("2026-01-01", "New Year's Day"), ("2026-04-03", "Good Friday"), ("2026-04-06", "Easter Monday"),
           ("2026-05-04", "Early May bank holiday"), ("2026-05-25", "Spring bank holiday"),
           ("2026-08-31", "Summer bank holiday"), ("2026-12-25", "Christmas Day")],
    "DE": [("2026-01-01", "New Year's Day"), ("2026-04-03", "Good Friday"), ("2026-04-06", "Easter Monday"),
           ("2026-05-01", "Labour Day"), ("2026-05-14", "Ascension Day"), ("2026-05-25", "Whit Monday"),
           ("2026-12-25", "Christmas Day"), ("2026-12-26", "Second Christmas Day")],
    "IN": [("2026-01-26", "Republic Day"), ("2026-03-04", "Holi"), ("2026-10-02", "Gandhi Jayanti"),
           ("2026-11-09", "Diwali"), ("2026-12-25", "Christmas Day")],
}
NIGHT_START, NIGHT_END = 23, 5
CLEAN_DESC = ["Accrual for utilities", "Depreciation charge for the month", "Reclassification of prepaid insurance",
              "Payroll accrual", "Bank charges accrual", "Intercompany recharge of shared services",
              "Provision for doubtful debts", "Month-end close entry", "Prepaid rent release",
              "Capitalised software amortisation", "Accrued audit fees", "Lease liability interest"]
KEYWORD_DESC = ["Adjustment per management instruction", "Plug to balance the sub-ledger", "Correction of posting error",
                "Adjust opening balance as instructed", "Override of system calculation", "Misc suspense clearing",
                "Per CFO instruction - reclass", "Manual fix of reconciliation difference"]
PII_DESC = ["Adjustment requested by m.rao@meridian.example.com, call +44 207 123 4567",
            "Plug entry per instruction of j.walker@meridian.example.com",
            "Error correction, contact +1-415-555-0142 or a.silva@meridian.example.com"]
SYSTEM_DESC = ["Scheduled depreciation run", "Automated FX revaluation", "Auto adjustment from bank feed",
               "Recurring rent allocation", "Automatic accrual reversal"]


def is_holiday(cal, d):
    return d.isoformat() in {h[0] for h in HOLIDAYS[cal]}


def weekday_date(cal, want_holiday=False, want_weekend=False):
    if want_holiday:
        pool = [date.fromisoformat(h[0]) for h in HOLIDAYS[cal] if date.fromisoformat(h[0]).weekday() < 5 and date.fromisoformat(h[0]) <= date(2026, 10, 2)]
        return random.choice(pool)
    while True:
        d = date(2026, 1, 5) + timedelta(days=random.randint(0, 270))
        if want_weekend and d.weekday() >= 5 and not is_holiday(cal, d):
            return d
        if not want_weekend and d.weekday() < 5 and not is_holiday(cal, d):
            return d


def clean_amount(limit, unit):
    while True:
        a = round(random.uniform(300, 0.8 * limit * random.choice([0.2, 0.5, 1.0])), 2)
        if a % unit != 0 and a < 0.93 * limit:
            return a


def build(cid, n_manual, n_system, plan, users):
    org, cur, limit, unit, rmin, cal = CONFIG[cid]
    code = cid[-2:]
    rows, truth = [], []
    seq = [0]

    def add(day, hour, minute, source, desc, amount, flags):
        seq[0] += 1
        jid = f"JV-{code}-{seq[0]:04d}"
        user = "SYSTEM" if source == "System" else random.choice(users)
        rows.append({"JournalId": jid, "OrgId": org, "CompanyId": cid,
                     "PostingDateTime": datetime(day.year, day.month, day.day, hour, minute).strftime("%Y-%m-%d %H:%M"),
                     "PostedBy": user, "Source": source, "Description": desc, "Amount": f"{amount:.2f}",
                     "Currency": cur, "Account": random.choice(["6100", "6200", "2100", "1300", "4900"])})
        truth.append({"JournalId": jid, "CompanyId": cid, "Source": source,
                      "ExpectedFlags": ";".join(sorted(flags)) if source == "Manual" else ""})

    def day_hour(flags):
        wk = "WEEKEND" in flags
        hol = "HOLIDAY" in flags
        d = weekday_date(cal, want_holiday=hol, want_weekend=wk and not hol)
        hour = random.choice([23, 0, 1, 2, 3, 4]) if "NIGHT" in flags else random.randint(9, 17)
        return d, hour, random.randint(0, 59)

    for flags, count in plan:
        for _ in range(count):
            fl = set(flags)
            d, h, m = day_hour(fl)
            if "BLANK" in fl:
                desc = random.choice(["", "   "])
            elif "KEYWORD" in fl:
                desc = random.choice(PII_DESC + KEYWORD_DESC) if random.random() < 0.35 else random.choice(KEYWORD_DESC)
            else:
                desc = random.choice(CLEAN_DESC)
            if "ROUND" in fl:
                amt = float(random.choice([k for k in range(int(rmin), int(0.9 * limit), int(unit))]))
            elif "BELOW_LIMIT" in fl:
                amt = round(limit * random.uniform(0.955, 0.995), 2)
            else:
                amt = clean_amount(limit, unit)
            add(d, h, m, "Manual", desc, amt, fl)
    done = len(rows)
    for _ in range(n_manual - done):
        d, h, m = day_hour(set())
        add(d, h, m, "Manual", random.choice(CLEAN_DESC), clean_amount(limit, unit), set())
    for i in range(n_system):
        d = date(2026, 1, 5) + timedelta(days=random.randint(0, 270))
        # system entries may post on weekends, at night, with 'adjust' wording: they are not tested
        add(d, random.choice([2, 3, 4, 23, 12, 15]), random.randint(0, 59), "System", random.choice(SYSTEM_DESC),
            clean_amount(limit, unit), set())
    random.shuffle(rows)
    return rows, truth


GROUP_PLAN = [({"WEEKEND"}, 4), ({"HOLIDAY"}, 3), ({"NIGHT"}, 4), ({"KEYWORD"}, 5), ({"BLANK"}, 2), ({"ROUND"}, 4),
              ({"BELOW_LIMIT"}, 3), ({"WEEKEND", "KEYWORD"}, 2), ({"NIGHT", "ROUND"}, 1), ({"HOLIDAY", "BELOW_LIMIT"}, 1)]
SOLO_PLAN = [({"WEEKEND"}, 3), ({"HOLIDAY"}, 2), ({"NIGHT"}, 3), ({"KEYWORD"}, 4), ({"BLANK"}, 2), ({"ROUND"}, 3),
             ({"BELOW_LIMIT"}, 2), ({"WEEKEND", "KEYWORD"}, 1), ({"NIGHT", "ROUND"}, 1)]


def write(folder, cids, plan, n_manual, n_system):
    folder.mkdir(parents=True, exist_ok=True)
    rows, truth, conf, hols = [], [], [], []
    for cid in cids:
        users = [f"USR-{cid[-2:]}-{i:02d}" for i in range(1, 7)]
        r, t = build(cid, n_manual, n_system, plan, users)
        rows += r; truth += t
        org, cur, limit, unit, rmin, cal = CONFIG[cid]
        conf.append({"CompanyId": cid, "ApprovalLimit": limit, "NightStartHour": NIGHT_START, "NightEndHour": NIGHT_END,
                     "RoundUnit": unit, "RoundMinimum": rmin})
        hols += [{"CompanyId": cid, "Date": d, "Name": n} for d, n in HOLIDAYS[cal]]
    for name, data in (("journal.csv", rows), ("jv_truth.csv", truth), ("jv_config.csv", conf), ("holidays.csv", hols)):
        with open(folder / name, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(data[0])); w.writeheader(); w.writerows(data)
    flagged = sum(1 for t in truth if t["ExpectedFlags"])
    print(folder.name, "entries", len(rows), "manual flagged", flagged)


write(FLOW / "data", ["CMP-US", "CMP-UK", "CMP-DE", "CMP-IN"], GROUP_PLAN, 60, 20)
write(FLOW / "data_standalone", ["CMP-HB"], SOLO_PLAN, 50, 15)
