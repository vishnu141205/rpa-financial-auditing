"""Generates the visual (XAML) workflows for the EthicalAuditFlow project.

Run:  python -I tools/build_xaml.py
Output: EthicalAuditSolution/EthicalAuditFlow/*.xaml
Expression language: VisualBasic. Every stage is a plain-activity workflow
(Assign / If / For Each / Add Data Row / Read CSV ...) so it opens as blocks in Studio.
"""
import html
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "EthicalAuditSolution" / "EthicalAuditFlow"

STR, INT, DBL, BOOL = "x:String", "x:Int32", "x:Double", "x:Boolean"
DT, ROW = "sd:DataTable", "sd:DataRow"
INV = "System.Globalization.CultureInfo.InvariantCulture"


def esc(s):
    return html.escape(s, quote=True)


# ---------------------------------------------------------------- primitives
def var(t, name, default=None):
    d = f' Default="{esc(default)}"' if default is not None else ""
    return f'<Variable x:TypeArguments="{t}" Name="{name}"{d} />'


def val(t, expr):
    return (f'<InArgument x:TypeArguments="{t}"><VisualBasicValue x:TypeArguments="{t}" '
            f'ExpressionText="{esc(expr)}" /></InArgument>')


def seq(name, children, variables=()):
    v = ""
    if variables:
        v = "<Sequence.Variables>" + "".join(variables) + "</Sequence.Variables>"
    return f'<Sequence DisplayName="{esc(name)}">{v}{"".join(children)}</Sequence>'


def assign(t, to, value, name=None):
    name = name or f"Set {to}"
    return (f'<Assign x:TypeArguments="{t}" DisplayName="{esc(name)}"><Assign.To>'
            f'<OutArgument x:TypeArguments="{t}"><VisualBasicReference x:TypeArguments="{t}" '
            f'ExpressionText="{esc(to)}" /></OutArgument></Assign.To><Assign.Value>{val(t, value)}'
            f'</Assign.Value></Assign>')


def log(msg, level="Info", name="Log"):
    return (f'<ui:LogMessage Level="{level}" DisplayName="{esc(name)}"><ui:LogMessage.Message>'
            f'{val("x:Object", msg)}</ui:LogMessage.Message></ui:LogMessage>')


def if_(cond, then, else_=None, name="If"):
    e = f'<If.Else>{seq("Else", else_)}</If.Else>' if else_ else ""
    return (f'<If DisplayName="{esc(name)}"><If.Condition>{val(BOOL, cond)}</If.Condition>'
            f'<If.Then>{seq("Then", then)}</If.Then>{e}</If>')


def foreach(t, values, item, body, name="For Each", variables=()):
    return (f'<ui:ForEach x:TypeArguments="{t}" DisplayName="{esc(name)}"><ui:ForEach.Values>'
            f'{val("sc:IEnumerable", values)}</ui:ForEach.Values><ui:ForEach.Body>'
            f'<ActivityAction x:TypeArguments="{t}"><ActivityAction.Argument>'
            f'<DelegateInArgument x:TypeArguments="{t}" Name="{item}" /></ActivityAction.Argument>'
            f'{seq("Body", body, variables)}</ActivityAction></ui:ForEach.Body></ui:ForEach>')


def read_csv(path_expr, table, name):
    return (f'<csv:ReadCsvFile DisplayName="{esc(name)}" FilePath="[{esc(path_expr)}]" '
            f'IncludeColumnNames="True" DataTable="[{table}]" />')


def write_csv(path_expr, table, name):
    return (f'<csv:AppendWriteCsvFile DisplayName="{esc(name)}" FilePath="[{esc(path_expr)}]" '
            f'CsvAction="Write" AddHeaders="True"><csv:AppendWriteCsvFile.DataTable>'
            f'<InArgument x:TypeArguments="sd:DataTable">[{table}]</InArgument>'
            f'</csv:AppendWriteCsvFile.DataTable></csv:AppendWriteCsvFile>')


def new_table(table, header, name):
    return (f'<uic:GenerateDataTable DisplayName="{esc(name)}" AutoDetectTypes="False" UseColumnHeader="True" '
            f'CSVParsing="True"><uic:GenerateDataTable.Input><InArgument x:TypeArguments="x:String">'
            f'["{header}"]</InArgument></uic:GenerateDataTable.Input><uic:GenerateDataTable.DataTable>'
            f'<OutArgument x:TypeArguments="sd:DataTable">[{table}]</OutArgument>'
            f'</uic:GenerateDataTable.DataTable></uic:GenerateDataTable>')


def add_row(table, items, name):
    return (f'<uic:AddDataRow DisplayName="{esc(name)}"><uic:AddDataRow.DataTable>'
            f'<InOutArgument x:TypeArguments="sd:DataTable">[{table}]</InOutArgument></uic:AddDataRow.DataTable>'
            f'<uic:AddDataRow.ArrayRow><InArgument x:TypeArguments="s:Object[]">'
            f'[{esc("New Object() {" + ", ".join(items) + "}")}]</InArgument></uic:AddDataRow.ArrayRow>'
            f'</uic:AddDataRow>')


def invoke(file, args, name):
    # Direct InArgument/OutArgument children (a Dictionary wrapper is silently cleared by Studio on load).
    a = ""
    for key, (kind, t, expr) in args.items():
        tag = {"in": "InArgument", "out": "OutArgument", "io": "InOutArgument"}[kind]
        a += f'<{tag} x:TypeArguments="{t}" x:Key="{key}">[{esc(expr)}]</{tag}>'
    return (f'<ui:InvokeWorkflowFile DisplayName="{esc(name)}" WorkflowFileName="{file}" UnSafe="False">'
            f'<ui:InvokeWorkflowFile.Arguments>{a}</ui:InvokeWorkflowFile.Arguments></ui:InvokeWorkflowFile>')


def sha(expr):
    return (f"BitConverter.ToString(System.Security.Cryptography.SHA256.Create().ComputeHash("
            f"System.Text.Encoding.UTF8.GetBytes({expr}))).Replace(\"-\", \"\").ToLower()")


def dbl(row, col):
    return f'Double.Parse({row}("{col}").ToString, {INV})'


