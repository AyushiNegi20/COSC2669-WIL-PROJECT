# Report implementation checkpoint

Updated 25 October 2026 for the written-report handoff.

The report describes the runtime at original backend commit
`449c4ba4d8e06913f0303a2b73eebf08bc426f57` (13 October 2026).
That identifier records provenance; assessors do not need access to the private
development repository. The public application is under `fintrace/` here.

The WIL copy already included the 5 October broad financial question and expanded
profit/EPS routes. This update imports the two remaining 13 October runtime file
changes, their current integrity manifest and the reporting-limit regression
tests. It preserves the WIL-specific public evidence-bundle location and setup
instructions. No extracted financial values, retrieval settings, model weights
or calculation rules are changed for this report update.

The reporting-limit route distinguishes a prediction from a historical year
outside the FY2024/FY2025 corpus. It explains the available evidence and retains
the original refusal, rather than inventing a result.

`config/setup_artifacts.json` within `fintrace/` pins the current manifest hash
while continuing to download the unchanged verified bundle from this public
repository's `fintrace-demo-2026-10-01` release. There is no need to copy a private
work folder or regenerate a manifest to bypass integrity.

The historical assessment in `report/evidence/` concerns candidate `aa7fef9`,
not this checkpoint. Source equivalence, code tests and integrity checks in this
update do not confer that candidate's financial-quality result on current code.
The final verification record is `SUBMISSION_CHECKS.md`.
