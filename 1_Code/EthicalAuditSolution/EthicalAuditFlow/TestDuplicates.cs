using System;
using System.Data;
using System.Linq;
using UiPath.CodedWorkflows;

namespace EthicalAuditFlow
{
    public class TestDuplicates : CodedWorkflow
    {
        /// <summary>
        /// Duplicate-payment test (occurrence): same company, vendor, amount and date under different invoice numbers.
        /// The first entry stays committed; later ones are routed as suspected duplicates. Skipped in Baseline mode.
        /// </summary>
        [Workflow]
        public int Execute(DataTable results, DataTable ledger, bool ethical)
        {
            if (!ethical)
            {
                Log("Duplicate test not performed (Baseline)", LogLevel.Warn);
                return 0;
            }
            var byLedger = results.AsEnumerable().ToDictionary(r => r["LedgerId"].ToString());
            var found = 0;
            var groups = ledger.AsEnumerable().Where(r => r["IsIntercompany"].ToString() == "false")
                .GroupBy(r => r["CompanyId"] + "|" + r["VendorId"] + "|" + r["Amount"] + "|" + r["PostingDate"])
                .Where(g => g.Count() > 1);
            foreach (var g in groups)
            {
                var ordered = g.OrderBy(r => r["LedgerId"].ToString(), StringComparer.Ordinal).ToList();
                foreach (var dup in ordered.Skip(1))
                {
                    var row = byLedger[dup["LedgerId"].ToString()];
                    if (row["Decision"].ToString() != "Commit") continue;
                    row["Outcome"] = "DUPLICATE_SUSPECT";
                    row["Decision"] = "RouteToAuditor";
                    row["Reason"] = "same vendor, amount and date as " + ordered[0]["TxnId"] + " (possible duplicate payment)";
                    row["VarianceAmountUSD"] = row["AmountUSD"];
                    found++;
                }
            }
            Log("Duplicate-payment test: " + found + " suspected duplicates");
            return found;
        }
    }
}
