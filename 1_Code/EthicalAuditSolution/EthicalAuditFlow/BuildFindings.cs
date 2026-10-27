using System;
using System.Data;
using System.Linq;
using UiPath.CodedWorkflows;

namespace EthicalAuditFlow
{
    public class BuildFindings : CodedWorkflow
    {
        /// <summary>
        /// Findings register (the exception queue for the human reviewer). Every routed item and orphan invoice gets an
        /// assertion, control reference, working-paper reference and a severity rated against company materiality.
        /// The bot is the preparer; reviewer sign-off is left open (segregation of duties).
        /// </summary>
        [Workflow]
        public DataTable Execute(DataTable results, DataTable orphans, DataTable planning, DataTable journalFlags, DataTable revenueFlags)
        {
            var f = Calc.Table("FindingId", "WorkingPaperRef", "OrgId", "CompanyId", "Reference", "TxnId", "TestPerformed",
                               "Assertion", "ControlRef", "Outcome", "AmountUSD", "ExposureUSD", "ExposureType", "Severity",
                               "Status", "Preparer", "Reviewer", "ReviewerSignOff", "ReviewerComment", "Reason", "Evidence");
            var seq = 0;

            string Sev(string company, double exposure)
            {
                var p = Calc.Plan(planning, company);
                var pm = Calc.D(p["PerformanceMateriality"]);
                if (exposure >= pm) return "Critical";
                if (exposure >= 0.5 * pm) return "High";
                if (exposure >= Calc.D(p["ClearlyTrivial"])) return "Medium";
                return "Low";
            }

            void Add(string org, string company, string reference, string txn, string outcome, string amountUsd,
                     string exposureUsd, string reason, string evidence)
            {
                var m = Map(outcome);
                // Factual = a quantified difference found; Unresolved = evidence still missing, exposure not yet a misstatement.
                var type = (outcome == "ROUTE_VARIANCE" || outcome == "IC_MISMATCH") ? "Factual" : "Unresolved";
                seq++;
                f.Rows.Add("F-" + seq.ToString("0000"), "WP-" + company.Substring(company.Length - 2) + "-" + m.wp, org, company,
                           reference, txn, m.test, m.assertion, m.control, outcome, amountUsd, exposureUsd, type,
                           Sev(company, Calc.D(exposureUsd)), "Open - pending reviewer sign-off", "RPA Bot (EthicalAudit)",
                           "", "", "", reason, evidence);
            }

            foreach (var r in results.AsEnumerable().Where(x => x["Decision"].ToString() == "RouteToAuditor")
                                     .OrderBy(x => x["CompanyId"].ToString()).ThenBy(x => x["LedgerId"].ToString()))
                Add(r["OrgId"].ToString(), r["CompanyId"].ToString(), r["LedgerId"].ToString(), r["TxnId"].ToString(),
                    r["Outcome"].ToString(), r["AmountUSD"].ToString(), r["VarianceAmountUSD"].ToString(),
                    r["Reason"].ToString(), r["Evidence"].ToString());
            foreach (DataRow o in orphans.Rows)
                Add(o["OrgId"].ToString(), o["CompanyId"].ToString(), o["DocId"].ToString(), o["TxnId"].ToString(),
                    "ORPHAN_DOCUMENT", o["AmountUSD"].ToString(), o["AmountUSD"].ToString(),
                    "invoice has no ledger entry (possible unrecorded liability)", o["Evidence"].ToString());
            foreach (DataRow j in journalFlags.Rows)
                Add(j["OrgId"].ToString(), j["CompanyId"].ToString(), j["JournalId"].ToString(), j["JournalId"].ToString(),
                    "JV_RISK", j["AmountUSD"].ToString(), j["AmountUSD"].ToString(), j["Reason"].ToString(), j["Evidence"].ToString());
            foreach (DataRow v in revenueFlags.Rows)
                Add(v["OrgId"].ToString(), v["CompanyId"].ToString(), v["DocumentNo"].ToString(), v["DocumentNo"].ToString(),
                    v["Outcome"].ToString(), v["AmountUSD"].ToString(), v["AmountUSD"].ToString(), v["Reason"].ToString(), v["Evidence"].ToString());
            Log("Findings register: " + f.Rows.Count + " findings raised for reviewer sign-off");
            return f;
        }

        private static (string test, string assertion, string control, string wp) Map(string outcome)
        {
            switch (outcome)
            {
                case "ROUTE_VARIANCE": return ("Invoice-to-ledger amount match", "Accuracy", "CTRL-REC-02", "REC");
                case "ROUTE_UNLINKED_VENDOR": return ("Vendor master validation", "Validity / authorisation", "CTRL-VND-01", "VND");
                case "ROUTE_LOW_CONFIDENCE": return ("Extraction reliability check", "Accuracy", "CTRL-DOC-01", "DOC");
                case "UNMATCHED_NO_DOC": return ("Supporting document inspection", "Existence / occurrence", "CTRL-DOC-02", "EXS");
                case "DUPLICATE_SUSPECT": return ("Duplicate payment test", "Occurrence", "CTRL-PAY-01", "DUP");
                case "ORPHAN_DOCUMENT": return ("Unrecorded liability (completeness) test", "Completeness", "CTRL-CMP-01", "CMP");
                case "IC_MISMATCH": return ("Intercompany agreement and elimination", "Accuracy / completeness", "CTRL-IC-01", "ICO");
                case "REV_CUTOFF": return ("Revenue cut-off test", "Cut-off", "CTRL-REV-01", "REV");
                case "REV_CREDIT": return ("Credit note and refund test", "Occurrence", "CTRL-REV-02", "CRN");
                case "JV_RISK": return ("Journal-entry testing (management override)", "Occurrence / authorisation", "CTRL-JE-01", "JET");
                default: return ("Other", "n/a", "CTRL-GEN-00", "GEN");
            }
        }
    }
}
