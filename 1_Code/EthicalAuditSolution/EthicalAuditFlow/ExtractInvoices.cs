using System;
using System.Collections.Generic;
using System.Data;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text.RegularExpressions;
using UglyToad.PdfPig;
using UglyToad.PdfPig.DocumentLayoutAnalysis.TextExtractor;
using UiPath.CodedWorkflows;

namespace EthicalAuditFlow
{
    public class ExtractInvoices : CodedWorkflow
    {
        private const double Found = 0.97;

        /// <summary>
        /// Intake step: reads each invoice PDF in the folder and extracts the audit fields with labelled-pattern
        /// matching. A PDF with no text layer (a poor scan) cannot be read, so every field gets confidence 0 and the
        /// document is routed to a human by the confidence bound. The vendor name is mapped to the approved vendor
        /// master; a name that is not in the master maps to no vendor.
        /// (Connection point: swap this block for Document Understanding when that service is licensed.)
        /// </summary>
        [Workflow]
        public (DataTable documents, int extracted, int unreadable, double extractionAccuracyPct) Execute(
            string invoiceFolder, DataTable documents, DataTable companies, DataTable vendorMaster)
        {
            var byDoc = documents.AsEnumerable().ToDictionary(r => r["DocId"].ToString());
            // an invoice PDF is named after its invoice number (TxnId); older sets are named after the document id
            var byTxn = documents.AsEnumerable().GroupBy(r => r["TxnId"].ToString()).Where(g => g.Count() == 1).ToDictionary(g => g.Key, g => g.First());
            var extracted = 0; var unreadable = 0; var agree = 0; var compared = 0;
            if (!Directory.Exists(invoiceFolder))
            {
                Log("Invoice folder not found: " + invoiceFolder, LogLevel.Warn);
                return (documents, 0, 0, 0);
            }
            foreach (var file in Directory.GetFiles(invoiceFolder, "*.pdf").OrderBy(f => f, StringComparer.Ordinal))
            {
                var docId = Path.GetFileNameWithoutExtension(file);
                if (!byDoc.TryGetValue(docId, out var row) && !byTxn.TryGetValue(docId, out row))
                {
                    Log("PDF " + docId + " has no intake record; skipped", LogLevel.Warn);
                    continue;
                }
                var intake = row.ItemArray.Clone() as object[];   // values from the intake record, kept only for comparison
                var text = ReadText(file);
                if (string.IsNullOrWhiteSpace(text))
                {
                    // Unreadable scan: keep the intake identity so the ledger can still be linked, zero the confidence.
                    row["ConfTxnId"] = "0.00"; row["ConfAmount"] = "0.00"; row["ConfVendor"] = "0.00";
                    row["RawText"] = "";
                    unreadable++;
                    continue;
                }
                var txn = Grab(text, @"Invoice number:\s*([A-Z0-9\-]+)");
                var date = Grab(text, @"Invoice date:\s*(\d{4}-\d{2}-\d{2})");
                var total = Regex.Match(text, @"Total due:\s*([\d,]+\.\d{2})\s*([A-Z]{3})");
                var billTo = Grab(text, @"Bill to:\s*([^\r\n]+)");
                var vendorName = VendorName(text);
                var company = companies.AsEnumerable().FirstOrDefault(c => c["Name"].ToString() == billTo);
                var companyId = company != null ? company["CompanyId"].ToString() : row["CompanyId"].ToString();
                var vendorId = vendorMaster.AsEnumerable()
                    .Where(v => v["CompanyId"].ToString() == companyId &&
                                string.Equals(v["VendorName"].ToString(), vendorName, StringComparison.OrdinalIgnoreCase))
                    .Select(v => v["VendorId"].ToString()).FirstOrDefault() ?? "UNLISTED";
                var amount = total.Success
                    ? double.Parse(total.Groups[1].Value.Replace(",", ""), CultureInfo.InvariantCulture).ToString("0.00", CultureInfo.InvariantCulture)
                    : "0.00";

                row["CompanyId"] = companyId;
                row["TxnId"] = txn ?? row["TxnId"].ToString();
                row["VendorId"] = vendorId;
                row["VendorName"] = vendorName ?? "";
                row["Amount"] = amount;
                row["Currency"] = total.Success ? total.Groups[2].Value : row["Currency"].ToString();
                row["InvoiceDate"] = date ?? row["InvoiceDate"].ToString();
                row["VendorIban"] = Grab(text, @"IBAN:\s*([A-Z0-9]+)") ?? "";
                row["VendorEmail"] = Grab(text, @"Email:\s*(\S+)") ?? "";
                row["VendorPhone"] = Grab(text, @"Phone:\s*(\+[\d\- ]+\d)") ?? "";
                row["TaxId"] = Grab(text, @"Tax ID:\s*([\d\-]+)") ?? "";
                row["CardLast"] = Grab(text, @"Card on file:\s*([\d\-]+)") ?? "";
                row["ConfTxnId"] = Conf(txn != null);
                row["ConfAmount"] = Conf(total.Success);
                row["ConfVendor"] = Conf(vendorName != null);
                row["RawText"] = Regex.Replace(text, @"\s+", " ").Trim();
                extracted++;

                // extraction accuracy: does the PDF agree with the intake record (the expected values)?
                compared++;
                var cols = documents.Columns;
                bool Same(string col) => string.Equals(row[col].ToString(), intake[cols[col].Ordinal]?.ToString(), StringComparison.Ordinal);
                if (Same("TxnId") && Same("Amount") && Same("Currency")) agree++;
            }
            var acc = compared == 0 ? 0.0 : Math.Round(100.0 * agree / compared, 1);
            Log("PDF extraction: " + extracted + " read, " + unreadable + " unreadable scans, " + acc + "% agree with intake values");
            return (documents, extracted, unreadable, acc);
        }

        private static string Conf(bool ok) => (ok ? Found : 0.0).ToString("0.00", CultureInfo.InvariantCulture);

        private static string Grab(string text, string pattern)
        {
            var m = Regex.Match(text, pattern);
            return m.Success ? m.Groups[1].Value.Trim() : null;
        }

        private static string VendorName(string text)
        {
            var lines = text.Split(new[] { '\r', '\n' }, StringSplitOptions.RemoveEmptyEntries).Select(l => l.Trim()).ToList();
            var i = lines.FindIndex(l => l.Equals("INVOICE", StringComparison.OrdinalIgnoreCase));
            for (var j = i + 1; i >= 0 && j < lines.Count; j++)
                if (!lines[j].Contains(":")) return lines[j];
            return null;
        }

        private static string ReadText(string file)
        {
            try
            {
                using (var pdf = PdfDocument.Open(file))
                    return string.Join("\n", pdf.GetPages().Select(p => ContentOrderTextExtractor.GetText(p)));
            }
            catch (Exception)
            {
                return "";
            }
        }
    }
}
