# Written-report handoff checks

Date: 25 October 2026. These are repository, evidence and document checks, not a
fresh financial-answer evaluation or group sign-off.

## Document

- Changes were made in the original shared Overleaf project. Existing source
  text was checked before replacement to avoid overwriting concurrent edits.
- Report compile: zero errors and zero warnings; bibliography spacing produces
  informational underfull-box notices, not clipped body content.
- Rendered pagination: 25 PDF pages overall. Physical pages 1-20 contain the
  cover, front matter and main report. Physical page 21 starts the template's
  excluded-content marker, declaration, acknowledgements and references;
  appendices follow. The counted length is therefore 20 pages.
- The five other reflections remain empty for their owners. Filling them in
  the appendix does not add counted main text, but any further edits should be
  followed by a new page-limit check.
- Declarations record substantive AI assistance. The 24-case results table
  preserves the historical review's categories and unclassified D20, rather
  than inventing a complete accuracy score.
- Public report links point to tag `report-submission-2026-10-25`. Technical
  configuration details were moved to the appendix to keep the main narrative
  readable and within the limit. Source screenshots and diagram are retained.

## Code and artifacts

- Current manifest: `3d4043f96753b48f3fa57d9bae5c83837d9a989bbde124cb845010b129e673d3`.
- The WIL reporting-limit runtime files and manifest match original backend
  checkpoint `449c4ba`. WIL setup continues using the public evidence release.
- `python report/verify_submission.py`: 24 original first responses checked
  against the preserved aggregate, original before/after integrity intact,
  87 manifest-listed code/configuration files verified, and 20 report evidence
  URL targets resolved locally. Original response hashes match the source copy.
- Full `bank_integrity.py` check on the configured WIL copy: `unchanged: true`,
  no errors. Local evidence and model files were copied from the existing
  installation and verified; they are ignored by Git, not published as source.
- Final Python regression run: 621 tests, no failures, no errors, no skips.
- Frontend Node tests: 10 passed, zero failures.
- Walert reproduction tests: 3 passed.
- No assertions were weakened and no financial values or retrieval settings
  were modified for this submission sync. No new model-quality score is claimed.

## Earlier attempts retained in the account

The first Python run in the sandbox was blocked by loopback/socket and temporary
file permissions. With those permissions available, the clean code-only checkout
ran 601 tests with four corpus-dependent skips. An attempted directory junction
was denied and was not used. Copying data without the required model artifacts
then exposed four integrity errors for missing model files. After all
manifest-listed local artifacts were copied, integrity passed and all 621 tests
ran successfully. Missing files were supplied; integrity was not bypassed.

Dependencies were reused from the existing Python environment. This is not a
certified fresh-machine installation or an unrestricted end-to-end accuracy
assessment. Historical evaluation results remain tied to their original runs.

## Remaining human actions

- Five members complete their own reflections and review their technical account.
- The group confirms actual completed contributions and agrees the final
  written-report contribution sheet. Allocation of work is not authorship proof.
- Complete and agree the written-report Condition 3 declaration, consistent with
  actual AI assistance and any teaching-team clarification of permitted uses.
- Export the latest report from the original Overleaf project, review the three
  final PDFs and submit after group approval. The older presentation forms are
  not automatically the written-report forms.
