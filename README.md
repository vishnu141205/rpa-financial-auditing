# Ethical RPA for Financial Auditing

A UiPath Cloud solution that checks a company's payments, journal entries and sales against their supporting
documents, hides personal data before it works, and sends everything it cannot decide to a human reviewer in
Action Center. It handles a group of companies under one organization (four subsidiaries).

## Files in this package

```
README.md                         this file
1_Code/                           the source files
2_Sample_Data/                    sample input and output files
```

### 1_Code: the source

**EthicalAuditSolution.uipx** is the solution file. The solution has two processes and one storage bucket.

**EthicalAuditFlow** (process 1) tests the data and creates the review forms.

| File | What it does |
|---|---|
| `Main.xaml` | The main workflow. It runs the stages below in order and returns the results of the run |
| `Stage1_LoadData.xaml` | Reads the companies, ledger, extracted invoices and vendor list |
| `Stage3_ReconcileCompanies.xaml` | Reconciles the ledger payments of each company |
| `Stage4_Intercompany.xaml` | Matches transactions between companies of the same group |
| `Stage5_AuditTests.xaml` | Runs the missing-invoice and duplicate-payment tests |
| `Stage6_AuditTrail.xaml` | Builds the audit trail and its hash chain |
| `Stage7_Metrics.xaml` | Works out accuracy and the other run figures |
| `Stage8_WriteWorkingPapers.xaml` | Writes the result files |
| `Stage9_StoreWorkingPapers.xaml` | Uploads the result files to the storage bucket |
| `Stage10_ReviewTasks.xaml` | Creates the review forms in Action Center |
| `ExtractInvoices.cs` | Reads supplier, amount and date from the invoice PDFs |
| `PlanAudit.cs` | Sets materiality and the testing thresholds for each company |
| `RedactionEngine.cs`, `RedactSensitiveData.cs` | Replace emails, phone numbers, IBANs, card and tax numbers with placeholders |
| `ReconcileCompany.cs` | Matches each ledger payment to its invoice and compares the amounts |
| `TestCompleteness.cs` | Finds invoices that have no ledger payment |
| `TestDuplicates.cs` | Finds payments that look like duplicates |
| `TestJournalEntries.cs` | Journal-entry testing: weekend, holiday and night postings, risky wording, round and just-below-limit amounts |
| `TestRevenueCutOff.cs` | Revenue cut-off and credit-note testing |
| `BuildFindings.cs` | Combines every result into one findings list with severity |
| `BuildAuditReport.cs` | Builds the audit report for each company and the group |
| `BuildReviewGroups.cs` | Groups the findings into review forms |
| `AppendAuditChain.cs` | Adds an entry to the hash chain |
| `Calc.cs` | Shared helper functions |
| `project.json`, `project.uiproj`, `entry-points.json` | Project settings, dependencies and the process's input and output arguments |

**EthicalAuditFinalize** (process 2) reads the reviewers' decisions and writes the final report.

| File | What it does |
|---|---|
| `Main.xaml` | Reads each form's decision from Action Center, signs off the findings and uploads the files |
| `BuildPostReviewReport.cs` | Recalculates the outstanding amounts and the conclusion after the review |
| `BuildCompletionSummary.cs` | Builds the readable completion summary |
| `project.json`, `project.uiproj`, `entry-points.json` | Project settings and arguments |