HEADER = """<Activity mc:Ignorable="sap sap2010" x:Class="{cls}" mva:VisualBasic.Settings="{{x:Null}}"
 xmlns="http://schemas.microsoft.com/netfx/2009/xaml/activities"
 xmlns:av="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
 xmlns:csv="clr-namespace:UiPath.CSV.Activities;assembly=UiPath.Excel.Activities"
 xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006"
 xmlns:mva="clr-namespace:Microsoft.VisualBasic.Activities;assembly=System.Activities"
 xmlns:s="clr-namespace:System;assembly=System.Private.CoreLib"
 xmlns:sap="http://schemas.microsoft.com/netfx/2009/xaml/activities/presentation"
 xmlns:sap2010="http://schemas.microsoft.com/netfx/2010/xaml/activities/presentation"
 xmlns:sc="clr-namespace:System.Collections;assembly=System.Private.CoreLib"
 xmlns:scg="clr-namespace:System.Collections.Generic;assembly=System.Private.CoreLib"
 xmlns:sco="clr-namespace:System.Collections.ObjectModel;assembly=mscorlib"
 xmlns:sd="clr-namespace:System.Data;assembly=System.Data.Common"
 xmlns:upae="clr-namespace:UiPath.Persistence.Activities.ExternalTask;assembly=UiPath.Persistence.Activities"
 xmlns:upaf="clr-namespace:UiPath.Persistence.Activities.FormTask;assembly=UiPath.Persistence.Activities"
 xmlns:upat="clr-namespace:UiPath.Persistence.Activities.Tasks;assembly=UiPath.Persistence.Activities"
 xmlns:upmt="clr-namespace:UiPath.Persistence.Activities.Model.Task;assembly=UiPath.Persistence.Activities"
 xmlns:ucas="clr-namespace:UiPath.Core.Activities.Storage;assembly=UiPath.System.Activities"
 xmlns:ui="http://schemas.uipath.com/workflow/activities"
 xmlns:uic="clr-namespace:UiPath.Core.Activities;assembly=UiPath.System.Activities"
 xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml">
 <TextExpression.NamespacesForImplementation>
  <sco:Collection x:TypeArguments="x:String">
   <x:String>System.Activities</x:String><x:String>System.Activities.Statements</x:String>
   <x:String>System.Activities.Expressions</x:String><x:String>Microsoft.VisualBasic</x:String>
   <x:String>Microsoft.VisualBasic.Activities</x:String><x:String>System</x:String>
   <x:String>System.Collections</x:String><x:String>System.Collections.Generic</x:String>
   <x:String>System.Data</x:String><x:String>System.IO</x:String><x:String>System.Linq</x:String>
   <x:String>System.Text.RegularExpressions</x:String><x:String>UiPath.Core</x:String>
   <x:String>UiPath.Core.Activities</x:String><x:String>UiPath.Persistence.Activities.ExternalTask</x:String><x:String>UiPath.Persistence.Activities.FormTask</x:String>
  </sco:Collection>
 </TextExpression.NamespacesForImplementation>
 <TextExpression.ReferencesForImplementation>
  <sco:Collection x:TypeArguments="AssemblyReference">
   <AssemblyReference>System.Activities</AssemblyReference><AssemblyReference>Microsoft.VisualBasic</AssemblyReference>
   <AssemblyReference>System.Private.CoreLib</AssemblyReference><AssemblyReference>mscorlib</AssemblyReference>
   <AssemblyReference>System.Data</AssemblyReference><AssemblyReference>System.Data.Common</AssemblyReference>
   <AssemblyReference>System</AssemblyReference><AssemblyReference>System.Linq</AssemblyReference>
   <AssemblyReference>System.Core</AssemblyReference><AssemblyReference>System.Data.DataSetExtensions</AssemblyReference>
   <AssemblyReference>System.Text.RegularExpressions</AssemblyReference>
   <AssemblyReference>System.Security.Cryptography</AssemblyReference>
   <AssemblyReference>UiPath.System.Activities</AssemblyReference><AssemblyReference>UiPath.Excel.Activities</AssemblyReference><AssemblyReference>UiPath.Persistence.Activities</AssemblyReference>
  </sco:Collection>
 </TextExpression.ReferencesForImplementation>
"""


def members(args):
    kinds = {"in": "InArgument", "out": "OutArgument", "io": "InOutArgument"}
    m = "".join(f'<x:Property Name="{n}" Type="{kinds[k]}({t})" />' for n, (k, t) in args.items())
    return f"<x:Members>{m}</x:Members>" if m else ""


def write_workflow(file, args, body):
    cls = file.replace(".xaml", "")
    head = HEADER.format(cls=cls)
    marker = " <TextExpression.NamespacesForImplementation>"
    i = head.index(marker)
    # Studio writes x:Members first, directly under the root element.
    text = head[:i] + " " + members(args) + "\n" + head[i:] + body + "\n</Activity>\n"
    (OUT / file).write_text(text, encoding="utf-8")


# ---------------------------------------------------------------- Stage 1
def stage1():
    args = {"in_DataFolder": ("in", STR), "out_Companies": ("out", DT), "out_Ledger": ("out", DT),
            "out_Documents": ("out", DT), "out_Truth": ("out", DT), "out_VendorMaster": ("out", DT)}
    body = seq("Stage 1 - Load organization, ledger and extracted invoices", [
        read_csv('in_DataFolder & "/companies.csv"', "out_Companies", "Read companies (organization hierarchy)"),
        read_csv('in_DataFolder & "/ledger.csv"', "out_Ledger", "Read ledger"),
        read_csv('in_DataFolder & "/documents.csv"', "out_Documents", "Read extracted invoices (Document Understanding output)"),
        read_csv('in_DataFolder & "/ground_truth.csv"', "out_Truth", "Read ground truth (benchmark only)"),
        read_csv('in_DataFolder & "/vendor_master.csv"', "out_VendorMaster", "Read the approved vendor master"),
        log('"Loaded " & out_Companies.Rows.Count & " companies, " & out_Ledger.Rows.Count & " ledger rows, " '
            '& out_Documents.Rows.Count & " documents"', name="Log load summary"),
    ])
    write_workflow("Stage1_LoadData.xaml", args, body)


PATTERNS = [
    ("IBAN", r"\b[A-Z]{2}\d{2}[A-Z]{4}\d{10,14}\b"),
    ("EMAIL", r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}"),
    ("CARD", r"\b\d{4}-\d{4}-\d{4}-\d{4}\b"),
    ("PHONE", r"\+\d{1,3}[-\s]?\d{3}[-\s]?\d{3}[-\s]?\d{4}"),
    ("TAXID", r"\b\d{3}-\d{2}-\d{4}\b"),
]


def vb_str(s):
    return '"' + s.replace('"', '""') + '"'


# ---------------------------------------------------------------- Stage 3 : reconcile every company (script block per company)
RESULT_HEADER = ("OrgId,CompanyId,LedgerId,TxnId,VendorId,Amount,Currency,AmountUSD,Outcome,Decision,Reason,"
                 "VariancePct,VarianceAmountUSD,Evidence")


