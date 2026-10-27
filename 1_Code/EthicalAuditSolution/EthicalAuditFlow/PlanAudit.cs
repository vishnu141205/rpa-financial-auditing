using System;
using System.Data;
using System.Linq;
using UiPath.CodedWorkflows;

namespace EthicalAuditFlow
{
    public class PlanAudit : CodedWorkflow
    {
        /// <summary>
        /// Audit planning per company: population, overall materiality (% of population), performance materiality
        /// (lower for higher inherent risk) and clearly-trivial threshold. Testing approach is 100% of the population.
        /// </summary>
        [Workflow]
        public DataTable Execute(DataTable companies, DataTable ledger)
        {
            var plan = Calc.Table("OrgId", "CompanyId", "Currency", "InherentRisk", "LedgerItems", "PopulationValueUSD",
                                  "OverallMateriality", "PerformanceMateriality", "ClearlyTrivial", "MaterialityBasis", "Approach");
            foreach (DataRow c in companies.Rows)
            {
                var id = c["CompanyId"].ToString();
                var fx = Calc.D(c["FxToGroup"]);
                var rows = ledger.Select("CompanyId = '" + id + "'");
                var population = rows.Sum(r => Math.Abs(Calc.D(r["Amount"]))) * fx;
                var overall = population * Calc.D(c["MaterialityPct"]) / 100.0;
                var risk = c["InherentRisk"].ToString();
                var pmFactor = risk == "High" ? 0.50 : risk == "Medium" ? 0.65 : 0.75;
                plan.Rows.Add(c["OrgId"], id, c["Currency"], risk, rows.Length.ToString(), Calc.S(population),
                              Calc.S(overall), Calc.S(overall * pmFactor), Calc.S(overall * 0.05),
                              Calc.S(Calc.D(c["MaterialityPct"]), 1) + "% of tested disbursements (USD); PM " + (pmFactor * 100) + "% of overall for " + risk + " risk",
                              "100% population testing (automated); exceptions to human reviewer");
            }
            Log("Audit plan built for " + plan.Rows.Count + " companies (materiality and risk-adjusted performance materiality)");
            return plan;
        }
    }
}
