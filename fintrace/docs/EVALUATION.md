# Evaluation

## Coverage follow-up

The final read-only candidate and its remaining gaps are recorded in
`reports/coverage/RELEASE_CANDIDATE.md`. The protocol for an external reviewer
is `docs/EVALUATOR_HANDOFF.md`.

The current coverage candidate is documented in `reports/coverage/REVIEW.md`.
Its questions were exposed during development. It is not a new blind assessment
and should not inherit accuracy claims from the older frozen release.

```powershell
.\.venv-retrieval\Scripts\python.exe tools/smoke_demo_coverage.py
.\.venv-retrieval\Scripts\python.exe tools/evaluate_wording.py --stage numeric --families-only
```

The first command exercises the actual HTTP handler, source PDF delivery and
known coverage regressions. The second preserves the original supported-metric
wording families. It explicitly excludes the old scope-control questions:
some of those require refusal of measures now supported by checked NAB tables.
Those historical expectations are retained, not silently relaxed. Neither
command supplies a general financial accuracy percentage.

## Earlier evaluations

The wording-robustness follow-up is documented in `reports/wording/REVIEW.md`.
It compares actual financial outputs across question variants, with separate
guard and narrative checks. It is developer-authored regression evidence, not
a new independent accuracy score. Reproduce it with:

```powershell
.\.venv-retrieval\Scripts\python.exe -X utf8 tools/evaluate_wording.py --stage all
```

The runner preserves first responses and failed attempts in timestamped folders.
Numerical equivalence is checked against canonical queries, not against a new
human-transcribed gold set. Narrative evidence requires manual review; its
presence alone is never marked as a correctness pass.

The earlier full rehearsal is in `reports/demo/`: 24 first responses, the protocol
in `eval/demo/protocol.json`, a case-by-case review, summary and browser smoke
notes. It was builder-reviewed and development-exposed, not an independent blind
assessment. HTTP success is not answer correctness.

That run had no HTTP errors or timeouts. The review found the required information
in 17 answerable cases and safe handling of seven guard cases. Narrative passage
selection had a median response time of about seven seconds. This is not a claim
of 100 percent accuracy or successful unrestricted free-form reasoning. Some
answers contain unnecessary context or long quotations.

The original run passed 658 Python tests and 10 frontend tests before repository
cleanup. Obsolete-version tests were removed with their retired code. The
post-cleanup test count is recorded separately in `reports/cleanup_checks.json`;
do not conflate a smaller maintained test suite with an accuracy change.

The cleanup's additional live GPU smoke timed out while other GPU evaluation
work was running. It is preserved as a failed attempt, not counted as a new
end-to-end pass. The current code/data integrity check and maintained tests pass.
Rerun live timing in an uncontended session before relying on a new latency claim.

Run the current checks:

```powershell
.\.venv-retrieval\Scripts\python.exe -X utf8 -m unittest discover -s tests -q
node --test web/ui-model.test.mjs web/scope-controls.test.mjs
.\.venv-retrieval\Scripts\python.exe -X utf8 scripts/bank_integrity.py
.\.venv-retrieval\Scripts\python.exe -X utf8 tools/evaluate_demo.py --quick
```

Omit `--quick` for all 24 demo cases. Every run gets a new folder under
`reports/runs/`; failures are retained, not retried until a favourable answer
appears. Read each answer against its cited source and inspect correctness,
basis, relevance, coverage, refusals and latency separately.

Extraction reference checks and the retained retrieval baseline evaluation have
their own protocols under `eval/`. They are not input to the answer index.
Historical model comparisons and earlier failed runs remain available in Git at
commit `ba7f42d`; they were removed from the current tree, not erased from history.
