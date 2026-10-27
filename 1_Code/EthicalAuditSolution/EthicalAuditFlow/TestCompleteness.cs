using System;
using System.Data;
using System.Linq;
using UiPath.CodedWorkflows;

namespace EthicalAuditFlow
{
    public class TestCompleteness : CodedWorkflow
    {
        /// <summary>
        /// Completeness test: invoices that exist in the document set but have no ledger entry (unrecorded liability).
        /// Skipped in Baseline mode.
        /// </summary>
        [Workflow]
        public DataTable Execute(DataTable ledger, DataTable documents, DataTable companies, bool ethical)
        {
            var orphans = Calc.Table("OrgId", "CompanyId", "DocId", "TxnId", "VendorId", "Amount", "Currency", "AmountUSD", "Evidence");
            if (!ethical)
            {
                Log("Completeness test not performed (Baseline)", LogLevel.Warn);
                return orphans;
            }
            var known = ledger.AsEnumerable().Select(r => r["CompanyId"] + "|" + r["TxnId"]).ToHashSet();
            foreach (DataRow d in documents.Rows)
            {
                if (known.Contains(d["CompanyId"] + "|" + d["TxnId"])) continue;
                var co = Calc.Company(companies, d["CompanyId"].ToString());
                orphans.Rows.Add(d["OrgId"], d["CompanyId"], d["DocId"], d["TxnId"], d["VendorId"], d["Amount"], d["Currency"],
                                 Calc.S(Calc.D(d["Amount"]) * Calc.D(co["FxToGroup"])), d["RawText"]);
            }
            Log("Completeness test: " + orphans.Rows.Count + " invoices with no ledger entry");
            return orphans;
        }
    }
}
