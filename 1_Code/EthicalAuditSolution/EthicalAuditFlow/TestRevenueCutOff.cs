using System;
using System.Collections.Generic;
using System.Data;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text;
using UiPath.CodedWorkflows;

namespace EthicalAuditFlow
{
    public class TestRevenueCutOff : CodedWorkflow
    {
        /// <summary>
        /// Revenue cut-off and credit-note test. Sales invoices dated within the cut-off window around each company's
        /// fiscal year-end are checked against their shipping date (revenue recorded in the wrong year, or with no
        /// shipping record). Credit notes issued shortly after year-end are checked for large amounts and for reversing
        /// a sale made in the last days of the year. A flag is a risk indicator that a reviewer must confirm.
        /// Skipped in Baseline mode. If the data folder has no sales file, nothing is tested.
        /// Outcome REV_CUTOFF = invoice exceptions, REV_CREDIT = credit-note exceptions.
        /// </summary>
        [Workflow]
        public (DataTable flags, string summary) Execute(string dataFolder, DataTable companies, bool ethical)
        {
            var flags = Calc.Table("OrgId", "CompanyId", "DocumentNo", "Outcome", "Flags", "Reason", "Amount", "Currency", "AmountUSD", "Evidence");
            if (!ethical)
            {
                Log("Revenue cut-off test not performed (Baseline)", LogLevel.Warn);
                return (flags, "RvTested=0 (not performed in Baseline)");
            }
            var sales = Read(Path.Combine(dataFolder, "sales.csv"));
            if (sales == null)
            {
                Log("No sales file in " + dataFolder + "; revenue cut-off test skipped", LogLevel.Warn);
                return (flags, "RvTested=0 (no sales file)");
            }
            var config = (Read(Path.Combine(dataFolder, "fiscal_config.csv")) ?? new List<Dictionary<string, string>>())
                .ToDictionary(r => r["CompanyId"]);
            var truth = Read(Path.Combine(dataFolder, "sales_truth.csv"));
            var redactor = new RedactionEngine(Guid.NewGuid().ToString("N"));
            var inv = CultureInfo.InvariantCulture;
            var byNo = sales.ToDictionary(r => r["CompanyId"] + "|" + r["DocumentNo"]);

            var tested = 0;
            foreach (var s in sales)
            {
                var co = s["CompanyId"];
                if (!config.TryGetValue(co, out var cfg)) continue;
                var ye = DateTime.ParseExact(cfg["FiscalYearEnd"], "yyyy-MM-dd", inv);
                var cut = int.Parse(cfg["CutOffDays"], inv); var win = int.Parse(cfg["CreditWindowDays"], inv);
                var thr = decimal.Parse(cfg["CreditThreshold"], inv);
                var date = DateTime.ParseExact(s["DocumentDate"], "yyyy-MM-dd", inv);
                var amount = decimal.Parse(s["Amount"], inv);
                var hit = new List<string>(); var why = new List<string>(); string outcome; string evidence;

                if (s["Type"] == "Invoice")
                {
                    if (Math.Abs((date - ye).Days) > cut) continue;
                    tested++; outcome = "REV_CUTOFF";
                    DateTime? ship = s["ShipDate"].Length == 0 ? (DateTime?)null : DateTime.ParseExact(s["ShipDate"], "yyyy-MM-dd", inv);
                    if (ship == null) { hit.Add("NO_SHIP_DATE"); why.Add("no shipping record for a sale dated " + s["DocumentDate"] + ", close to year-end " + cfg["FiscalYearEnd"]); }
                    else if (date <= ye && ship.Value > ye) { hit.Add("CUTOFF_EARLY"); why.Add("recorded " + s["DocumentDate"] + " (this year) but shipped " + s["ShipDate"] + " (after year-end " + cfg["FiscalYearEnd"] + ")"); }
                    else if (date > ye && ship.Value <= ye) { hit.Add("CUTOFF_LATE"); why.Add("recorded " + s["DocumentDate"] + " (after year-end " + cfg["FiscalYearEnd"] + ") but shipped " + s["ShipDate"] + " (this year)"); }
                    evidence = "invoice " + s["DocumentNo"] + " to " + s["CustomerName"] + "; invoice date " + s["DocumentDate"] + "; ship date " + (s["ShipDate"].Length == 0 ? "(none)" : s["ShipDate"]);
                }
                else
                {
                    if (date <= ye || date > ye.AddDays(win)) continue;
                    tested++; outcome = "REV_CREDIT";
                    if (amount >= thr) { hit.Add("CREDIT_AFTER_YE"); why.Add("large credit note issued " + (date - ye).Days + " days after year-end (threshold " + thr.ToString("N0", inv) + ")"); }
                    var orig = s["OriginalInvoice"].Length > 0 && byNo.TryGetValue(co + "|" + s["OriginalInvoice"], out var o) ? o : null;
                    if (orig != null)
                    {
                        var od = DateTime.ParseExact(orig["DocumentDate"], "yyyy-MM-dd", inv);
                        if (od >= ye.AddDays(-cut) && od <= ye)
                        { hit.Add("CREDIT_REVERSES_YE_SALE"); why.Add("reverses invoice " + orig["DocumentNo"] + " dated " + orig["DocumentDate"] + ", in the last " + cut + " days of the year"); }
                    }
                    var reason = s["Reason"].Trim();
                    evidence = "credit note " + s["DocumentNo"] + " against " + s["OriginalInvoice"] + " for " + s["CustomerName"] + "; reason: " +
                               (reason.Length == 0 ? "(blank)" : redactor.Redact(reason.Length > 120 ? reason.Substring(0, 120) : reason));
                }
                if (hit.Count == 0) continue;
                var usd = Calc.S((double)amount * Calc.D(Calc.Company(companies, co)["FxToGroup"]));
                flags.Rows.Add(s["OrgId"], co, s["DocumentNo"], outcome, string.Join(";", hit),
                               "[" + string.Join(", ", hit) + "] " + string.Join("; ", why), s["Amount"], s["Currency"], usd, evidence);
            }

            var summary = "RvTested=" + tested + "; RvFlagged=" + flags.Rows.Count;
            if (truth != null)
            {
                var expected = truth.Where(t => t["ExpectedFlags"].Length > 0).ToDictionary(t => t["DocumentNo"], t => t["ExpectedFlags"]);
                var actual = flags.AsEnumerable().ToDictionary(r => r["DocumentNo"].ToString(),
                    r => string.Join(";", r["Flags"].ToString().Split(';').OrderBy(x => x, StringComparer.Ordinal)));
                var exact = expected.Count(e => actual.TryGetValue(e.Key, out var a) && a == e.Value);
                summary += "; RvExpected=" + expected.Count + "; RvExactMatches=" + exact + "; RvFalseFlags=" + actual.Count(a => !expected.ContainsKey(a.Key));
            }
            Log("Revenue cut-off test: " + summary);
            return (flags, summary);
        }

