using System;
using System.Data;
using System.Globalization;
using System.Linq;
using UiPath.CodedWorkflows;

namespace EthicalAuditFinalize
{
    public class BuildPostReviewReport : CodedWorkflow
    {
        /// <summary>
        /// Recalculates the audit summary after the reviewers have decided. The original report is not touched.
        /// Approved findings are treated as resolved and drop out of the outstanding amounts. Rejected findings and
        /// findings nobody has decided yet stay outstanding. The conclusion is then re-derived with the same rule.
        /// </summary>
        [Workflow]
        public (DataTable report, string conclusion) Execute(DataTable findings, DataTable planning, DataTable originalReport)
        {
            var rep = new DataTable();
            foreach (var c in new[] { "Scope", "InherentRisk", "Findings", "Approved", "Rejected", "StillOpen",
                                      "FactualBeforeUSD", "UnresolvedBeforeUSD", "OutstandingFactualUSD", "OutstandingUnresolvedUSD",
                                      "OverallMaterialityUSD", "PerformanceMaterialityUSD", "ConclusionBefore", "ConclusionAfterReview" })
                rep.Columns.Add(c, typeof(string));

            string Conclude(double factual, double unresolved, double overall, double perf, int outstanding) =>
                factual >= overall ? "Material misstatement indicated - escalate to engagement lead"
                : (factual >= perf || unresolved >= overall) ? "Further audit procedures required before a conclusion"
                : outstanding > 0 ? "Outstanding exceptions below performance materiality - resolve and document"
                : "All exceptions reviewed and approved - no outstanding exceptions";

            // The report file's first column is read by position (a file's first header can carry a byte-order mark).
            DataRow Before(string scope) => originalReport.AsEnumerable().FirstOrDefault(r => r[0].ToString() == scope);
            double Num(object o) => double.Parse(o.ToString(), CultureInfo.InvariantCulture);
            string S(double v) => Math.Round(v, 2).ToString("0.00", CultureInfo.InvariantCulture);

            int tFind = 0, tApp = 0, tRej = 0, tOpen = 0;
            double tFactB = 0, tUnresB = 0, tFactO = 0, tUnresO = 0, tOverall = 0, tPerf = 0;
            foreach (DataRow p in planning.Rows)
            {
                var id = p["CompanyId"].ToString();
                var fs = findings.Select("CompanyId = '" + id + "'");
                bool Approved(DataRow f) => f["Status"].ToString().StartsWith("Reviewed", StringComparison.Ordinal);
                bool Rejected(DataRow f) => f["Status"].ToString().StartsWith("Rejected", StringComparison.Ordinal);
                var app = fs.Count(Approved); var rej = fs.Count(Rejected); var open = fs.Length - app - rej;
                var outstanding = fs.Where(f => !Approved(f)).ToList();
                var factO = outstanding.Where(f => f["ExposureType"].ToString() == "Factual").Sum(f => Num(f["ExposureUSD"]));
                var unresO = outstanding.Where(f => f["ExposureType"].ToString() == "Unresolved").Sum(f => Num(f["ExposureUSD"]));
                var before = Before(id);
                var factB = before != null ? Num(before["FactualMisstatementUSD"]) : 0;
                var unresB = before != null ? Num(before["UnresolvedExposureUSD"]) : 0;
                var overall = Num(p["OverallMateriality"]); var perf = Num(p["PerformanceMateriality"]);
                rep.Rows.Add(id, p["InherentRisk"], fs.Length.ToString(), app.ToString(), rej.ToString(), open.ToString(),
                             S(factB), S(unresB), S(factO), S(unresO), S(overall), S(perf),
                             before != null ? before["PreliminaryConclusion"].ToString() : "",
                             Conclude(factO, unresO, overall, perf, rej + open));
                tFind += fs.Length; tApp += app; tRej += rej; tOpen += open;
                tFactB += factB; tUnresB += unresB; tFactO += factO; tUnresO += unresO; tOverall += overall; tPerf += perf;
            }
            var group = Before("GROUP");
            var conclusion = Conclude(tFactO, tUnresO, tOverall, tPerf, tRej + tOpen);
            rep.Rows.Add("GROUP", "", tFind.ToString(), tApp.ToString(), tRej.ToString(), tOpen.ToString(),
                         S(tFactB), S(tUnresB), S(tFactO), S(tUnresO), S(tOverall), S(tPerf),
                         group != null ? group["PreliminaryConclusion"].ToString() : "", conclusion);
            Log("After review: " + tApp + " approved, " + tRej + " rejected, " + tOpen + " still open. Conclusion: " + conclusion);
            return (rep, conclusion);
        }
    }
}