def stage3():
    args = {"in_Ethical": ("in", BOOL), "in_Companies": ("in", DT), "in_Ledger": ("in", DT),
            "in_Documents": ("in", DT), "out_Results": ("out", DT)}
    body = seq("Stage 3 - Reconcile each company in isolation", [
        new_table("out_Results", RESULT_HEADER, "Create results table"),
        foreach(ROW, "in_Companies.Rows", "crow", [
            assign(STR, "coId", 'crow("CompanyId").ToString', "Company id"),
            log('"Reconciling " & coId & " (" & crow("Name").ToString & ")"', name="Log company start"),
            invoke("ReconcileCompany.cs", {
                "results": ("in", DT, "out_Results"), "companyId": ("in", STR, "coId"),
                "companies": ("in", DT, "in_Companies"), "ledger": ("in", DT, "in_Ledger"),
                "documents": ("in", DT, "in_Documents"), "ethical": ("in", BOOL, "in_Ethical"),
                "Output": ("out", DT, "out_Results")}, "Script block: reconcile this company"),
        ], "For each company in the organization", [var(STR, "coId")]),
    ])
    write_workflow("Stage3_ReconcileCompanies.xaml", args, body)


# ---------------------------------------------------------------- Stage 4 : intercompany (plain blocks)
def result_row(table, items, name):
    return add_row(table, items, name)


def stage4():
    args = {"in_Ethical": ("in", BOOL), "in_Companies": ("in", DT), "in_Ledger": ("in", DT),
            "io_Results": ("io", DT)}
    legs = 'in_Ledger.Select("IsIntercompany = \'true\' AND TxnId = \'" & icTxn & "\'")'
    comp = 'in_Companies.Select("CompanyId = \'" & {c} & "\'")(0)'
    paired = [
        assign(STR, "coA", legs + '(0)("CompanyId").ToString', "Leg A company"),
        assign(STR, "coB", legs + '(1)("CompanyId").ToString', "Leg B company"),
        assign(DBL, "grpA", dbl(legs + "(0)", "Amount") + " * " + dbl(comp.format(c="coA"), "FxToGroup"),
               "Leg A in group currency (USD)"),
        assign(DBL, "grpB", dbl(legs + "(1)", "Amount") + " * " + dbl(comp.format(c="coB"), "FxToGroup"),
               "Leg B in group currency (USD)"),
        assign(DBL, "icVar", "Math.Round(Math.Abs(grpA - grpB) / Math.Max(grpA, grpB) * 100.0, 4)",
               "Intercompany variance %"),
        assign(DBL, "icTol", "If(in_Ethical, " + dbl("in_Companies.Rows(0)", "IcTolerancePct") + ", 0.0)",
               "Intercompany tolerance (0 in Baseline)"),
        assign(STR, "outcome", 'If(icVar <= icTol, "IC_MATCH", "IC_MISMATCH")'),
        assign(STR, "decision", 'If(outcome = "IC_MATCH", "Commit", "RouteToAuditor")'),
        assign(STR, "reason", 'If(outcome = "IC_MATCH", "intercompany legs agree in group currency", '
                              '"intercompany legs differ by " & icVar.ToString(' + INV + ') & "%")'),
        assign(STR, "diffUsd", 'If(outcome = "IC_MATCH", "0", Math.Round(Math.Abs(grpA - grpB), 2).ToString(' + INV + '))',
               "Potential misstatement (USD)"),
    ]
    for i, co in enumerate(("coA", "coB")):
        usd = "grpA" if i == 0 else "grpB"
        paired.append(result_row("io_Results", [
            'in_Companies.Rows(0)("OrgId").ToString', co, f'{legs}({i})("LedgerId").ToString', "icTxn",
            f'{legs}({i})("VendorId").ToString', f'{legs}({i})("Amount").ToString', f'{legs}({i})("Currency").ToString',
            f"Math.Round({usd}, 2).ToString({INV})", "outcome", "decision", "reason", f"icVar.ToString({INV})",
            "diffUsd", '""'], f"Add result row for leg {'AB'[i]}"))
    unpaired = [
        foreach(ROW, legs, "leg", [
            result_row("io_Results", [
                'leg("OrgId").ToString', 'leg("CompanyId").ToString', 'leg("LedgerId").ToString', "icTxn",
                'leg("VendorId").ToString', 'leg("Amount").ToString', 'leg("Currency").ToString', '"0"',
                '"IC_MISMATCH"', '"RouteToAuditor"', '"unpaired intercompany leg"', '"0"', '"0"', '""'],
                "Add unpaired leg"),
        ], "For each unpaired leg"),
    ]
    each_tx = [
        assign(INT, "legCount", legs + ".Length", "Number of legs"),
        if_("legCount = 2", paired, unpaired, "If both legs present"),
    ]
    ic_list = ('in_Ledger.AsEnumerable().Where(Function(r) r("IsIntercompany").ToString = "true")'
               '.Select(Function(r) r("TxnId").ToString).Distinct().ToList()')
    body = seq("Stage 4 - Intercompany matching across the organization's companies", [
        foreach(STR, ic_list, "icTxn", each_tx, "For each intercompany transaction",
                [var(INT, "legCount"), var(STR, "coA"), var(STR, "coB"), var(STR, "outcome"), var(STR, "decision"),
                 var(STR, "reason"), var(STR, "diffUsd"), var(DBL, "grpA"), var(DBL, "grpB"), var(DBL, "icVar"),
                 var(DBL, "icTol")]),
        log('"Intercompany matching done; results table now holds " & io_Results.Rows.Count & " rows"',
            name="Log intercompany summary"),
    ])
    write_workflow("Stage4_Intercompany.xaml", args, body)


# ---------------------------------------------------------------- Stage 5 : substantive audit tests (script blocks)
def stage5():
    args = {"in_Ethical": ("in", BOOL), "in_Companies": ("in", DT), "in_Ledger": ("in", DT),
            "in_Documents": ("in", DT), "io_Results": ("io", DT), "out_Duplicates": ("out", INT),
            "out_Orphans": ("out", DT)}
    body = seq("Stage 5 - Substantive audit tests", [
        invoke("TestDuplicates.cs", {
            "results": ("in", DT, "io_Results"), "ledger": ("in", DT, "in_Ledger"), "ethical": ("in", BOOL, "in_Ethical"),
            "Output": ("out", INT, "out_Duplicates")}, "Script block: duplicate-payment test (occurrence)"),
        invoke("TestCompleteness.cs", {
            "ledger": ("in", DT, "in_Ledger"), "documents": ("in", DT, "in_Documents"),
            "companies": ("in", DT, "in_Companies"), "ethical": ("in", BOOL, "in_Ethical"),
            "Output": ("out", DT, "out_Orphans")}, "Script block: unrecorded-liability test (completeness)"),
        log('"Substantive tests: " & out_Duplicates & " suspected duplicates, " & out_Orphans.Rows.Count & " invoices without ledger entry"',
            name="Log test summary"),
    ])
    write_workflow("Stage5_AuditTests.xaml", args, body)


