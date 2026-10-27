using System;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;

namespace EthicalAuditFlow
{
    /// <summary>
    /// Pre-persistence redaction. Runs in memory on every string BEFORE it reaches a log,
    /// queue payload, working paper or temp file. Each match becomes a salted, per-run pseudonym token so
    /// reviewers can still correlate repeats without seeing the value.
    /// </summary>
    public class RedactionEngine
    {
        public static readonly (string Name, Regex Pattern)[] Rules =
        {
            ("IBAN",  new Regex(@"\b[A-Z]{2}\d{2}[A-Z]{4}\d{10,14}\b", RegexOptions.Compiled)),
            ("EMAIL", new Regex(@"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", RegexOptions.Compiled)),
            ("CARD",  new Regex(@"\b\d{4}-\d{4}-\d{4}-\d{4}\b", RegexOptions.Compiled)),
            ("PHONE", new Regex(@"\+\d{1,3}[-\s]?\d{3}[-\s]?\d{3}[-\s]?\d{4}", RegexOptions.Compiled)),
            ("TAXID", new Regex(@"\b\d{3}-\d{2}-\d{4}\b", RegexOptions.Compiled)),
        };

        private readonly string _salt;

        public RedactionEngine(string salt)
        {
            _salt = salt ?? Guid.NewGuid().ToString("N");
        }

        public string Redact(string text)
        {
            if (string.IsNullOrEmpty(text)) return text;
            foreach (var rule in Rules)
            {
                var name = rule.Name;
                text = rule.Pattern.Replace(text, m => "[" + name + "#" + Token(m.Value) + "]");
            }
            return text;
        }

        private string Token(string value)
        {
            using (var sha = SHA256.Create())
            {
                var hash = sha.ComputeHash(Encoding.UTF8.GetBytes(_salt + value));
                return BitConverter.ToString(hash, 0, 4).Replace("-", "").ToLowerInvariant();
            }
        }
    }
}
