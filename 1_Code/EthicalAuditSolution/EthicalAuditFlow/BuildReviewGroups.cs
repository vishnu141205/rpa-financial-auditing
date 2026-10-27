using System;
using System.Collections.Generic;
using System.Data;
using System.Globalization;
using System.Linq;
using System.Text.RegularExpressions;
using UiPath.CodedWorkflows;

namespace EthicalAuditFlow
{
    public class BuildReviewGroups : CodedWorkflow
    {
        private static readonly string[] TypeOrder =
        {
            "ROUTE_VARIANCE", "ROUTE_UNLINKED_VENDOR", "ROUTE_LOW_CONFIDENCE", "UNMATCHED_NO_DOC",
            "DUPLICATE_SUSPECT", "ORPHAN_DOCUMENT", "IC_MISMATCH", "JV_RISK", "REV_CUTOFF", "REV_CREDIT"
        };

        private static readonly Dictionary<string, string> TypeName = new Dictionary<string, string>
        {
            { "ROUTE_VARIANCE", "amount differences" }, { "ROUTE_UNLINKED_VENDOR", "unlisted vendors" },
            { "ROUTE_LOW_CONFIDENCE", "low-confidence extractions" }, { "UNMATCHED_NO_DOC", "missing invoices" },
            { "DUPLICATE_SUSPECT", "suspected duplicate payments" }, { "ORPHAN_DOCUMENT", "unrecorded invoices" },
            { "IC_MISMATCH", "intercompany mismatches" }, { "JV_RISK", "risky journal entries" }, { "REV_CUTOFF", "revenue cut-off exceptions" }, { "REV_CREDIT", "credit note exceptions" }
        };

        private static readonly Dictionary<string, string> Question = new Dictionary<string, string>
        {
            { "ROUTE_VARIANCE", "Is each difference explained (rounding, credit note, freight) and acceptable? Approve if resolved, Reject to send it back to the preparer." },
            { "ROUTE_UNLINKED_VENDOR", "Is each vendor a legitimate supplier that should be added to the approved list, or a spelling difference or an unapproved vendor? Approve only if every one is resolved." },
            { "ROUTE_LOW_CONFIDENCE", "Were these invoices read and verified by hand? Approve if the amounts and vendors were confirmed against the document." },
            { "UNMATCHED_NO_DOC", "Was the missing supporting invoice obtained for each entry? Approve if support exists, Reject if the entry cannot be supported." },
            { "DUPLICATE_SUSPECT", "Is each one a real duplicate payment? Approve if they are confirmed as separate, valid payments, Reject if a refund or reversal is needed." },
            { "ORPHAN_DOCUMENT", "Should each invoice be recorded as a liability? Approve if it is handled, Reject if it must be booked." },
            { "IC_MISMATCH", "Which company's amount is wrong, and has it been corrected? Approve when both sides agree." },
            { "JV_RISK", "Does each flagged journal entry have a valid business reason and documented approval? Approve if each is supported, Reject if any needs follow-up, explanation or reversal." },
            { "REV_CUTOFF", "Was each sale shipped in the period it was recorded, and is there a shipping record? Approve if the dates are supported by the shipping log, Reject if revenue must be moved to the right period." },
            { "REV_CREDIT", "Is each credit note legitimate, and was the original sale genuine? Approve if supported by a returns or pricing record, Reject if it hides a reversed or fictitious sale." },
            { "MIXED", "Review the findings listed for this company. Approve if all are resolved, Reject to return them to the preparer." },
        };