# ---------------------------------------------------------------- Stage 6 : audit trail (hash chain per company)
def stage6():
    args = {"in_Companies": ("in", DT), "in_Results": ("in", DT), "out_Chain": ("out", DT), "out_OrgAnchor": ("out", STR)}
    company = [
        assign(STR, "coId", 'crow("CompanyId").ToString', "Company id"),
        invoke("AppendAuditChain.cs", {
            "results": ("in", DT, "in_Results"), "chain": ("in", DT, "out_Chain"), "companyId": ("in", STR, "coId"),
            "head": ("out", STR, "head"), "entries": ("out", INT, "entries")}, "Script block: append to tamper-evident chain"),
        assign(STR, "anchorInput", 'anchorInput & coId & ":" & head & ";"', "Fold company chain head into the organization anchor"),
    ]
    body = seq("Stage 6 - Audit trail (SHA-256 hash chain per company, anchored at organization level)", [
        new_table("out_Chain", "CompanyId,Seq,PayloadHash,PrevHash,EntryHash,Payload", "Create audit chain table"),
        assign(STR, "anchorInput", '""'),
        foreach(ROW, "in_Companies.Rows", "crow", company, "For each company",
                [var(STR, "coId"), var(STR, "head"), var(INT, "entries")]),
        assign(STR, "out_OrgAnchor", sha("anchorInput"), "Organization-level anchor hash"),
        log('"Organization anchor " & out_OrgAnchor.Substring(0, 16)', name="Log anchor"),
    ], [var(STR, "anchorInput")])
    write_workflow("Stage6_AuditTrail.xaml", args, body)


# ---------------------------------------------------------------- Stage 7 : benchmark metrics
def stage7():
    args = {"in_Results": ("in", DT), "in_Truth": ("in", DT), "in_Chain": ("in", DT), "in_Findings": ("in", DT),
            "in_Orphans": ("in", DT), "in_Mode": ("in", STR), "in_Conclusion": ("in", STR), "in_JvSummary": ("in", STR), "in_RvSummary": ("in", STR),
            "out_Committed": ("out", INT), "out_Routed": ("out", INT), "out_FalseCommits": ("out", INT),
            "out_FalseRoutes": ("out", INT), "out_AccuracyPct": ("out", DBL), "out_LeakHits": ("out", INT),
            "out_ChainOk": ("out", BOOL), "out_Summary": ("out", STR)}
    per_result = [
        assign(STR, "expected", 'in_Truth.Select("LedgerId = \'" & r("LedgerId").ToString & "\'")(0)("ExpectedOutcome").ToString',
               "Expected outcome (ground truth)"),
        assign(BOOL, "expCommit", 'expected = "AUTO_MATCH" OrElse expected = "AUTO_MATCH_TOLERANCE" OrElse expected = "IC_MATCH"',
               "Should it commit?"),
        assign(BOOL, "actCommit", 'r("Decision").ToString = "Commit"', "Did the bot commit?"),
        assign(INT, "out_Committed", "out_Committed + If(actCommit, 1, 0)", "Count committed"),
        assign(INT, "correct", "correct + If(actCommit = expCommit, 1, 0)", "Count correct decisions"),
        assign(INT, "out_FalseCommits", "out_FalseCommits + If(actCommit AndAlso Not expCommit, 1, 0)", "Count false commits"),
        assign(INT, "out_FalseRoutes", "out_FalseRoutes + If((Not actCommit) AndAlso expCommit, 1, 0)", "Count false routes"),
    ]
    leak = [assign(INT, "out_LeakHits",
                   f'out_LeakHits + System.Text.RegularExpressions.Regex.Matches(blob, {vb_str(p)}).Count',
                   f"Count {n} patterns left in persisted text") for n, p in PATTERNS]
    chain = [
        assign(STR, "expectedPrev", 'If(a("CompanyId").ToString <> lastCo, New String("0"c, 64), expectedPrev)', "Chain start per company"),
        assign(BOOL, "linkOk",
               'a("PrevHash").ToString = expectedPrev AndAlso a("PayloadHash").ToString = ' + sha('a("Payload").ToString')
               + ' AndAlso a("EntryHash").ToString = ' + sha('a("Seq").ToString & "|" & a("PrevHash").ToString & "|" & a("PayloadHash").ToString'),
               "Recompute and compare hashes"),
        assign(BOOL, "out_ChainOk", "out_ChainOk AndAlso linkOk", "Accumulate chain verdict"),
        assign(STR, "expectedPrev", 'a("EntryHash").ToString', "Advance expected link"),
        assign(STR, "lastCo", 'a("CompanyId").ToString', "Remember company"),
    ]
    blob = ('String.Join(" ", in_Chain.AsEnumerable().Select(Function(x) x("Payload").ToString())) & " " & '
            'String.Join(" ", in_Findings.AsEnumerable().Select(Function(x) x("Evidence").ToString()))')
    body = seq("Stage 7 - Benchmark metrics, leakage scan and chain verification", [
        assign(INT, "out_Committed", "0"), assign(INT, "out_FalseCommits", "0"), assign(INT, "out_FalseRoutes", "0"),
        assign(INT, "out_LeakHits", "0"), assign(BOOL, "out_ChainOk", "True"), assign(INT, "correct", "0"),
        foreach(ROW, "in_Results.Rows", "r", per_result, "For each result vs ground truth",
                [var(STR, "expected"), var(BOOL, "expCommit"), var(BOOL, "actCommit")]),
        assign(INT, "out_Routed", "in_Results.Rows.Count - out_Committed", "Routed = rows - committed"),
        assign(DBL, "out_AccuracyPct", "Math.Round(100.0 * correct / in_Results.Rows.Count, 2)", "Decision accuracy %"),
        assign(STR, "blob", blob, "All text that was persisted (audit trail + findings register)"),
        *leak,
        foreach(ROW, "in_Chain.Rows", "a", chain, "Verify every link of the hash chain"),
        assign(INT, "orphansExpected", 'in_Truth.Select("ExpectedOutcome = \'ORPHAN_DOCUMENT\'").Length', "Orphan invoices seeded"),
        assign(STR, "out_Summary",
               '"Mode=" & in_Mode & "; Rows=" & in_Results.Rows.Count & "; Committed=" & out_Committed & "; Routed=" & out_Routed '
               '& "; DecisionAccuracy%=" & out_AccuracyPct & "; FalseCommits=" & out_FalseCommits & "; FalseRoutes=" & out_FalseRoutes '
               '& "; Findings=" & in_Findings.Rows.Count & "; OrphansFound=" & in_Orphans.Rows.Count & "/" & orphansExpected '
               '& "; " & in_JvSummary & "; " & in_RvSummary & "; SensitiveLeakHits=" & out_LeakHits & "; ChainIntact=" & out_ChainOk & "; Conclusion=" & in_Conclusion',
               "Build summary"),
        log("out_Summary", name="Log summary"),
    ], [var(INT, "correct"), var(INT, "orphansExpected"), var(STR, "blob"), var(STR, "expectedPrev", ""),
        var(STR, "lastCo", ""), var(BOOL, "linkOk")])
    write_workflow("Stage7_Metrics.xaml", args, body)


