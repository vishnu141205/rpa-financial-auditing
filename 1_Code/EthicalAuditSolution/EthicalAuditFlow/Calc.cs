using System;
using System.Data;
using System.Globalization;
using System.Security.Cryptography;
using System.Text;

namespace EthicalAuditFlow
{
    /// <summary>Shared helpers for the audit script blocks (parsing, hashing, table layouts).</summary>
    public static class Calc
    {
        public static double D(object o) => double.Parse(o.ToString(), CultureInfo.InvariantCulture);

        public static string S(double v, int digits = 2) => Math.Round(v, digits).ToString(CultureInfo.InvariantCulture);

        public static string Sha256(string s)
        {
            using (var sha = SHA256.Create())
            {
                var h = sha.ComputeHash(Encoding.UTF8.GetBytes(s));
                var sb = new StringBuilder();
                foreach (var b in h) sb.Append(b.ToString("x2"));
                return sb.ToString();
            }
        }

        public static DataRow Company(DataTable companies, string id) => companies.Select("CompanyId = '" + id + "'")[0];

        public static DataRow Plan(DataTable planning, string id) => planning.Select("CompanyId = '" + id + "'")[0];

        public static DataTable Table(params string[] columns)
        {
            var t = new DataTable();
            foreach (var c in columns) t.Columns.Add(c, typeof(string));
            return t;
        }
    }
}
