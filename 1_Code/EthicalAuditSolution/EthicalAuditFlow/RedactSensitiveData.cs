using System;
using System.Data;
using UiPath.CodedWorkflows;

namespace EthicalAuditFlow
{
    public class RedactSensitiveData : CodedWorkflow
    {
        /// <summary>
        /// Pre-persistence redaction (data minimisation). Masks IBAN, e-mail, card, phone and tax-ID patterns in
        /// the extracted invoice text in memory, before any log, queue payload, working paper or file is written.
        /// </summary>
        [Workflow]
        public DataTable Execute(DataTable documents, bool redact)
        {
            if (!redact)
            {
                Log("WARNING: redaction disabled (Baseline) - raw document text will flow downstream", LogLevel.Warn);
                return documents;
            }
            var engine = new RedactionEngine(Guid.NewGuid().ToString("N"));
            foreach (DataRow r in documents.Rows) r["RawText"] = engine.Redact(r["RawText"].ToString());
            Log("Redacted " + documents.Rows.Count + " documents before any log, queue or file write");
            return documents;
        }
    }
}
