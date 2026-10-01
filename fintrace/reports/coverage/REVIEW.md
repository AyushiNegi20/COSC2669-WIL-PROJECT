# Coverage follow-up, 27 September 2026

## Finding

FinTrace already had extractable text from all six source PDFs: 1,021 pages,
including all 265 pages of the NAB FY2025 Annual Report. Missing answers did not
establish that those reports were absent. The separate numerical binder covered
selected validated tables; routing and paragraph selection also caused misses.

This change treats numerical validation scope and document-reading scope
separately. Broader report questions can retrieve cited passages. They are not
refused merely because a measure is outside the original thirteen-metric list.
This is not permission to calculate from unvalidated table text.

## Changes

- Added source-derived NAB statutory performance rows, basic/diluted statutory
  EPS, Group underlying profit and two reconciliation paths. No expected answer
  values or evaluation keys are imported into runtime code.
- Two PDF extractors must agree on headers, years and values. Five statement
  identities, segment sums and cash-to-statutory identities must reconcile.
- Repaired prose continuing across NAB PDF blocks/columns, preserving component
  source IDs. The new v3 cache has 7,780 prose blocks. The old cache is retained.
- Kept numerical change questions on Python arithmetic, including basis-point
  output. Explanation questions keep the requested subject rather than becoming
  generic profit summaries.
- Kept explanations of a checked movement within its source reports and basis.
  Report-version questions search the explicitly named report vintage.
- Kept company, period, privacy, prediction and incompatible-scope safeguards.

## Preserved runs and corrections

Raw responses remain locally under `reports/runs/`; generated corpora and large
run files are not part of the Git repository. No response was replaced by a
more favourable retry.

1. `coverage-20260926T215358Z`: 25 existing NAB question texts plus eight extra
   cases, with no UI scope filters. Integrity matched before and after.
2. `coverage-20260926T220657Z`: the same questions after additional fixes, with
   NAB/FY2025 UI filters for the 25 NAB cases. Explicit question scope overrides
   those filters. Integrity matched before and after; all 33 requests completed.
   This scope change means the two runs are not a controlled accuracy comparison.
3. `coverage-http-20260926T221826Z`: actual local HTTP requests. Found a remaining
   statutory-expense premise-routing failure. The failure and all nine responses
   are preserved. It is not counted as a successful smoke run.
4. `coverage-http-20260926T222121Z`: final HTTP follow-up, nine questions plus
   frontend asset, health and source-PDF requests. Checks passed and integrity
   matched before and after. EPS, impairment source consistency, basis points,
   labelled profit alternatives, investment, expense drivers, reconciliation,
   underlying profit and future-period refusal were exercised.

Review found and corrected an EPS phrase being mistaken for statutory NPAT,
and an impairment response combining a cash-basis calculation with a statutory
explanation. A later HTTP check caught the new statutory tables not being used
when checking an explanation's assumed direction. Regression tests now exercise
the entry points, not just the underlying parsers.

Source review included the annual-report financial-performance and EPS tables,
Note 2 segment/reconciliation tables, expense and impairment commentary, the
software policy and the restatement paragraph. These are developer-reviewed,
exposed examples, not an independent held-out quality score.

## Maintained checks

- 570 Python regression tests passed, including 18 new tests. No existing
  assertions were weakened or removed.
- 10 frontend model/scope tests passed. This is not a visual browser walkthrough.
- The final HTTP run passed the nine exposed regression checks above and served
  the original NAB source PDF successfully. The temporary test server shut down.
- Code/data integrity matched. This verifies artifact consistency, not accuracy.
- 232 supported numerical wording checks passed in
  `wording-20260926T222242Z`, with matching integrity before and after. They
  compare financial outputs against canonical requests, not a new gold answer
  set. Historical unsupported-measure controls were explicitly excluded using
  `--families-only`; some of those measures now have validated source paths.

The HTTP review confirmed that the impairment explanation now uses the same
cash-basis report as its checked movement. The statutory operating-expense
explanation uses the statutory annual-report comparison instead.

## Remaining limitations

- NAB Note 6 Group-versus-parent income tax and parent-company net interest
  income still lack validated table bindings. The system gives an evidence-limit
  response, not a neighbouring Group number. They are real coverage limitations.
- Broad software-amortisation wording retrieved related commentary rather than
  the most useful accounting-policy paragraph. The more specific useful-life
  question retrieved the policy. Retrieval completeness is not guaranteed.
- Explanation output can be quoted passages instead of smooth generated prose.
  Definitions remain model-generated with automated checks. Latency varies.
- Full text does not imply all tables or image-only disclosures are understood.
  Supported numerical paths remain bounded and cross-bank comparison is disabled.
- This work does not demonstrate universal accuracy or remove the need for a
  rehearsal on the actual presentation laptop.

The previous frozen tag remains the rollback reference. Do not replace its
evidence artifacts or claim its independent results apply to this candidate.