# ---------------------------------------------------------------- Stage 8 : write the audit working papers
def stage8():
    args = {"in_OutDir": ("in", STR), "in_Planning": ("in", DT), "in_Results": ("in", DT), "in_Findings": ("in", DT),
            "in_Chain": ("in", DT), "in_Report": ("in", DT), "in_ReviewTasks": ("in", DT)}
    body = seq("Stage 8 - Write the audit working papers", [
        f'<ui:CreateDirectory DisplayName="Create output folder" Path="[in_OutDir]" />',
        write_csv('in_OutDir & "/1_audit_plan.csv"', "in_Planning", "WP: audit plan (materiality, risk)"),
        write_csv('in_OutDir & "/2_reconciliation_results.csv"', "in_Results", "WP: reconciliation results"),
        write_csv('in_OutDir & "/3_findings_register.csv"', "in_Findings", "WP: findings register (reviewer queue)"),
        write_csv('in_OutDir & "/4_audit_report.csv"', "in_Report", "WP: summary of audit differences"),
        write_csv('in_OutDir & "/5_audit_trail_hash_chain.csv"', "in_Chain", "WP: tamper-evident audit trail"),
        write_csv('in_OutDir & "/6_review_tasks.csv"', "in_ReviewTasks", "WP: Action Center review tasks (for the finalize run)"),
        log('"Working papers written to " & in_OutDir', name="Log output location"),
    ])
    write_workflow("Stage8_WriteWorkingPapers.xaml", args, body)


# ---------------------------------------------------------------- Stage 9 : retain the working papers in an Orchestrator storage bucket
BUCKET = "EthicalAudit-WorkingPapers"


def stage9():
    args = {"in_OutDir": ("in", STR), "in_RunFolder": ("in", STR), "out_Stored": ("out", BOOL)}
    files = ["1_audit_plan.csv", "2_reconciliation_results.csv", "3_findings_register.csv", "4_audit_report.csv",
             "5_audit_trail_hash_chain.csv", "6_review_tasks.csv"]
    path_expr = 'in_OutDir & "/" & fname'
    dest_expr = 'in_RunFolder & "/"'
    upload = (f'<ucas:UploadStorageFile DisplayName="Upload working paper to bucket" StorageBucketName="{BUCKET}" '
              f'Path="[{esc(path_expr)}]" Destination="[{esc(dest_expr)}]" />')
    names_expr = "New String() {" + ", ".join('"' + f + '"' for f in files) + "}"
    catch = ('<TryCatch.Catches><Catch x:TypeArguments="s:Exception"><ActivityAction x:TypeArguments="s:Exception">'
             '<ActivityAction.Argument><DelegateInArgument x:TypeArguments="s:Exception" Name="exception" />'
             '</ActivityAction.Argument>' +
             seq("Catch", [
                 assign(BOOL, "out_Stored", "False", "Mark not stored"),
                 log('"Working papers NOT stored in bucket: " & exception.Message', "Error", "Log upload failure"),
             ]) + '</ActivityAction></Catch></TryCatch.Catches>')
    body = seq("Stage 9 - Retain the working papers (Orchestrator storage bucket)", [
        assign(BOOL, "out_Stored", "True", "Assume stored"),
        '<TryCatch DisplayName="Try upload to bucket"><TryCatch.Try>' + seq("Try", [
            foreach(STR, names_expr, "fname", [upload], "For each working paper"),
            log('"Working papers stored in bucket ' + BUCKET + ' under " & in_RunFolder', name="Log stored"),
        ]) + '</TryCatch.Try>' + catch + '</TryCatch>',
    ])
    write_workflow("Stage9_StoreWorkingPapers.xaml", args, body)


# ---------------------------------------------------------------- Stage 10 : review forms in Action Center (one per problem group)
import hashlib
import uuid as _uuid

# Labels of the three problem-specific fields on each form. The values come from BuildReviewGroups.cs.
FORM_SPECS = {
    "ROUTE_VARIANCE": ("Largest variance (%)", "Tolerance applied (%)", "Total difference (USD)"),
    "ROUTE_UNLINKED_VENDOR": ("Invoices affected", "Total invoice value (USD)", "Why it was flagged"),
    "ROUTE_LOW_CONFIDENCE": ("Lowest extraction confidence", "Confidence required", "Total value at risk (USD)"),
    "UNMATCHED_NO_DOC": ("Entries without an invoice", "Total value (USD)", "Why it was flagged"),
    "DUPLICATE_SUSPECT": ("Suspected duplicates", "Total value (USD)", "Duplicates of"),
    "ORPHAN_DOCUMENT": ("Invoices not in the ledger", "Total value (USD)", "Why it was flagged"),
    "IC_MISMATCH": ("Mismatched legs", "Total difference (USD)", "Tolerance applied (%)"),
    "JV_RISK": ("Entries flagged", "Total amount (USD)", "Why they were flagged"),
    "REV_CUTOFF": ("Sales flagged", "Total amount (USD)", "Why they were flagged"),
    "REV_CREDIT": ("Credit notes flagged", "Total amount (USD)", "Why they were flagged"),
}
GENERIC_SPEC = ("Findings", "High-severity findings", "Total exposure (USD)")


