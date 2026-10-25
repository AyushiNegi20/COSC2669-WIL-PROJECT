# Historical release assessment: preserved first responses

## Provenance

- Assessed candidate: `aa7fef9b82ade8f13bdfacb448008c69be7aabfe`.
- Run identifier: `release-20260926T233529Z` (UTC identifier; reviewed locally on
  27 September 2026).
- Entry point: `serve_fintrace_demo.build_backend()` through the sanctioned
  runner, with Qwen3 8B and the configuration saved in `results.json`.
- This archive was copied for public report evidence on 25 October 2026.
  It is not a newly executed assessment or an accuracy result for current code.

`001.json` through `024.json` are the unaltered first responses. `results.json`
contains the original run metadata and aggregate, including before/after
integrity checks. `questions.json` and `EVALUATION.md` are the original question
file and AI-assisted companion assessment, preserved without correcting them.
`SHA256SUMS.json` records hashes of those original files.

The original question file names both issuer PDFs and `metric_scope_13` as
reference material. The original review describes separate question authorship,
but that is not equivalent to a fully blind, source-only or independent human
evaluation. Several expected answers needed interpretation or correction. In
particular D09's deposit expectation uses a different comparative value, and
D19/D20 use the word "restated" more strongly than the source establishes.
Do not reuse those expectations as unqualified gold answers.

## Exact reconciliation of the companion review

This is a transcription of its named categories, not a new model run or a new
financial adjudication. It makes the previously approximate coverage explicit.

| Recorded category | Count / 24 | Question IDs |
| --- | ---: | --- |
| Explicitly listed as correct and sufficiently complete | 12 | D01, D02, D03, D04, D08, D09, D10, D11, D12, D14, D19, D23 |
| Partial or limited response | 4 | D05, D07, D13, D15 |
| Over-refusal of an answerable question | 1 | D06 |
| Appropriate non-answer under the declared boundaries | 6 | D16, D17, D18, D21, D22, D24 |
| Discussed as a correct vintage example, but not assigned a completeness category | 1 | D20 |
| Total | 24 | D01-D24 |

The same review recorded zero serious financial errors, zero misleading
citations, zero runtime errors and zero model/excerpt fallbacks. Those are
separate checks, not additional mutually exclusive categories. Historical
"sufficiently complete" judgments use that review's criteria; later review of
generic profit expanded the expected alternatives from two to four. These
counts must not become a current 100% accuracy claim or a fully adjudicated
13/18 score by silently assigning D20 a new category.

The development run `release-20260926T232432Z` is different: it recorded seven
unable-to-verify statuses in 24 responses. Do not combine its 29.2% status rate
with the outcome categories above as though they came from the same run.

Reference answers and assessments remain outside application evidence paths.
