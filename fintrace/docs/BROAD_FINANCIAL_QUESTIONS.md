# Broad financial questions: 5 October 2026

This update includes the previously local general-profit change and addresses
related ambiguity in the demo. It does not claim every question is covered.

## What changed

- Generic profit retains the available accounting and operational variants:
  four for CBA FY2025, three for NAB FY2025. Specific requests stay filtered.
- EPS lookups inspect literal indexed source rows for accounting basis,
  basic/diluted status and operational scope. CBA FY2025 exposes four checked
  basic EPS variants; NAB FY2025 exposes six checked basic/diluted variants.
  Equal values with different scopes remain separately labelled. Missing
  variants are not calculated or inferred from a neighbouring EPS figure.
- Unqualified loans shows Group gross loans and acceptances with an explicit
  explanation that this is not net loans or a lending segment. Those qualified
  questions do not enter this shortcut.
- Unqualified income shows available, separately labelled operating-income
  measures. NAB also includes its checked statutory operating income and
  statutory net interest income. A component is not added to its total.
- Unqualified margin offers net interest margin as a labelled alternative,
  not as a synonym for profit margin. Rate changes retain percentage-point
  and basis-point labels and Python arithmetic.
- Company/year filters work with the new routes. Definitions, narrative
  questions, non-Group scopes, unsupported periods and explicit subtypes
  retain their separate routes. Later-report comparative vintage is disclosed.

## Checks performed

Final local checks: 618 Python tests, 10 frontend unit tests, nine HTTP
question checks and four frontend/health asset checks passed. Integrity checks
passed with unchanged evidence and model hashes. These counts cover different
test layers and must not be reported as a combined answer-accuracy score.

The same 24 questions were run before and after the changes through
`serve_fintrace_demo.build_backend()` with the configured local Qwen3 8B
clients. Both runs completed without runtime errors. The questions cover both
banks, generic wording and specific measures that must not be substituted.
Source-bound EPS variants were checked against the extracted tables on CBA
PDF page 19 and NAB PDF page 13. New corpus-backed tests retain their exact
basis and scope. This is a developer regression check, not an independent
accuracy score or a claim of 24 fully complete answers.

The final HTTP rehearsal checks nine questions, including filter-only context,
an explicit continuing-operations EPS request, original-report vintage and an
EPS comparison. It also checks the page, JavaScript, stylesheet and health
endpoint. No live model call is needed to generate these numerical answers;
the configured backend still uses local model services for other question types.

Raw first responses stay locally under
`reports/broad-financial-questions-2026-10-05/` and the earlier profit rehearsal
remains under `reports/profit-scope-update-2026-10-04/`. These run folders are
not application dependencies or blind test sets.

Reproduce on the configured laptop:

```powershell
.\.venv-retrieval\Scripts\python.exe -X utf8 -m unittest discover -s tests
.\.venv-retrieval\Scripts\python.exe -X utf8 tools/check_broad_questions_http.py
.\.venv-retrieval\Scripts\python.exe -X utf8 scripts/bank_integrity.py
```

## Limitations retained

Broad income and margin responses are partial interpretations, not exhaustive
financial summaries. CBA diluted EPS is not bound by this added profile; a
specific request can still receive an honest non-answer. Generic EPS comparisons
on the original core path still calculate basic cash EPS only and are now
marked partial rather than implying all EPS variants were compared. Full-report
prose remains an evidence-reading path, not automatic validation of every table.

The 24-question rehearsal had a slow first profit response while loading
resources. Warm deterministic broad lookups were much faster, but this is not
a latency guarantee. Restart any server started before this update; a running
Python process does not automatically load the new code.

The earlier independent assessment and tag remain historical. These changes
are developer tested and are not a new independent quality certification.