def form_layout(labels):
    comps = [
        {"label": "Company", "type": "textfield", "key": "Company", "disabled": True, "input": True},
        {"label": "Findings in this group", "type": "textfield", "key": "Findings", "disabled": True, "input": True},
        {"label": labels[0], "type": "textfield", "key": "Detail1", "disabled": True, "input": True},
        {"label": labels[1], "type": "textfield", "key": "Detail2", "disabled": True, "input": True},
        {"label": labels[2], "type": "textfield", "key": "Detail3", "disabled": True, "input": True},
        {"label": "Items (largest first)", "type": "textarea", "key": "Items", "disabled": True, "input": True, "rows": 9},
        {"label": "What the reviewer decides", "type": "textarea", "key": "Question", "disabled": True, "input": True, "rows": 3},
        {"label": "Reviewer comment (optional)", "type": "textarea", "key": "Comment", "input": True, "rows": 3},
        {"label": "Approve", "type": "button", "key": "Approve", "action": "submit", "theme": "primary", "input": True},
        {"label": "Reject", "type": "button", "key": "Reject", "action": "submit", "theme": "danger", "input": True},
    ]
    return json.dumps(comps, separators=(",", ":"))


def switch_str(expr, cases, default, name):
    body = "".join(f'<Sequence x:Key="{k}" DisplayName="{esc(k)}">{v}</Sequence>' for k, v in cases.items())
    return (f'<Switch x:TypeArguments="x:String" DisplayName="{esc(name)}"><Switch.Expression>'
            f'<InArgument x:TypeArguments="x:String"><VisualBasicValue x:TypeArguments="x:String" ExpressionText="{esc(expr)}" />'
            f'</InArgument></Switch.Expression>{body}<Switch.Default>{seq("Default", [default])}</Switch.Default></Switch>')


def stage10():
    args = {"in_Ethical": ("in", BOOL), "in_Grouping": ("in", STR), "in_Findings": ("in", DT), "in_Results": ("in", DT),
            "in_Companies": ("in", DT), "out_ReviewTasks": ("out", DT), "out_TasksCreated": ("out", INT)}

    def data_item(key, expr):
        return f'<InArgument x:TypeArguments="x:String" x:Key="{key}">[{esc(expr)}]</InArgument>'

    def create(labels, title):
        layout = form_layout(labels)
        guid = str(_uuid.uuid5(_uuid.NAMESPACE_URL, "ethicalaudit-review-" + hashlib.sha1(layout.encode()).hexdigest()))
        return (
            f'<upaf:CreateFormTask DisplayName="{esc(title)}" TaskPriority="High" GenerateInputFields="False" '
            f'FormLayoutGuid="{guid}" TaskTitle="[grpTitle]" TaskOutput="[taskData]">'
            '<upaf:CreateFormTask.FormLayout><InArgument x:TypeArguments="x:String">[' + esc(vb_str(layout)) + ']</InArgument>'
            '</upaf:CreateFormTask.FormLayout>'
            '<upaf:CreateFormTask.FormData><scg:Dictionary x:TypeArguments="x:String, Argument">'
            + data_item("Company", 'If(grow("CompanyId").ToString = "ALL", "All companies", grow("CompanyId").ToString)')
            + data_item("Findings", 'grow("Count").ToString')
            + data_item("Detail1", 'grow("Detail1").ToString')
            + data_item("Detail2", 'grow("Detail2").ToString')
            + data_item("Detail3", 'grow("Detail3").ToString')
            + data_item("Items", 'grow("Items").ToString')
            + data_item("Question", 'grow("Question").ToString')
            + data_item("Comment", '""')
            + '</scg:Dictionary></upaf:CreateFormTask.FormData></upaf:CreateFormTask>')

    cases = {k: create(v, "Create review form: " + k) for k, v in FORM_SPECS.items()}
    default = create(GENERIC_SPEC, "Create review form: mixed findings")
    per_group = [
        assign(STR, "grpTitle", 'grow("Title").ToString', "Form title"),
        switch_str('grow("Outcome").ToString', cases, default, "Choose the form for this problem type"),
        add_row("out_ReviewTasks", ['grow("GroupKey").ToString', 'grow("CompanyId").ToString', 'grow("Outcome").ToString',
                                    "taskData.Id.GetValueOrDefault().ToString", "grpTitle"], "Record the task id"),
        assign(INT, "out_TasksCreated", "out_TasksCreated + 1", "Count forms"),
    ]
    body = seq("Stage 10 - Raise review forms in Action Center (one per problem group)", [
        new_table("out_ReviewTasks", "GroupKey,CompanyId,Outcome,TaskId,Title", "Create review-task table"),
        assign(INT, "out_TasksCreated", "0"),
        if_("in_Ethical", [
            invoke("BuildReviewGroups.cs", {
                "findings": ("in", DT, "in_Findings"), "results": ("in", DT, "in_Results"),
                "companies": ("in", DT, "in_Companies"), "grouping": ("in", STR, "in_Grouping"),
                "groups": ("out", DT, "dtGroups"), "count": ("out", INT, "groupCount")}, "Script block: group the findings for review"),
            foreach(ROW, "dtGroups.Rows", "grow", per_group, "Create one review form per group",
                    [var(STR, "grpTitle"), var("upaf:FormTaskData", "taskData")]),
            log('"Created " & out_TasksCreated & " review forms; run the finalize process after the reviewers decide"',
                name="Log forms created"),
        ], [
            log('"Baseline mode: no reviewer forms are raised"', "Warn", "Log Baseline"),
        ], "If Ethical mode"),
    ], [var(DT, "dtGroups"), var(INT, "groupCount")])
    write_workflow("Stage10_ReviewTasks.xaml", args, body)


