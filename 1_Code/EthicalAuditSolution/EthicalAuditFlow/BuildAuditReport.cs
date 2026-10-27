using System;
using System.Data;
using System.Linq;
using UiPath.CodedWorkflows;

namespace EthicalAuditFlow
{
    public class BuildAuditReport : CodedWorkflow
    {
        /// <summary>
        /// Summary of audit differences: per company and for the group - items tested, coverage, exceptions by severity,
        /// potential misstatement against materiality and a preliminary conclusion for the engagement lead.
        /// </summary>
        [Workflow]
        public (DataTable report, string conclusion) Execute(DataTable planning, DataTable results, DataTable findings)
        {
            var rep = Calc.Table("Scope", "InherentRisk", "ItemsTested", "CoveragePct", "Committed", "Exceptions", "Critical", "High",
                                 "Medium", "Low", "FactualMisstatementUSD", "UnresolvedExposureUSD", "OverallMaterialityUSD", "PerformanceMaterialityUSD",
                                 "PreliminaryConclusion");

            // Factual misstatement (quantified differences) is compared with materiality; unresolved exposure
            // (missing evidence) cannot support a conclusion until the reviewer resolves it.
            string Conclude(double factual, double unresolved, double overall, double perf, int ex) =>
                factual >= overall ? "Material misstatement indicated - escalate to engagement lead"
                : (factual >= perf || unresolved >= overall) ? "Further audit procedures required before a conclusion"
                : ex > 0 ? "Exceptions below performance materiality - resolve and document"
                : "No exceptions noted";

            int tCrit = 0, tHigh = 0, tEx = 0, tItems = 0, tCommit = 0, tLedger = 0;
            double tFact = 0, tUnres = 0, tOverall = 0, tPerf = 0;
            foreach (DataRow p in planning.Rows)
            {
                var id = p["CompanyId"].ToString();
                var rs = results.Select("CompanyId = '" + id + "'");
                var fs = findings.Select("CompanyId = '" + id + "'");
                var fact = fs.Where(x => x["ExposureType"].ToString() == "Factual").Sum(x => Calc.D(x["ExposureUSD"]));
                var unres = fs.Where(x => x["ExposureType"].ToString() == "Unresolved").Sum(x => Calc.D(x["ExposureUSD"]));
                var items = rs.Length;
                var ledgerItems = int.Parse(p["LedgerItems"].ToString());
                var commit = rs.Count(x => x["Decision"].ToString() == "Commit");
                var crit = fs.Count(x => x["Severity"].ToString() == "Critical");
                var high = fs.Count(x => x["Severity"].ToString() == "High");
                rep.Rows.Add(id, p["InherentRisk"], items.ToString(), Calc.S(100.0 * items / ledgerItems), commit.ToString(),
                             fs.Length.ToString(), crit.ToString(), high.ToString(),
                             fs.Count(x => x["Severity"].ToString() == "Medium").ToString(),
                             fs.Count(x => x["Severity"].ToString() == "Low").ToString(),
                             Calc.S(fact), Calc.S(unres), p["OverallMateriality"], p["PerformanceMateriality"],
                             Conclude(fact, unres, Calc.D(p["OverallMateriality"]), Calc.D(p["PerformanceMateriality"]), fs.Length));
                tCrit += crit; tHigh += high; tEx += fs.Length; tItems += items; tCommit += commit; tLedger += ledgerItems;
                tFact += fact; tUnres += unres; tOverall += Calc.D(p["OverallMateriality"]); tPerf += Calc.D(p["PerformanceMateriality"]);
            }
            var conclusion = Conclude(tFact, tUnres, tOverall, tPerf, tEx);
            rep.Rows.Add("GROUP", "", tItems.ToString(), Calc.S(100.0 * tItems / tLedger), tCommit.ToString(), tEx.ToString(),
                         tCrit.ToString(), tHigh.ToString(), findings.Select("Severity = 'Medium'").Length.ToString(),
                         findings.Select("Severity = 'Low'").Length.ToString(), Calc.S(tFact), Calc.S(tUnres), Calc.S(tOverall), Calc.S(tPerf), conclusion);
            Log("Preliminary conclusion: " + conclusion);
            return (rep, conclusion);
        }
    }
}
