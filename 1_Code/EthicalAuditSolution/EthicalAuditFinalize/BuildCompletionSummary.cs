using System;
using System.Collections.Generic;
using System.Data;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Net;
using System.Security.Cryptography;
using System.Text;
using UiPath.CodedWorkflows;

namespace EthicalAuditFinalize
{
    public class BuildCompletionSummary : CodedWorkflow
    {
        private static readonly Dictionary<string, string> TypeName = new Dictionary<string, string>
        {
            { "ROUTE_VARIANCE", "Amount differences" }, { "ROUTE_UNLINKED_VENDOR", "Unlisted vendors" },
            { "ROUTE_LOW_CONFIDENCE", "Low-confidence extractions" }, { "UNMATCHED_NO_DOC", "Missing invoices" },
            { "DUPLICATE_SUSPECT", "Suspected duplicate payments" }, { "ORPHAN_DOCUMENT", "Unrecorded invoices" },
            { "IC_MISMATCH", "Intercompany mismatches" }, { "JV_RISK", "Risky journal entries" }, { "REV_CUTOFF", "Revenue cut-off exceptions" }, { "REV_CREDIT", "Credit note exceptions" }
        };

        /// <summary>
        /// Writes the one-page audit completion summary (HTML): scope, tests, findings by status, conclusions before and
        /// after review, who reviewed, the integrity check of the audit trail, and a signature block.
        /// </summary>
        [Workflow]
        public (string status, bool chainOk, string orgHash) Execute(string runFolder, string outputPath, DataTable findings,
            DataTable planning, DataTable reportBefore, DataTable reportAfter, DataTable outcomes, DataTable chain)
        {
            string H(object o) => WebUtility.HtmlEncode(o == null ? "" : o.ToString());
            bool Approved(DataRow f) => f["Status"].ToString().StartsWith("Reviewed", StringComparison.Ordinal);
            bool Rejected(DataRow f) => f["Status"].ToString().StartsWith("Rejected", StringComparison.Ordinal);

            // ---- integrity: re-verify every link of every company's hash chain (columns read by position) ----
            var heads = new Dictionary<string, string>();
            var chainOk = true; var checkedEntries = 0;
            var zeros = new string('0', 64);
            string lastCo = null, expectedPrev = zeros;
            foreach (DataRow r in chain.Rows)
            {
                var co = r[0].ToString();
                if (co != lastCo) { expectedPrev = zeros; lastCo = co; }
                var ok = r[3].ToString() == expectedPrev
                         && r[2].ToString() == Sha(r[5].ToString())
                         && r[4].ToString() == Sha(r[1] + "|" + r[3] + "|" + r[2]);
                chainOk = chainOk && ok; checkedEntries++;
                expectedPrev = r[4].ToString(); heads[co] = expectedPrev;
            }
            var anchorInput = string.Concat(planning.AsEnumerable()
                .Select(p => p["CompanyId"].ToString())
                .Select(id => id + ":" + (heads.ContainsKey(id) ? heads[id] : "") + ";"));
            var orgHash = Sha(anchorInput);

            var total = findings.Rows.Count;
            var approved = findings.AsEnumerable().Count(Approved);
            var rejected = findings.AsEnumerable().Count(Rejected);
            var open = total - approved - rejected;
            var complete = total > 0 && approved == total;
            var status = complete ? "COMPLETE - all exceptions reviewed and approved"
                                  : "NOT COMPLETE - " + (total - approved) + " of " + total + " findings outstanding";
            var groupBefore = reportBefore.AsEnumerable().FirstOrDefault(r => r[0].ToString() == "GROUP");
            var orgId = planning.Rows.Count > 0 ? planning.Rows[0][0].ToString() : "";

            var sb = new StringBuilder();
            sb.Append("<!doctype html><html lang='en'><head><meta charset='utf-8'><title>Audit completion summary</title>");
            sb.Append("<style>body{font-family:Segoe UI,Arial,sans-serif;max-width:900px;margin:24px auto;padding:0 16px;color:#1a1a1a}");
            sb.Append("h1{font-size:22px;margin:0 0 4px}h2{font-size:16px;margin:24px 0 8px;border-bottom:1px solid #ccc;padding-bottom:4px}");
            sb.Append("table{border-collapse:collapse;width:100%;font-size:13px}th,td{border:1px solid #ccc;padding:6px 8px;text-align:left;vertical-align:top}");
            sb.Append("th{background:#f2f2f2}.ok{background:#e6f4ea;border:1px solid #2e7d32}.no{background:#fdecea;border:1px solid #c62828}");
            sb.Append(".banner{padding:12px 14px;font-weight:600;font-size:15px;margin:12px 0}.muted{color:#555;font-size:12px}");
            sb.Append(".sig td{height:42px}</style></head><body>");
            sb.Append("<h1>Audit completion summary</h1>");
            sb.Append("<div class='muted'>Organization " + H(orgId) + " &middot; run " + H(runFolder) + " &middot; generated " +
                      DateTime.UtcNow.ToString("yyyy-MM-dd HH:mm", CultureInfo.InvariantCulture) + " UTC</div>");
            sb.Append("<div class='banner " + (complete ? "ok" : "no") + "'>" + H(status) + "</div>");

            sb.Append("<h2>1. Scope</h2><table><tr><th>Payments tested</th><th>Approved automatically</th><th>Exceptions raised</th><th>Coverage</th></tr><tr>");
            sb.Append("<td>" + H(groupBefore?["ItemsTested"]) + "</td><td>" + H(groupBefore?["Committed"]) + "</td><td>" + H(groupBefore?["Exceptions"]) +
                      "</td><td>" + H(groupBefore?["CoveragePct"]) + "% of the ledger (all entries, not a sample)</td></tr></table>");
            sb.Append("<p class='muted'>Tests performed: ledger-to-invoice reconciliation (existence, vendor validity, extraction confidence, amount accuracy), " +
                      "duplicate-payment test, unrecorded-invoice (completeness) test, intercompany agreement, revenue cut-off and credit-note testing, and journal-entry testing of manual entries (weekend, holiday and night postings, risky wording, round and just-below-limit amounts).</p>");

            sb.Append("<h2>2. Conclusion by company</h2><table><tr><th>Scope</th><th>Findings</th><th>Approved</th><th>Rejected</th><th>Open</th>" +
                      "<th>Conclusion at test time</th><th>Conclusion after review</th></tr>");
            foreach (DataRow r in reportAfter.Rows)
                sb.Append("<tr><td>" + H(r["Scope"]) + "</td><td>" + H(r["Findings"]) + "</td><td>" + H(r["Approved"]) + "</td><td>" + H(r["Rejected"]) +
                          "</td><td>" + H(r["StillOpen"]) + "</td><td>" + H(r["ConclusionBefore"]) + "</td><td><b>" + H(r["ConclusionAfterReview"]) + "</b></td></tr>");
            sb.Append("</table>");

            sb.Append("<h2>3. Findings by problem type</h2><table><tr><th>Problem type</th><th>Findings</th><th>Approved</th><th>Rejected</th><th>Open</th></tr>");
            foreach (var g in findings.AsEnumerable().GroupBy(f => f["Outcome"].ToString()).OrderBy(g => g.Key, StringComparer.Ordinal))
            {
                var a = g.Count(Approved); var rj = g.Count(Rejected);
                sb.Append("<tr><td>" + H(TypeName.TryGetValue(g.Key, out var n) ? n : g.Key) + "</td><td>" + g.Count() + "</td><td>" + a + "</td><td>" + rj +
                          "</td><td>" + (g.Count() - a - rj) + "</td></tr>");
            }
            sb.Append("<tr><td><b>Total</b></td><td><b>" + total + "</b></td><td><b>" + approved + "</b></td><td><b>" + rejected + "</b></td><td><b>" + open + "</b></td></tr></table>");

            sb.Append("<h2>4. Who reviewed</h2><table><tr><th>Reviewer</th><th>Forms decided</th><th>Approve</th><th>Reject</th><th>First decision</th><th>Last decision</th></tr>");
            var decided = outcomes.AsEnumerable().Where(r => r["Status"].ToString() == "Completed").ToList();
            foreach (var g in decided.GroupBy(r => r["Reviewer"].ToString()).OrderBy(g => g.Key, StringComparer.Ordinal))
            {
                var times = g.Select(r => r["CompletedAt"].ToString()).OrderBy(t => t, StringComparer.Ordinal).ToList();
                sb.Append("<tr><td>" + H(g.Key) + "</td><td>" + g.Count() + "</td><td>" + g.Count(r => !r["Action"].ToString().StartsWith("Reject")) +
                          "</td><td>" + g.Count(r => r["Action"].ToString().StartsWith("Reject")) + "</td><td>" + H(times.First()) + "</td><td>" + H(times.Last()) + "</td></tr>");
            }
            if (decided.Count == 0) sb.Append("<tr><td colspan='6'>No review form has been decided yet.</td></tr>");
            sb.Append("</table>");

            sb.Append("<h2>5. Integrity of the audit trail</h2><table>");
            sb.Append("<tr><th>Hash chain re-verified</th><td>" + (chainOk ? "Yes - " : "NO - ") + checkedEntries + " entries checked</td></tr>");
            sb.Append("<tr><th>Organization-level hash</th><td style='font-family:Consolas,monospace;word-break:break-all'>" + H(orgHash) + "</td></tr></table>");
            sb.Append("<p class='muted'>The organization hash combines the end of every company's chain. Any later edit to a recorded decision changes it.</p>");

            sb.Append("<h2>6. Important notes</h2><ul class='muted'>");
            sb.Append("<li>This summary covers the payments tested. It is not an audit opinion on the financial statements.</li>");
            sb.Append("<li>An approval is the reviewer's confirmation that the exception is resolved. The system does not itself verify the evidence.</li>");
            sb.Append("<li>Amounts at risk are in USD. Approved findings are treated as resolved. Rejected and undecided findings remain outstanding.</li></ul>");

            sb.Append("<h2>7. Sign-off</h2><table class='sig'><tr><th>Role</th><th>Name</th><th>Signature</th><th>Date</th></tr>");
            sb.Append("<tr><td>Prepared by</td><td>RPA Bot (EthicalAudit)</td><td>automated</td><td>" + DateTime.UtcNow.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture) + "</td></tr>");
            sb.Append("<tr><td>Reviewed by</td><td>" + H(string.Join(", ", decided.Select(r => r["Reviewer"].ToString()).Distinct())) + "</td><td></td><td></td></tr>");
            sb.Append("<tr><td>Engagement lead</td><td></td><td></td><td></td></tr></table></body></html>");

            File.WriteAllText(outputPath, sb.ToString(), new UTF8Encoding(false));
            Log("Completion summary written: " + status + "; hash chain " + (chainOk ? "verified" : "FAILED"));
            return (status, chainOk, orgHash);
        }

        private static string Sha(string s)
        {
            using (var sha = SHA256.Create())
            {
                var h = sha.ComputeHash(Encoding.UTF8.GetBytes(s));
                var sb = new StringBuilder();
                foreach (var b in h) sb.Append(b.ToString("x2"));
                return sb.ToString();
            }
        }
    }
}
