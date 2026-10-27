using System;
using System.Data;
using System.Linq;
using UiPath.CodedWorkflows;

namespace EthicalAuditFlow
{
    public class ReconcileCompany : CodedWorkflow
    {
        /// <summary>
        /// Match one company's ledger entries to its extracted invoices (existence, vendor validity, extraction
        /// confidence, amount accuracy). Only this company's rows are visible to the test.
        /// Ethical = per-company tolerance + confidence bound; Baseline = exact match only.
        /// </summary>
        [Workflow]
        public DataTable Execute(DataTable results, string companyId, DataTable companies, DataTable ledger,
                                 DataTable documents, bool ethical)
        {
            var co = Calc.Company(companies, companyId);
            var fx = Calc.D(co["FxToGroup"]);
            var tol = ethical ? Calc.D(co["TolerancePct"]) : 0.0;
            var minConf = Calc.D(co["MinConfidence"]);
            var docs = documents.AsEnumerable().Where(d => d["CompanyId"].ToString() == companyId)
                                .ToLookup(d => d["TxnId"].ToString());
            var n = 0;
            foreach (var l in ledger.Select("CompanyId = '" + companyId + "' AND IsIntercompany = 'false'"))
            {
                var txn = l["TxnId"].ToString();
                var amt = Calc.D(l["Amount"]);
                var doc = docs[txn].FirstOrDefault();
                string outcome, reason, evidence = "";
                double variance = 0, diff = 0;
                if (doc == null)
                {
                    outcome = "UNMATCHED_NO_DOC";
                    reason = "no supporting document for ledger entry (existence)";
                }
                else
                {
                    evidence = doc["RawText"].ToString();
                    var docAmt = Calc.D(doc["Amount"]);
                    var conf = Math.Min(Math.Min(Calc.D(doc["ConfTxnId"]), Calc.D(doc["ConfAmount"])), Calc.D(doc["ConfVendor"]));
                    variance = amt == 0 ? 0 : Math.Round(Math.Abs(amt - docAmt) / Math.Abs(amt) * 100.0, 4);
                    diff = Math.Abs(amt - docAmt) * fx;
                    if (doc["VendorId"].ToString() != l["VendorId"].ToString())
                    {
                        outcome = "ROUTE_UNLINKED_VENDOR";
                        reason = "document vendor " + doc["VendorId"] + " not in vendor master for this ledger entry";
                    }
                    else if (ethical && conf < minConf)
                    {
                        outcome = "ROUTE_LOW_CONFIDENCE";
                        reason = "extraction confidence " + Calc.S(conf) + " below bound " + Calc.S(minConf);
                    }
                    else if (variance > tol)
                    {
                        outcome = "ROUTE_VARIANCE";
                        reason = "variance " + Calc.S(variance, 4) + "% exceeds tolerance " + Calc.S(tol);
                    }
                    else
                    {
                        outcome = docAmt == amt ? "AUTO_MATCH" : "AUTO_MATCH_TOLERANCE";
                        reason = "agreed to supporting document";
                    }
                }
                var commit = outcome.StartsWith("AUTO");
                var exposure = commit ? 0 : (outcome == "ROUTE_VARIANCE" ? diff : amt * fx);
                results.Rows.Add(co["OrgId"], companyId, l["LedgerId"], txn, l["VendorId"], l["Amount"], l["Currency"],
                                 Calc.S(amt * fx), outcome, commit ? "Commit" : "RouteToAuditor", reason,
                                 Calc.S(variance, 4), Calc.S(exposure), evidence);
                n++;
            }
            Log("Reconciled " + companyId + ": " + n + " ledger entries");
            return results;
        }
    }
}
