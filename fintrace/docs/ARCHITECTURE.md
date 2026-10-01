# Current architecture

`Start-FinTrace-Demo.ps1` starts `scripts/serve_fintrace_demo.py` with
`config/demo_local8b.json`. There is one supported demo entry point.

The browser sends questions to a loopback-only HTTP server. The conversational
backend resolves bank/year context and selects an answer path:

- Numeric: recognised measure requests use checked source-cell binding and Python
  arithmetic without asking the model to approve the lookup wording. All indexed
  financial rows matching the bank and metric are considered before strict binding.
- Definition: report-specific evidence and checked local-model paraphrasing.
- Narrative: full-report prose retrieval followed by local-model passage selection.
  The displayed text is quoted from the source, not a new causal explanation.

Document reading is broader than the checked numerical catalogue. Requests
outside that catalogue can search the report prose and return directly attributed
evidence rather than being refused just because a measure is not registered.
This does not permit unvalidated calculations or substitution of a nearby KPI.

Additional NAB annual-report tables have a separate, checked path in
`bank_statement_tables.py`: statutory financial-performance rows, basic/diluted
statutory EPS, Group underlying profit, cash-to-statutory reconciliation and
ownership reconciliation. Values are read from the pinned issuer PDFs, not
stored answers. pypdf and PyMuPDF must agree on year columns and rows. Statement
and reconciliation identities are checked in Decimal arithmetic. Parent-company,
segment and note-specific requests are not silently answered with Group totals.

NAB prose cache `library_v3.json` preserves incomplete paragraphs which continue
in the next layout block or column, with the component source IDs. The earlier
cache remains available for the frozen release. Targeted driver questions
preserve their named subject rather than becoming broad performance summaries.
"How did X change?" stays on the numerical path; "Why did X change?" asks for
reported explanations. Percentage-point changes also expose basis points.
For a checked directional premise, narrative retrieval is restricted to the
calculation's source reports and carries its reporting basis. This avoids
combining a cash-basis change with a statutory discussion from another report.

Structured retrieval combines lexical and dense matching. Full-report prose
retrieval uses lexical ranking with source context. These are separate indexes;
do not describe every narrative request as dense or hybrid search.

For numerical answers, the final candidate search is structural rather than
limited to the hybrid top-k passages. The binder still checks the row identity,
native digits, reporting basis, period, scope, report vintage and conflicting
values. Its source citations may therefore include rows outside that top-k list.
Do not report this candidate search as a measured improvement in Hit@5 or MRR.

Common spelling repairs, the CommBank alias and short FY years are recorded in
the response. Unknown financial concepts are not fuzzily mapped to nearby
measures. Mixed numerical/explanation requests preserve both branches; a failed
explanation remains a partial answer even when the numerical answer succeeds.

The PDF pipeline retains table structure, headings, native-text checks and source
metadata. Model-selected quotations do not automatically validate all extracted
numbers or establish that a passage completely answers a question.

`bank_integrity.py` checks the current runtime and local source artifacts. It no
longer needs old model experiments or test-run folders to start the application.
It is an integrity check, not a financial correctness score.

The retained version-named answer, retrieval and HTTP modules form an import
chain used by this demo. Their behaviours were not rewritten during cleanup.
Removing these remaining suffixes requires a separate tested refactor, not file
deletion. Old experimental entry points are not supported launch instructions.
