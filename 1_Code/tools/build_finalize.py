"""Generates the 'finalize review' workflow (run 2) for the EthicalAuditFinalize project.

Run:  python -I tools/build_finalize.py
Reads the findings register and the review-form list that run 1 left in the storage bucket, asks Action Center for each
form's outcome (Approve or Reject plus the reviewer's comment), signs off the findings that each form covers, and
uploads the signed-off register and an outcomes file.
"""
import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("bx", HERE / "build_xaml.py")
bx = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bx)
bx.OUT = HERE.parent / "EthicalAuditSolution" / "EthicalAuditFinalize"

STR, INT, BOOL, DT, ROW = bx.STR, bx.INT, bx.BOOL, bx.DT, bx.ROW
assign, log, seq, if_, foreach, var, esc = bx.assign, bx.log, bx.seq, bx.if_, bx.foreach, bx.var, bx.esc
BUCKET = "EthicalAudit-WorkingPapers"

# VB expression pieces kept as plain strings so no shell or escape layers touch them
FILTER_EXPR = ('"1 = 1" & If(coId = "ALL", "", " AND CompanyId = \'" & coId & "\'") '
               '& If(oc = "MIXED", "", " AND Outcome = \'" & oc & "\'")')
COMMENT_PATTERN = '"Comment"\\s*:\\s*"((?:[^"\\\\]|\\\\.)*)"'
COMMENT_EXPR = ("System.Text.RegularExpressions.Regex.Match(Newtonsoft.Json.JsonConvert.SerializeObject(taskInfo.Data), "
                + bx.vb_str(COMMENT_PATTERN) + ", System.Text.RegularExpressions.RegexOptions.IgnoreCase).Groups(1).Value")


def download(bucket_path_expr, local_expr, name):
    return (f'<ucas:DownloadStorageFile DisplayName="{esc(name)}" StorageBucketName="{BUCKET}" '
            f'Path="[{esc(bucket_path_expr)}]" Destination="[{esc(local_expr)}]" />')


def upload(local_expr, dest_expr, name):
    return (f'<ucas:UploadStorageFile DisplayName="{esc(name)}" StorageBucketName="{BUCKET}" '
            f'Path="[{esc(local_expr)}]" Destination="[{esc(dest_expr)}]" />')


