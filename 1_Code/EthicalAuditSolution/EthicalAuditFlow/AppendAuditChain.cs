using System;
using System.Data;
using System.Linq;
using UiPath.CodedWorkflows;

namespace EthicalAuditFlow
{
    public class AppendAuditChain : CodedWorkflow
    {
        /// <summary>
        /// Audit trail: appends one company's results to an append-only SHA-256 hash chain
        /// (entry = SHA-256(seq|prevHash|payloadHash)). Payloads are the already-redacted records, so the
        /// evidence trail itself never holds sensitive data.
        /// </summary>
        [Workflow]
        public (string head, int entries) Execute(DataTable results, DataTable chain, string companyId)
        {
            var prev = new string('0', 64);
            var seq = 0;
            foreach (var r in results.Select("CompanyId = '" + companyId + "'"))
            {
                seq++;
                var payload = string.Join("|", r["LedgerId"], r["TxnId"], r["Outcome"], r["Decision"], r["Reason"], r["Evidence"]);
                var ph = Calc.Sha256(payload);
                var entry = Calc.Sha256(seq + "|" + prev + "|" + ph);
                chain.Rows.Add(companyId, seq.ToString(), ph, prev, entry, payload);
                prev = entry;
            }
            Log("Audit trail " + companyId + ": " + seq + " entries, head " + prev.Substring(0, 12));
            return (prev, seq);
        }
    }
}
