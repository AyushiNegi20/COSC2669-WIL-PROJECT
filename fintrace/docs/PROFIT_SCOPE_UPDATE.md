# General profit lookup update

4 October 2026. This is a developer-regression-tested local update, not a new
independent accuracy assessment. Existing independent results and release tags
have not been relabelled.

## Behaviour

An unqualified numerical profit lookup now shows the available source-bound
cash and statutory profit variants, with operational scope, year, unit and
source page. No choice between accounting bases is required first.

CBA FY2025, in AUD million, from the Profit Announcement, PDF page 18:

| Operational scope | Cash profit | Statutory profit after tax |
| --- | ---: | ---: |
| Continuing operations | 10,252 | 10,133 |
| Including discontinued operations | 10,253 | 10,116 |

Including discontinued operations means the combined result, not the profit
from discontinued businesses alone. The displayed amounts come from indexed
source rows and the existing cell binder, not this document or an answer key.

NAB FY2025 has three bound variants in the primary results, PDF page 13:
continuing cash earnings of 7,091, continuing statutory profit of 6,788 and
statutory profit including discontinued operations of 6,759, all AUD million.
No fourth cash variant is inferred.

Explicit cash/statutory and operational-scope requests remain filtered.
Comparison calculations, definitions and explanation routes retain their
previous behaviour. A discontinued-operations-only request does not receive
the combined Group total as a substitute.

## Verification

- 606 Python regression tests passed, including nine new scope tests. Existing
  test assertions were not weakened.
- 14 configured demo-backend responses were preserved and checked against the
  CBA and NAB FY2024/FY2025 source tables. Specific requests, two chronological
  profit calculations and unsupported requests also passed their checks.
- Six real HTTP checks passed: broad and specific CBA profit, year/company
  filters, NAB profit, conversational earnings wording and a profit typo.
  The frontend receives the expected cited paragraphs.
- Ten frontend unit tests passed. Runtime integrity and offline installation
  artifact verification passed in the configured standalone checkout and the
  short-path WIL worktree.

The original long WIL folder still exceeds Windows' path limit for one model
artifact, as documented in WIL_MIGRATION.md. Use a short checkout for execution;
no manifest requirement was bypassed.

First-run responses and developer assertions are retained locally in the
standalone backend's `reports/profit-scope-update-2026-10-04/` and
`reports/runs/release-20261004T093947Z/`. They are regression data, not a blind
evaluation set. After recording these responses, the manifest's line endings
were normalised; runtime code and data hashes did not change. The final manifest
SHA256 is `70425ef72da6b39b791058be93bcb00161afa3508b4fc30dd41afd488770f7c9`.
