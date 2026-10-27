using System;
using System.Collections.Generic;
using System.Data;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.RegularExpressions;
using UiPath.CodedWorkflows;

namespace EthicalAuditFlow
{
    public class TestJournalEntries : CodedWorkflow
    {
        private static readonly string[] Keywords =
        {
            "plug", "error", "adjust", "per management", "per cfo", "per ceo", "as instructed", "override", "suspense", "misc", "manual fix"
        };

        /// <summary>
        /// Journal-entry (management override) test. Reads the general-ledger journal, tests every MANUAL entry and flags
        /// risk indicators: weekend, public-holiday or night posting, risky wording (or no description), round amounts,
        /// and amounts just below the approval limit. System entries are not tested. A flag is a risk indicator, not
        /// a proven error, so each flagged entry goes to a reviewer. Descriptions are redacted before they are kept.
        /// Skipped in Baseline mode. If the data folder has no journal file, nothing is tested.
        /// </summary>
        [Workflow]
        public (DataTable flags, string summary) Execute(string dataFolder, DataTable companies, bool ethical)
        {
            var flags = Calc.Table("OrgId", "CompanyId", "JournalId", "Flags", "Reason", "Amount", "Currency", "AmountUSD", "Evidence");
            if (!ethical)
            {
                Log("Journal-entry test not performed (Baseline)", LogLevel.Warn);
                return (flags, "JvTested=0 (not performed in Baseline)");
            }
            var journal = Read(Path.Combine(dataFolder, "journal.csv"));
            if (journal == null)
            {
                Log("No journal file in " + dataFolder + "; journal-entry test skipped", LogLevel.Warn);
                return (flags, "JvTested=0 (no journal file)");
            }
            var config = (Read(Path.Combine(dataFolder, "jv_config.csv")) ?? new List<Dictionary<string, string>>())
                .ToDictionary(r => r["CompanyId"]);
            var holidays = (Read(Path.Combine(dataFolder, "holidays.csv")) ?? new List<Dictionary<string, string>>())
                .GroupBy(r => r["CompanyId"] + "|" + r["Date"]).ToDictionary(g => g.Key, g => g.First()["Name"]);
            var truth = Read(Path.Combine(dataFolder, "jv_truth.csv"));
            var redactor = new RedactionEngine(Guid.NewGuid().ToString("N"));
            var inv = CultureInfo.InvariantCulture;

            var tested = 0;
            foreach (var j in journal.Where(r => r["Source"] == "Manual"))
            {
                tested++;
                var co = j["CompanyId"];
                if (!config.TryGetValue(co, out var cfg)) continue;
                var when = DateTime.ParseExact(j["PostingDateTime"], "yyyy-MM-dd HH:mm", inv);
                var amount = decimal.Parse(j["Amount"], inv);
                var desc = (j["Description"] ?? "").Trim();
                var hit = new List<string>(); var why = new List<string>();

                if (when.DayOfWeek == DayOfWeek.Saturday || when.DayOfWeek == DayOfWeek.Sunday)
                { hit.Add("WEEKEND"); why.Add("posted on a weekend (" + when.ToString("ddd yyyy-MM-dd HH:mm", inv) + ")"); }
                if (holidays.TryGetValue(co + "|" + when.ToString("yyyy-MM-dd"), out var hname))
                { hit.Add("HOLIDAY"); why.Add("posted on a public holiday (" + hname + ")"); }
                var ns = int.Parse(cfg["NightStartHour"], inv); var ne = int.Parse(cfg["NightEndHour"], inv);
                if (when.Hour >= ns || when.Hour < ne)
                { hit.Add("NIGHT"); why.Add("posted at " + when.ToString("HH:mm", inv) + " (outside normal hours)"); }
                if (desc.Length == 0)
                { hit.Add("BLANK"); why.Add("no description"); }
                else
                {
                    var low = desc.ToLowerInvariant();
                    var word = Keywords.FirstOrDefault(k => low.Contains(k));
                    if (word != null) { hit.Add("KEYWORD"); why.Add("description contains '" + word + "'"); }
                }
                var unit = decimal.Parse(cfg["RoundUnit"], inv); var rmin = decimal.Parse(cfg["RoundMinimum"], inv);
                if (amount >= rmin && amount % unit == 0)
                { hit.Add("ROUND"); why.Add("round amount"); }
                var limit = decimal.Parse(cfg["ApprovalLimit"], inv);
                if (amount < limit && amount >= 0.95m * limit)
                { hit.Add("BELOW_LIMIT"); why.Add("just below the approval limit (" + (amount / limit * 100m).ToString("0.#", inv) + "% of the limit)"); }
                if (hit.Count == 0) continue;

                var fx = Calc.D(Calc.Company(companies, co)["FxToGroup"]);
                var usd = Calc.S((double)amount * fx);
                var shown = desc.Length == 0 ? "(blank)" : redactor.Redact(desc.Length > 120 ? desc.Substring(0, 120) : desc);
                flags.Rows.Add(j["OrgId"], co, j["JournalId"], string.Join(";", hit),
                               "[" + string.Join(", ", hit) + "] " + string.Join("; ", why),
                               j["Amount"], j["Currency"], usd,
                               "manual entry by " + j["PostedBy"] + "; description: " + shown);
            }

            var summary = "JvTested=" + tested + "; JvFlagged=" + flags.Rows.Count;
            if (truth != null)
            {
                var expected = truth.Where(t => t["ExpectedFlags"].Length > 0).ToDictionary(t => t["JournalId"], t => t["ExpectedFlags"]);
                var actual = flags.AsEnumerable().ToDictionary(r => r["JournalId"].ToString(), r => string.Join(";", r["Flags"].ToString().Split(';').OrderBy(x => x, StringComparer.Ordinal)));
                var exact = expected.Count(e => actual.TryGetValue(e.Key, out var a) && a == e.Value);
                summary += "; JvExpected=" + expected.Count + "; JvExactMatches=" + exact + "; JvFalseFlags=" + actual.Count(a => !expected.ContainsKey(a.Key));
            }
            Log("Journal-entry test: " + summary);
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