def main():
    args = {"in_RunFolder": ("in", STR), "out_Reviewed": ("out", INT), "out_Pending": ("out", INT),
            "out_Rejected": ("out", INT), "out_Summary": ("out", STR), "out_AfterReview": ("out", STR),
            "out_Completion": ("out", STR)}
    paper = 'tmpDir & "/3_findings_register.csv"'
    tasks_file = 'tmpDir & "/6_review_tasks.csv"'
    signed = 'tmpDir & "/3_findings_register_signed.csv"'
    outcomes_file = 'tmpDir & "/7_review_outcomes.csv"'
    plan_file = 'tmpDir & "/1_audit_plan.csv"'
    report_file = 'tmpDir & "/4_audit_report.csv"'
    after_file = 'tmpDir & "/8_audit_report_after_review.csv"'
    chain_file = 'tmpDir & "/5_audit_trail_hash_chain.csv"'
    summary_file = 'tmpDir & "/9_audit_completion_summary.html"'

    mark = foreach(ROW, "dtFindings.Select(flt)", "f", [
        assign("x:Object", 'f("Reviewer")', "reviewer", "Reviewer"),
        assign("x:Object", 'f("ReviewerSignOff")', 'completedAt & " " & action', "Sign-off time and action"),
        assign("x:Object", 'f("ReviewerComment")', "comment", "Reviewer comment"),
        assign("x:Object", 'f("Status")',
               'If(action.StartsWith("Reject"), "Rejected - needs rework", "Reviewed - " & If(action = "", "Completed", action))',
               "Status"),
    ], "Record sign-off on each finding this form covers")

    per_task = [
        assign(STR, "coId", 'trow("CompanyId").ToString', "Company (ALL = whole organization)"),
        assign(STR, "oc", 'trow("Outcome").ToString', "Problem type (MIXED = all types)"),
        assign(STR, "flt", FILTER_EXPR, "Which findings this form covers"),
        assign("x:Int64", "taskId", 'Long.Parse(trow("TaskId").ToString)', "Task id"),
        '<upat:GetTaskData DisplayName="Get the form outcome from Action Center" TaskId="[taskId]" TaskOutput="[taskInfo]" />',
        assign(STR, "status", "taskInfo.Status.ToString", "Task status"),
        assign(STR, "action", 'If(taskInfo.Action Is Nothing, "", taskInfo.Action.ToString)', "Button the reviewer pressed"),
        assign(STR, "completedAt",
               "Convert.ToString(taskInfo.LastModificationTime, System.Globalization.CultureInfo.InvariantCulture)", "When it changed"),
        assign(STR, "comment", COMMENT_EXPR, "Reviewer comment typed on the form"),
        assign(STR, "reviewer",
               'If(taskInfo.AssignedToUser Is Nothing, "Action Center reviewer", taskInfo.AssignedToUser.EmailAddress)', "Reviewer"),
        if_('status = "Completed"', [
            mark,
            assign(INT, "out_Reviewed", 'out_Reviewed + If(action.StartsWith("Reject"), 0, 1)', "Count approved forms"),
            assign(INT, "out_Rejected", 'out_Rejected + If(action.StartsWith("Reject"), 1, 0)', "Count rejected forms"),
        ], [
            assign(INT, "out_Pending", "out_Pending + 1", "Count pending forms"),
        ], "If the reviewer has completed the form"),
        bx.add_row("dtOutcomes", ["coId", "oc", "taskId.ToString", "status", "action", "reviewer", "completedAt", "comment"],
                   "Record the outcome"),
        log('coId & " / " & oc & ": form " & taskId & " is " & status & If(action = "", "", " (" & action & ")")',
            name="Log outcome"),
    ]
    body = seq("Finalize review - read Action Center outcomes and sign off the findings", [
        if_("String.IsNullOrWhiteSpace(in_RunFolder)", [
            '<Throw DisplayName="Run folder is required"><Throw.Exception><InArgument x:TypeArguments="s:Exception">'
            '<VisualBasicValue x:TypeArguments="s:Exception" ExpressionText="New ArgumentException(&quot;in_RunFolder is required, '
            'for example 20261010-083217_Ethical&quot;)" /></InArgument></Throw.Exception></Throw>',
        ], None, "Check the run folder was supplied"),
        assign(STR, "runFolder", "in_RunFolder.Trim()", "Run folder without stray spaces"),
        assign(STR, "tmpDir",
               'System.IO.Path.Combine(System.IO.Path.GetTempPath(), "EthicalAuditFinalize", runFolder)', "Working folder"),
        '<ui:CreateDirectory DisplayName="Create working folder" Path="[tmpDir]" />',
        assign(INT, "out_Reviewed", "0"), assign(INT, "out_Pending", "0"), assign(INT, "out_Rejected", "0"),
        download('runFolder & "/3_findings_register.csv"', paper, "Download the findings register from the bucket"),
        download('runFolder & "/6_review_tasks.csv"', tasks_file, "Download the review-form list from the bucket"),
        bx.read_csv(paper, "dtFindings", "Read findings register"),
        bx.read_csv(tasks_file, "dtTasks", "Read review forms"),
        bx.new_table("dtOutcomes", "CompanyId,Outcome,TaskId,Status,Action,Reviewer,CompletedAt,Comment", "Create outcomes table"),
        foreach(ROW, "dtTasks.Rows", "trow", per_task, "For each review form",
                [var(STR, "coId"), var(STR, "oc"), var(STR, "flt"), var(STR, "comment"), var("x:Int64", "taskId"),
                 var("upmt:TaskData", "taskInfo"), var(STR, "status"), var(STR, "action"), var(STR, "completedAt"),
                 var(STR, "reviewer")]),
        download('runFolder & "/1_audit_plan.csv"', plan_file, "Download the audit plan from the bucket"),
        download('runFolder & "/4_audit_report.csv"', report_file, "Download the original audit report from the bucket"),
        bx.read_csv(plan_file, "dtPlan", "Read the audit plan"),
        bx.read_csv(report_file, "dtReportBefore", "Read the original audit report"),
        bx.invoke("BuildPostReviewReport.cs", {
            "findings": ("in", DT, "dtFindings"), "planning": ("in", DT, "dtPlan"),
            "originalReport": ("in", DT, "dtReportBefore"), "report": ("out", DT, "dtAfter"),
            "conclusion": ("out", STR, "out_AfterReview")}, "Script block: recalculate the audit summary after review"),
        bx.write_csv(after_file, "dtAfter", "Write the after-review audit summary"),
        download('runFolder & "/5_audit_trail_hash_chain.csv"', chain_file, "Download the audit trail from the bucket"),
        bx.read_csv(chain_file, "dtChain", "Read the audit trail"),
        bx.invoke("BuildCompletionSummary.cs", {
            "runFolder": ("in", STR, "runFolder"), "outputPath": ("in", STR, summary_file),
            "findings": ("in", DT, "dtFindings"), "planning": ("in", DT, "dtPlan"),
            "reportBefore": ("in", DT, "dtReportBefore"), "reportAfter": ("in", DT, "dtAfter"),
            "outcomes": ("in", DT, "dtOutcomes"), "chain": ("in", DT, "dtChain"),
            "status": ("out", STR, "out_Completion"), "chainOk": ("out", BOOL, "chainVerified"),
            "orgHash": ("out", STR, "orgHash")}, "Script block: write the audit completion summary"),
        bx.write_csv(signed, "dtFindings", "Write the signed-off findings register"),
        bx.write_csv(outcomes_file, "dtOutcomes", "Write the review outcomes"),
        upload(signed, 'runFolder & "/"', "Upload the signed-off register"),
        upload(outcomes_file, 'runFolder & "/"', "Upload the review outcomes"),
        upload(after_file, 'runFolder & "/"', "Upload the after-review audit summary"),
        upload(summary_file, 'runFolder & "/"', "Upload the audit completion summary"),
        assign(STR, "out_Summary",
               '"Run " & runFolder & ": forms approved=" & out_Reviewed & ", pending=" & out_Pending & ", rejected=" & out_Rejected '
               '& ", conclusion after review: " & out_AfterReview & ". Completion: " & out_Completion '
               '& ". Files uploaded to bucket ' + BUCKET + '"',
               "Build summary"),
        log("out_Summary", name="Log summary"),
    ], [var(STR, "runFolder"), var(STR, "tmpDir"), var(DT, "dtFindings"), var(DT, "dtTasks"), var(DT, "dtOutcomes"),
        var(DT, "dtPlan"), var(DT, "dtReportBefore"), var(DT, "dtAfter"), var(DT, "dtChain"),
        var(BOOL, "chainVerified"), var(STR, "orgHash")])
    bx.write_workflow("Main.xaml", args, body)
    print("written to", bx.OUT)


if __name__ == "__main__":
    main()
