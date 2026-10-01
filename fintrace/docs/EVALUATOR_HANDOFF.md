# Read-only assessment of the demo candidate

For the WIL submission checkout, use tag `fintrace-demo-2026-10-01` in
`AyushiNegi20/COSC2669-WIL-PROJECT` and run the commands from `fintrace/`.
The original repository's candidate references below remain provenance, not
tags to resolve in the WIL repository. See [migration checks](WIL_MIGRATION.md).

Evaluate the commit at tag `demo-eval-candidate-2026-09-27`. Record its
full commit hash with `git rev-parse HEAD` and verify the working tree is clean.
The earlier `demo-freeze-2026-09-27` is a different, preserved release.

After metadata-only history maintenance, this candidate tag resolves to
`604d4c1` instead of `aa7fef9`. The application files and integrity manifest are
unchanged; only development question-set attribution metadata differs in the
tree. Existing assessment records using the original hash remain historical
records and are not a new assessment of changed runtime behaviour.

Do not edit, tune, regenerate artifacts or switch models during assessment.
Keep fresh questions and source-checked answers outside the repository. Write
the questions before reading the developer's regression cases. Existing exposed
question sets remain useful regressions, but are not fresh independent tests.

## Use the real demo configuration

Run `scripts/bank_integrity.py` before and after. The entry point is
`serve_fintrace_demo.build_backend()`, not a bare
`answer_bank_conversational.Backend()`. The latter does not install all the demo's
configured clients. The candidate uses local Qwen3 8B with the pinned
`config/demo_local8b.json` settings; do not substitute a default model.

An optional runner accepts question text without loading an answer key into the
backend:

```powershell
.\.venv-retrieval\Scripts\python.exe scripts/bank_integrity.py
.\.venv-retrieval\Scripts\python.exe tools/evaluate_release_candidate.py --questions C:\path\to\questions.json
.\.venv-retrieval\Scripts\python.exe scripts/bank_integrity.py
```

Input: `{"questions":[{"id":"q1","q":"Question text"}]}`. Optional scope can be
`{"company":"NAB","year":"2025"}`. Declare filters up front; do not change them
after seeing an answer. Explicit bank/year in a question takes precedence.

The runner preserves full first responses in a new `reports/runs/release-*`
folder, including errors, fallbacks, calculations, sources and presentation.
No retries are used to replace an unfavourable answer. It deliberately does not
award correctness from keyword or number overlap.

## Read the entire answer

Review `response.presentation.paragraphs`, `response.answer.parts[*].claims`,
`response.answer.parts[*].calculations`, source excerpts and qualifications.
Reading only `answer.message` or the claims misses calculated changes. Inspect
the cited source page, reporting basis, unit, entity scope and report vintage.

Report separately:

- Wrong or unsupported financial answers and misleading citations.
- Correct, sufficiently complete answers to source-answerable questions.
- Partial answers and over-refusals where the reports contain an answer.
- Correct handling of genuinely unavailable information.
- Timing, errors and model/excerpt fallbacks.

The metric catalogue is not the boundary of all document Q&A. Conversely,
full-report prose coverage does not imply every table is calculation-ready.
Count answerable coverage gaps as gaps, not successful safety responses. Do not
call partial report excerpts a fully answered question.

## Release decision

Block release for wrong financial figures/bases, misleading evidence, crashes
or a reproducible failure of an agreed essential capability. List less serious
coverage and presentation gaps separately. Do not demand a new architecture or
expand scope as part of this assessment. Do not assume a small clean test set
establishes zero risk on arbitrary questions.

If the candidate passes, leave it unchanged for the demo. If it fails, report
the reproducing question, full response and source evidence before any edits.