        /// <summary>
        /// Groups the findings into review groups (one Action Center form each). The grouping is a setting:
        /// "CompanyAndType" (default), "Type" (one form per problem type across the organization) or "Company".
        /// For each group it works out the numbers a reviewer needs for that kind of problem and a readable item list.
        /// </summary>
        [Workflow]
        public (DataTable groups, int count) Execute(DataTable findings, DataTable results, DataTable companies, string grouping)
        {
            var mode = (grouping ?? "").Trim();
            var byCompany = mode.Equals("Company", StringComparison.OrdinalIgnoreCase);
            var byType = mode.Equals("Type", StringComparison.OrdinalIgnoreCase);
            var groups = Calc.Table("GroupKey", "CompanyId", "Outcome", "Title", "Count", "Detail1", "Detail2", "Detail3", "Items", "Question");
            var pct = results.AsEnumerable().ToDictionary(r => r["LedgerId"].ToString(), r => r["VariancePct"].ToString());

            string CompanyKey(DataRow f) => byType ? "ALL" : f["CompanyId"].ToString();
            string TypeKey(DataRow f) => byCompany ? "MIXED" : f["Outcome"].ToString();

            var ordered = findings.AsEnumerable()
                .GroupBy(f => (CompanyKey(f), TypeKey(f)))
                .OrderBy(g => g.Key.Item1, StringComparer.Ordinal)
                .ThenBy(g => Array.IndexOf(TypeOrder, g.Key.Item2) < 0 ? 99 : Array.IndexOf(TypeOrder, g.Key.Item2));

            foreach (var g in ordered)
            {
                var rows = g.ToList();
                var co = g.Key.Item1; var oc = g.Key.Item2;
                double Exposure() => rows.Sum(r => Calc.D(r["ExposureUSD"]));
                double Amount() => rows.Sum(r => Calc.D(r["AmountUSD"]));
                string Money(double v) => "$" + v.ToString("N2", CultureInfo.InvariantCulture);
                string Range(string col)
                {
                    var vals = rows.Select(r => r["CompanyId"].ToString()).Distinct()
                        .Select(id => Calc.D(Calc.Company(companies, id)[col])).ToList();
                    return vals.Min() == vals.Max() ? vals.Min().ToString("0.##", CultureInfo.InvariantCulture)
                        : vals.Min().ToString("0.##", CultureInfo.InvariantCulture) + " to " + vals.Max().ToString("0.##", CultureInfo.InvariantCulture);
                }

                string d1, d2, d3;
                switch (oc)
                {
                    case "ROUTE_VARIANCE":
                        d1 = rows.Select(r => pct.TryGetValue(r["Reference"].ToString(), out var p) ? Calc.D(p) : 0).DefaultIfEmpty(0).Max().ToString("0.##", CultureInfo.InvariantCulture) + " %";
                        d2 = Range("TolerancePct") + " %"; d3 = Money(Exposure()); break;
                    case "ROUTE_UNLINKED_VENDOR":
                        d1 = rows.Count.ToString(); d2 = Money(Amount()); d3 = "The vendor on the invoice is not in the approved vendor list"; break;
                    case "ROUTE_LOW_CONFIDENCE":
                        var conf = rows.Select(r => Regex.Match(r["Reason"].ToString(), @"confidence ([0-9.]+)"))
                                       .Where(m => m.Success).Select(m => Calc.D(m.Groups[1].Value)).DefaultIfEmpty(0).Min();
                        d1 = conf.ToString("0.00", CultureInfo.InvariantCulture); d2 = Range("MinConfidence"); d3 = Money(Amount()); break;
                    case "UNMATCHED_NO_DOC":
                        d1 = rows.Count.ToString(); d2 = Money(Amount()); d3 = "No supporting invoice is on file for these entries"; break;
                    case "DUPLICATE_SUSPECT":
                        var orig = rows.Select(r => Regex.Match(r["Reason"].ToString(), @"as (\S+) \(")).Where(m => m.Success)
                                       .Select(m => m.Groups[1].Value).Distinct().Take(5);
                        d1 = rows.Count.ToString(); d2 = Money(Amount()); d3 = string.Join(", ", orig); break;
                    case "ORPHAN_DOCUMENT":
                        d1 = rows.Count.ToString(); d2 = Money(Amount()); d3 = "The invoice exists but there is no ledger entry for it"; break;
                    case "REV_CUTOFF":
                    case "REV_CREDIT":
                        var rtally = rows.SelectMany(r => Regex.Match(r["Reason"].ToString(), @"^\[([A-Z_, ]+)\]").Groups[1].Value.Split(new[] { ", " }, StringSplitOptions.RemoveEmptyEntries))
                                         .GroupBy(x => x).OrderByDescending(g => g.Count()).Select(g => g.Key.ToLowerInvariant().Replace('_', ' ') + " " + g.Count());
                        d1 = rows.Count.ToString(); d2 = Money(Amount()); d3 = string.Join(", ", rtally); break;
                    case "JV_RISK":
                        var tally = rows.SelectMany(r => Regex.Match(r["Reason"].ToString(), @"^\[([A-Z_, ]+)\]").Groups[1].Value.Split(new[] { ", " }, StringSplitOptions.RemoveEmptyEntries))
                                        .GroupBy(x => x).OrderByDescending(g => g.Count()).Select(g => g.Key.ToLowerInvariant().Replace('_', ' ') + " " + g.Count());
                        d1 = rows.Count.ToString(); d2 = Money(Amount()); d3 = string.Join(", ", tally); break;
                    case "IC_MISMATCH":
                        d1 = rows.Count + " legs"; d2 = Money(Exposure() / 2.0);
                        d3 = Calc.D(companies.Rows[0]["IcTolerancePct"]).ToString("0.##", CultureInfo.InvariantCulture) + " %"; break;
                    default:
                        d1 = rows.Count.ToString(); d2 = rows.Count(r => r["Severity"].ToString() == "High" || r["Severity"].ToString() == "Critical").ToString();
                        d3 = Money(Exposure()); break;
                }

                var lines = rows.OrderByDescending(r => Calc.D(r["ExposureUSD"])).Take(25)
                    .Select(r => r["CompanyId"] + "  " + ((r["Outcome"].ToString() == "JV_RISK" || r["Outcome"].ToString().StartsWith("REV_")) ? r["Reference"].ToString() : r["Outcome"].ToString() == "ORPHAN_DOCUMENT"
                                    ? "no ledger entry (document " + r["Reference"] + ") / " + r["TxnId"]
                                    : r["Reference"] + " / " + r["TxnId"]) + "  |  " + r["Reason"] + "  |  $" + Calc.D(r["ExposureUSD"]).ToString("N2", CultureInfo.InvariantCulture) + "  |  " + r["Severity"]);
                var items = string.Join("\n", lines) + (rows.Count > 25 ? "\n... and " + (rows.Count - 25) + " more in the findings register" : "");
                var label = TypeName.TryGetValue(oc, out var tn) ? tn : "findings";
                var title = "Review " + label + " - " + (co == "ALL" ? "all companies" : co) + " (" + rows.Count + ")";
                groups.Rows.Add(co + "|" + oc, co, oc, title, rows.Count.ToString(), d1, d2, d3, items,
                                Question.TryGetValue(oc, out var q) ? q : Question["MIXED"]);
            }
            Log("Review groups (" + (byType ? "Type" : byCompany ? "Company" : "CompanyAndType") + "): " + groups.Rows.Count + " forms for " + findings.Rows.Count + " findings");
            return (groups, groups.Rows.Count);
        }
    }
}