        // Minimal CSV reader (quoted fields, doubled quotes, embedded commas). Returns null if the file does not exist.
        private static List<Dictionary<string, string>> Read(string path)
        {
            if (!File.Exists(path)) return null;
            var text = File.ReadAllText(path, Encoding.UTF8).TrimStart('﻿');
            var rows = new List<List<string>>(); var row = new List<string>(); var cell = new StringBuilder(); var q = false;
            for (var i = 0; i < text.Length; i++)
            {
                var c = text[i];
                if (q)
                {
                    if (c == '"') { if (i + 1 < text.Length && text[i + 1] == '"') { cell.Append('"'); i++; } else q = false; }
                    else cell.Append(c);
                }
                else if (c == '"') q = true;
                else if (c == ',') { row.Add(cell.ToString()); cell.Clear(); }
                else if (c == '\n' || c == '\r')
                {
                    if (c == '\r' && i + 1 < text.Length && text[i + 1] == '\n') i++;
                    row.Add(cell.ToString()); cell.Clear(); rows.Add(row); row = new List<string>();
                }
                else cell.Append(c);
            }
            if (cell.Length > 0 || row.Count > 0) { row.Add(cell.ToString()); rows.Add(row); }
            rows = rows.Where(r => r.Count > 1 || (r.Count == 1 && r[0].Length > 0)).ToList();
            if (rows.Count == 0) return new List<Dictionary<string, string>>();
            var head = rows[0];
            return rows.Skip(1).Select(r => head.Select((h, k) => new { h, v = k < r.Count ? r[k] : "" }).ToDictionary(x => x.h, x => x.v)).ToList();
        }
    }
}
