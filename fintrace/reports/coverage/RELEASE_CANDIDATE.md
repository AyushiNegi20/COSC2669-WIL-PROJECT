# Final demo evaluation candidate, 27 September 2026

This candidate follows `d9c6a5d`. The local annotated tag
`demo-eval-candidate-2026-09-27` identifies the exact commit for read-only
evaluation. The previous frozen demo tag remains untouched.

## Bounded fixes

- Financial subject and entity-scope checks run before prose ranking, source
  selection and fallback display. Capital questions cannot be answered with
  operating expenses; equity returns cannot be replaced with private-equity
  exposure; related-party loans cannot be labelled Group lending.
- Plain money-made questions disclose a profit interpretation and retain cash
  and statutory alternatives. Common dividend wording reaches the checked path.
- A single-year FY2025 movement can explicitly use FY2024 as its comparison;
  Python computes the change. Half-year, future and other-year requests are not
  silently expanded by this rule.
- Only whole, unqualified total-loan lookups can offer the disclosed gross-loans
  measure as a labelled alternative. Named segments, net amounts and related
  parties do not enter that shortcut.
- A later report's comparative column is identified without automatically
  asserting a restatement. No source values are changed by that disclosure.
- Grouped investment categories do not establish a technology-versus-branches
  budget ranking. The answer puts that limitation first and remains partial.

## Evidence from this development round

All runs below use exposed questions. They are regression evidence, not fresh
independent accuracy estimates. Earlier runs and failures remain on disk.

- 584 Python tests passed; existing assertions were not weakened.
- 10 frontend model/scope tests passed.
- `release-20260926T232432Z`: 24 first responses from the actual configured demo
  backend, zero runtime errors, integrity matched before and after.
- `wording-20260926T232619Z`: all 232 supported numerical wording checks passed.
  As documented previously, historical unsupported-measure controls were not
  included in that families-only run.
- `coverage-http-20260926T232747Z`: nine requests passed through the actual HTTP
  handler, along with frontend asset, health and source-PDF checks. Integrity
  matched before and after. The temporary server was shut down.

The 24-question response statuses were 11 source-bound answers, one definition
evidence answer, five partial answers and seven unable-to-verify responses.
These are status counts, not correctness scores. Six of the refusals concern
cross-bank ranking, prediction, an excluded year, another bank, personal advice
or live price. The cost-to-income refusal is an answerable coverage limitation.

The capital-position response now has capital evidence, not operating-expense
commentary. It still gives components rather than a complete capital-strength
assessment. Treat it as incomplete; do not score relevance as completeness.
Cash-basis definitions can include redundant surrounding excerpts. These remain
known limitations, not reasons to keep expanding the project before assessment.

## Answer-key discrepancy checked against the PDF

The exposed D09 expectation used 834,259 million for CBA's FY2024 customer
deposits. Visual inspection of the FY2025 Profit Announcement, PDF page 53
(printed page 33), shows 851,682 million in the 30 June 2024 column and 908,812
million in the 30 June 2025 column. The middle column is 31 December 2024.
The source-backed change is therefore 57,130 million, approximately 6.71%.

Source: `data/raw/CBA_FY2025_profit_announcement.pdf`, SHA256
`e2e911ab4feda08dfa6dde6c20f0915bf3522ea141383b21f3a6a682ca464a3f`.
No original evaluator files or expectations were overwritten. This discrepancy
must be adjudicated from source headers, not used to force a matching answer.

## Assessment handoff

Follow `docs/EVALUATOR_HANDOFF.md`. Use `serve_fintrace_demo.build_backend()` and
preserve the full JSON. A generic backend's defaults differ from the configured
demo. A text adapter that drops `calculations` can incorrectly report that
arithmetic was not performed.

Do not edit this candidate during assessment. Report wrong financial answers,
misleading citations and crashes separately from incomplete coverage and
cosmetic issues. A successful bounded review does not prove universal accuracy.