# ---------------------------------------------------------------- Main (Flowchart)
def main_flow():
    args = {"in_DataFolder": ("in", STR), "in_Mode": ("in", STR), "out_Summary": ("out", STR),
            "out_Committed": ("out", INT), "out_Routed": ("out", INT), "out_FalseCommits": ("out", INT),
            "out_LeakHits": ("out", INT), "out_ChainOk": ("out", BOOL), "out_AccuracyPct": ("out", DBL),
            "out_Conclusion": ("out", STR), "out_PapersStored": ("out", BOOL), "out_RunFolder": ("out", STR),
            "out_TasksCreated": ("out", INT), "in_ReviewGrouping": ("in", STR), "in_ExtractionMode": ("in", STR), "out_PdfExtracted": ("out", INT),
            "out_PdfUnreadable": ("out", INT), "out_ExtractionAccuracyPct": ("out", DBL)}
    wvars = [var(DT, n) for n in ("dtCompanies", "dtLedger", "dtDocs", "dtTruth", "dtPlanning", "dtResults",
                                   "dtOrphans", "dtFindings", "dtChain", "dtReport", "dtReviewTasks", "dtVendors", "dtJournal", "dtRevenue")]
    wvars += [var(BOOL, "ethical"), var(STR, "dataFolder"), var(STR, "outDir"), var(STR, "orgAnchor"),
              var(INT, "falseRoutes"), var(INT, "duplicates"), var(STR, "approvedBy"), var(STR, "jvSummary"), var(STR, "rvSummary")]
    IV = lambda f, a, n: invoke(f, a, n)
    steps = [
        ("Initialise", seq("Initialise run", [
            assign(BOOL, "ethical", 'Not String.Equals(in_Mode, "Baseline", StringComparison.OrdinalIgnoreCase)',
                   "Ethical mode unless Baseline requested"),
            assign(STR, "dataFolder", 'If(String.IsNullOrEmpty(in_DataFolder), "data", in_DataFolder)', "Data folder"),
            assign(STR, "out_RunFolder", 'DateTime.UtcNow.ToString("yyyyMMdd-HHmmss") & "_" & System.IO.Path.GetFileName(dataFolder.TrimEnd("/"c, "\\"c)) & "_" & Guid.NewGuid().ToString("N").Substring(0, 4) & "_" & If(ethical, "Ethical", "Baseline")', "Run folder name in the bucket (time, data set, random tag)"),
            assign(STR, "outDir", 'System.IO.Path.Combine(System.IO.Path.GetTempPath(), "EthicalAudit", out_RunFolder)',
                   "Working-paper folder"),
            log('"Starting ethical RPA audit run in " & If(ethical, "Ethical", "Baseline") & " mode"', name="Log start"),
        ])),
        ("Load", IV("Stage1_LoadData.xaml", {
            "in_DataFolder": ("in", STR, "dataFolder"), "out_Companies": ("out", DT, "dtCompanies"),
            "out_Ledger": ("out", DT, "dtLedger"), "out_Documents": ("out", DT, "dtDocs"),
            "out_Truth": ("out", DT, "dtTruth"), "out_VendorMaster": ("out", DT, "dtVendors")}, "1. Load organization and data")),
        "DECISION",
        "XGATE",
        ("Extract", IV("ExtractInvoices.cs", {
            "invoiceFolder": ("in", STR, 'dataFolder & "/invoices"'), "documents": ("io", DT, "dtDocs"),
            "companies": ("in", DT, "dtCompanies"), "vendorMaster": ("in", DT, "dtVendors"),
            "extracted": ("out", INT, "out_PdfExtracted"), "unreadable": ("out", INT, "out_PdfUnreadable"),
            "extractionAccuracyPct": ("out", DBL, "out_ExtractionAccuracyPct")},
            "1b. Extract invoice fields from the PDFs (script block)")),
        ("Plan", IV("PlanAudit.cs", {
            "companies": ("in", DT, "dtCompanies"), "ledger": ("in", DT, "dtLedger"),
            "Output": ("out", DT, "dtPlanning")}, "2. Plan: materiality and risk (script block)")),
        ("Redact", IV("RedactSensitiveData.cs", {
            "documents": ("in", DT, "dtDocs"), "redact": ("in", BOOL, "ethical"),
            "Output": ("out", DT, "dtDocs")}, "3. Redact before persistence (script block)")),
        ("Reconcile", IV("Stage3_ReconcileCompanies.xaml", {
            "in_Ethical": ("in", BOOL, "ethical"), "in_Companies": ("in", DT, "dtCompanies"),
            "in_Ledger": ("in", DT, "dtLedger"), "in_Documents": ("in", DT, "dtDocs"),
            "out_Results": ("out", DT, "dtResults")}, "4. Reconcile each company")),
        ("Intercompany", IV("Stage4_Intercompany.xaml", {
            "in_Ethical": ("in", BOOL, "ethical"), "in_Companies": ("in", DT, "dtCompanies"),
            "in_Ledger": ("in", DT, "dtLedger"), "io_Results": ("io", DT, "dtResults")}, "5. Match intercompany transactions")),
        ("Tests", IV("Stage5_AuditTests.xaml", {
            "in_Ethical": ("in", BOOL, "ethical"), "in_Companies": ("in", DT, "dtCompanies"),
            "in_Ledger": ("in", DT, "dtLedger"), "in_Documents": ("in", DT, "dtDocs"),
            "io_Results": ("io", DT, "dtResults"), "out_Duplicates": ("out", INT, "duplicates"),
            "out_Orphans": ("out", DT, "dtOrphans")}, "6. Substantive tests: duplicates + completeness")),
        ("Journal", IV("TestJournalEntries.cs", {
            "dataFolder": ("in", STR, "dataFolder"), "companies": ("in", DT, "dtCompanies"), "ethical": ("in", BOOL, "ethical"),
            "flags": ("out", DT, "dtJournal"), "summary": ("out", STR, "jvSummary")},
            "6b. Journal-entry test: weekend, holiday, night, wording, round and just-below-limit (script block)")),
        ("Revenue", IV("TestRevenueCutOff.cs", {
            "dataFolder": ("in", STR, "dataFolder"), "companies": ("in", DT, "dtCompanies"), "ethical": ("in", BOOL, "ethical"),
            "flags": ("out", DT, "dtRevenue"), "summary": ("out", STR, "rvSummary")},
            "6c. Revenue test: year-end cut-off and credit notes after year-end (script block)")),
        ("Findings", IV("BuildFindings.cs", {
            "results": ("in", DT, "dtResults"), "orphans": ("in", DT, "dtOrphans"), "planning": ("in", DT, "dtPlanning"),
            "journalFlags": ("in", DT, "dtJournal"), "revenueFlags": ("in", DT, "dtRevenue"),
            "Output": ("out", DT, "dtFindings")}, "7. Findings register (script block)")),
        ("Trail", IV("Stage6_AuditTrail.xaml", {
            "in_Companies": ("in", DT, "dtCompanies"), "in_Results": ("in", DT, "dtResults"),
            "out_Chain": ("out", DT, "dtChain"), "out_OrgAnchor": ("out", STR, "orgAnchor")}, "8. Audit trail hash chain")),
        ("Report", IV("BuildAuditReport.cs", {
            "planning": ("in", DT, "dtPlanning"), "results": ("in", DT, "dtResults"), "findings": ("in", DT, "dtFindings"),
            "report": ("out", DT, "dtReport"), "conclusion": ("out", STR, "out_Conclusion")},
            "9. Summary of audit differences (script block)")),
        ("Review", IV("Stage10_ReviewTasks.xaml", {
            "in_Ethical": ("in", BOOL, "ethical"), "in_Grouping": ("in", STR, "in_ReviewGrouping"),
            "in_Findings": ("in", DT, "dtFindings"), "in_Results": ("in", DT, "dtResults"),
            "in_Companies": ("in", DT, "dtCompanies"), "out_ReviewTasks": ("out", DT, "dtReviewTasks"),
            "out_TasksCreated": ("out", INT, "out_TasksCreated")},
            "10. Raise review tasks in Action Center (no waiting)")),
        ("Metrics", IV("Stage7_Metrics.xaml", {
            "in_Results": ("in", DT, "dtResults"), "in_Truth": ("in", DT, "dtTruth"), "in_Chain": ("in", DT, "dtChain"),
            "in_Findings": ("in", DT, "dtFindings"), "in_Orphans": ("in", DT, "dtOrphans"),
            "in_Mode": ("in", STR, 'If(ethical, "Ethical", "Baseline")'), "in_Conclusion": ("in", STR, "out_Conclusion"),
            "in_JvSummary": ("in", STR, "jvSummary"), "in_RvSummary": ("in", STR, "rvSummary"),
            "out_Committed": ("out", INT, "out_Committed"), "out_Routed": ("out", INT, "out_Routed"),
            "out_FalseCommits": ("out", INT, "out_FalseCommits"), "out_FalseRoutes": ("out", INT, "falseRoutes"),
            "out_AccuracyPct": ("out", DBL, "out_AccuracyPct"), "out_LeakHits": ("out", INT, "out_LeakHits"),
            "out_ChainOk": ("out", BOOL, "out_ChainOk"), "out_Summary": ("out", STR, "out_Summary")},
            "11. Benchmark metrics, leakage scan, chain check")),
        ("Write", IV("Stage8_WriteWorkingPapers.xaml", {
            "in_OutDir": ("in", STR, "outDir"), "in_Planning": ("in", DT, "dtPlanning"), "in_Results": ("in", DT, "dtResults"),
            "in_Findings": ("in", DT, "dtFindings"), "in_Chain": ("in", DT, "dtChain"), "in_Report": ("in", DT, "dtReport"),
            "in_ReviewTasks": ("in", DT, "dtReviewTasks")},
            "12. Write the working papers")),
        ("Store", IV("Stage9_StoreWorkingPapers.xaml", {
            "in_OutDir": ("in", STR, "outDir"), "in_RunFolder": ("in", STR, "out_RunFolder"),
            "out_Stored": ("out", BOOL, "out_PapersStored")}, "13. Retain working papers in storage bucket")),
        ("NoData", log('"No ledger rows found - nothing to audit"', "Warn", "No data")),
    ]
    names = ["Initialise", "Load", "DECISION", "XGATE", "Extract", "Plan", "Redact", "Reconcile", "Intercompany", "Tests", "Journal", "Revenue", "Findings",
             "Trail", "Report", "Review", "Metrics", "Write", "Store"]
    decisions = {
        "DECISION": ("Any ledger rows?", "dtLedger.Rows.Count &gt; 0", "XGATE", "NoData"),
        "XGATE": ("Read invoices from PDFs?", "String.Equals(in_ExtractionMode, &quot;PDF&quot;, StringComparison.OrdinalIgnoreCase)", "Extract", "Plan"),
    }
    ref = {n: f"__ReferenceID{i}" for i, n in enumerate(names)}
    ref["NoData"] = f"__ReferenceID{len(names)}"
    pos = {}
    y = 130
    for n in names:
        pos[n] = (330 if n in decisions else 300, y)
        y += 100 if n in decisions else 110
    pos["NoData"] = (620, pos["DECISION"][1] - 5)
    nxt = {names[i]: names[i + 1] for i in range(len(names) - 1)}
    stepmap = dict((s[0], s[1]) for s in steps if s not in decisions)
    nodes = ""
    for n in names + ["NoData"]:
        x, yy = pos[n]
        if n in decisions:
            label, cond, t, f = decisions[n]
            nodes += (f'<FlowDecision x:Name="{ref[n]}" DisplayName="{label}">'
                      f'<sap:WorkflowViewStateService.ViewState><scg:Dictionary x:TypeArguments="x:String, x:Object">'
                      f'<av:Point x:Key="ShapeLocation">{x},{yy}</av:Point><av:Size x:Key="ShapeSize">60,60</av:Size>'
                      f'</scg:Dictionary></sap:WorkflowViewStateService.ViewState>'
                      f'<FlowDecision.Condition><mva:VisualBasicValue x:TypeArguments="x:Boolean" '
                      f'ExpressionText="{cond}" /></FlowDecision.Condition>'
                      f'<FlowDecision.True><x:Reference>{ref[t]}</x:Reference></FlowDecision.True>'
                      f'<FlowDecision.False><x:Reference>{ref[f]}</x:Reference></FlowDecision.False>'
                      f'</FlowDecision>')
            continue
        nx = f'<FlowStep.Next><x:Reference>{ref[nxt[n]]}</x:Reference></FlowStep.Next>' if n in nxt else ""
        nodes += (f'<FlowStep x:Name="{ref[n]}"><sap:WorkflowViewStateService.ViewState>'
                  f'<scg:Dictionary x:TypeArguments="x:String, x:Object"><av:Point x:Key="ShapeLocation">{x},{yy}</av:Point>'
                  f'<av:Size x:Key="ShapeSize">260,60</av:Size></scg:Dictionary></sap:WorkflowViewStateService.ViewState>'
                  f'{stepmap[n]}{nx}</FlowStep>')
    height = y + 100
    fc = (f'<Flowchart DisplayName="Ethical RPA for Financial Auditing" sap:VirtualizedContainerService.HintSize="900,{height}">'
          f'<sap:WorkflowViewStateService.ViewState><scg:Dictionary x:TypeArguments="x:String, x:Object">'
          f'<x:Boolean x:Key="IsExpanded">True</x:Boolean><av:Point x:Key="ShapeLocation">400,30</av:Point>'
          f'<av:Size x:Key="ShapeSize">60,75</av:Size><x:Double x:Key="Width">900</x:Double><x:Double x:Key="Height">{height}</x:Double>'
          f'</scg:Dictionary></sap:WorkflowViewStateService.ViewState>'
          f'<Flowchart.Variables>{"".join(wvars)}</Flowchart.Variables>'
          f'<Flowchart.StartNode><x:Reference>{ref["Initialise"]}</x:Reference></Flowchart.StartNode>{nodes}</Flowchart>')
    write_workflow("Main.xaml", args, fc)


if __name__ == "__main__":
    for fn in (stage1, stage3, stage4, stage5, stage6, stage7, stage8, stage9, stage10, main_flow):
        fn()
    print("written to", OUT)