**resources/** holds the definitions of the storage bucket `EthicalAudit-WorkingPapers` and of the two processes.

**tools/** are Python scripts that generate the sample data and build the workflow files.

| File | What it does |
|---|---|
| `generate_dataset.py` | Group ledger, extracted invoice data, answer key and organization settings |
| `make_invoices.py` | The invoice PDFs, the vendor list and the document manifest |
| `generate_standalone.py` | A second data set for one standalone company |
| `generate_journal.py` | Journal entries, journal settings, holidays and answer key |
| `generate_sales.py` | Sales invoices, credit notes, year-end settings and answer key |
| `build_xaml.py` | Generates the EthicalAuditFlow workflow files (`Main.xaml` and the stages) |
| `build_finalize.py` | Generates the EthicalAuditFinalize workflow file |

### 2_Sample_Data: input and output

**input/group_data/** is the group data set: organization ORG-001 with four companies (US, UK, DE, IN).

| File | What it holds |
|---|---|
| `companies.csv` | The companies, their currency, risk level and tolerances |
| `ledger.csv` | 500 payments made to suppliers |
| `documents.csv` | The data read from each invoice, including the raw text |
| `du_batch.csv` | The list of invoice PDFs and what each should contain |
| `vendor_master.csv` | The approved suppliers of each company |
| `invoices/` | 461 invoice PDFs, named by transaction ID |
| `journal.csv` | Journal entries: 240 manual and 80 system entries |
| `jv_config.csv` | Approval limit, night hours and round-number rule for each company |
| `holidays.csv` | Public holidays for each company |
| `sales.csv` | Sales invoices and credit notes |
| `fiscal_config.csv` | Year-end, cut-off days, credit-note window and credit threshold for each company |

**output/group_run_20261019-134051_Ethical/** holds the files the latest group run left in the storage bucket,
before the human review. This run includes the journal and revenue tests.

| File | What it holds |
|---|---|
| `1_audit_plan.csv` | Materiality and testing thresholds for each company |
| `2_reconciliation_results.csv` | The outcome for every ledger payment |
| `3_findings_register.csv` | Every finding, with severity and redacted evidence (284 findings) |
| `4_audit_report.csv` | The summary for each company and the group, with the first conclusion |
| `5_audit_trail_hash_chain.csv` | The audit trail, each entry chained to the one before |
| `6_review_tasks.csv` | The 40 review forms that were created |

**output/output_after_review/** holds the files a human review left behind. They come from an earlier group run
(`20261011-124648`) that was made before the journal and revenue tests were added, so it has 124 findings and
seven problem types. It shows what the review step produces.

| File | What it holds |
|---|---|
| `3_findings_register_signed.csv` | The findings register with each finding approved or rejected |
| `6_review_tasks.csv` | The review forms of that run |
| `7_review_outcomes.csv` | Each form's decision, reviewer, time and comment |
| `8_audit_report_after_review.csv` | The outstanding amounts and the conclusion after review |
| `9_audit_completion_summary.html` | A readable completion summary |

## What it tests

| Test | Input | What it looks for |
|---|---|---|
| Payment reconciliation | `ledger.csv` and the invoice PDFs | Amount differences, unknown suppliers, unreadable invoices, missing invoices, duplicates, invoices with no payment |
| Intercompany matching | `ledger.csv` | Transactions between two group companies that do not agree |
| Journal-entry testing | `journal.csv` | Weekend, holiday and night postings, risky wording, round amounts, amounts just under the approval limit |
| Revenue cut-off | `sales.csv` | Sales recorded in a different year from the shipment, or with no shipping record |
| Credit notes | `sales.csv` | Large credit notes after year-end, and credit notes that cancel a year-end sale |

Personal data is replaced with placeholders before any result is stored or shown to a reviewer. A hash chain over
the audit trail makes later edits detectable.

## What to install

| Needed | Why | Notes |
|---|---|---|
| UiPath Automation Cloud account | Runs the processes, holds the review forms and the result files | Needs Orchestrator, serverless robots, Action Center and storage buckets |
| Node.js and the UiPath CLI | Packs, publishes, deploys and runs the solution | `npm install -g @uipath/cli` (built with 1.203 to 1.204). The CLI installs its tool packages the first time you use them |
| Python 3.10 or later (optional) | Only to regenerate the sample data or rebuild the workflow files | `pip install pillow reportlab` |
| UiPath Studio 2026.0 (optional) | Only to look at the workflows as diagrams | The project targets Studio 26.0.203.0 (Portable) |

## How to run it

The checks run in UiPath Cloud. The review step needs Action Center and the storage step needs a bucket, so a
complete run cannot be done on a laptop alone.

1. **Sign in.**

   ```
   uip login
   ```

2. **Add the data, then pack, publish and deploy.** The processes read their data from a folder inside the
   EthicalAuditFlow project, so copy the sample data in first. From the `1_Code/EthicalAuditSolution` folder:

   ```
   cp -r ../../2_Sample_Data/input/group_data EthicalAuditFlow/data
   uip solution pack . ./out -v 1.0.0
   uip solution publish ./out/EthicalAuditSolution_1.0.0.zip
   uip solution deploy run --name EthicalAuditPDF --package-name EthicalAuditSolution --package-version 1.0.0 --folder-name EthicalAuditPDF --parent-folder-path Shared
   ```

   On Windows PowerShell use `Copy-Item -Recurse` in place of `cp -r`. Packing downloads the activity packages, so
   it takes a couple of minutes. The payment step also reads `ground_truth.csv` (the answer key) from the data
   folder. It is not in `input/group_data`, so create it with `tools/generate_dataset.py` or add your own before
   you run.

3. **Find the process keys.**

   ```
   uip or processes list --folder-path Shared/EthicalAuditPDF
   ```

4. **Start process 1, EthicalAuditFlow.** `in_DataFolder` is the folder name inside the project (`data`).
   `in_Mode` is `Ethical` (all protections on) or `Baseline` (the comparison run without them).

   ```
   uip or jobs start <EthicalAuditFlow-key> --folder-path Shared/EthicalAuditPDF --runtime-type Serverless --input-arguments '{"in_DataFolder":"data","in_Mode":"Ethical","in_ExtractionMode":"PDF"}'
   ```

   When the job finishes, read its output. `out_RunFolder` names the folder in the bucket that holds this run's
   files, and `out_Summary` gives the accuracy and test figures.

5. **Review.** In Action Center, open the Tasks list. Each form groups similar findings. Read the evidence and choose
   Approve (the explanation is supported) or Reject (it needs follow-up).

6. **Start process 2, EthicalAuditFinalize,** with the run folder from step 4.

   ```
   uip or jobs start <EthicalAuditFinalize-key> --folder-path Shared/EthicalAuditPDF --runtime-type Serverless --input-arguments '{"in_RunFolder":"<out_RunFolder>"}'
   ```

7. **Read the results.** They are in the bucket `EthicalAudit-WorkingPapers`, in the run folder. To download:

   ```
   uip or buckets list --folder-path Shared/EthicalAuditPDF
   uip or bucket-files list <bucket-key> --folder-path Shared/EthicalAuditPDF --prefix <out_RunFolder>
   uip or bucket-files download <bucket-key> "<run folder>/8_audit_report_after_review.csv" --folder-path Shared/EthicalAuditPDF --destination 8_audit_report_after_review.csv
   ```

## Result from the sample run

| Run | Payments | Committed / routed | Accuracy | Findings | Review forms |
|---|---|---|---|---|---|
| Group (4 companies), Ethical | 500 | 382 / 118 | 100% | 284 | 40 |

The journal test examined 240 manual entries and flagged 116, and the revenue test examined 92 documents and
flagged 44. Both matched the answer keys exactly, with no false flags.

## Regenerating the data and the workflows (optional)

Run these from the `1_Code` folder. The scripts are seeded, so they produce the same data each time.

```
python tools/generate_dataset.py       # group ledger, documents, answer key and organization settings
python tools/make_invoices.py          # the invoice PDFs, vendor master, document manifest
python tools/generate_standalone.py    # a second, standalone-company data set (one company, no intercompany)
python tools/generate_journal.py       # journal entries, settings, holidays, answer key
python tools/generate_sales.py         # sales invoices, credit notes, year-end settings, answer key
python -I tools/build_xaml.py          # rebuilds EthicalAuditFlow workflow files
python -I tools/build_finalize.py      # rebuilds EthicalAuditFinalize workflow file
```

`Main.xaml` and the other workflow files are generated. Change the scripts and rebuild, rather than editing the
XAML by hand.

## Limits

- It is not a full audit. It covers payments, journal entries, revenue cut-off and credit notes.
- Invoice reading is a stand-in for UiPath Document Understanding.
- The data is synthetic. The answer keys come from a separate copy of the same rules, so a 100% score shows the
  rules are applied correctly, not that they would catch every real irregularity.
- A flag is a warning sign for a reviewer, not proof of an error.
