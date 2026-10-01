# WIL demo import

## Provenance

Imported on 1 October 2026 from
`AyushiNegi20/FinTrace-Backend` commit
`289f3a39fa8adaa83038118e7335d7d33807f2d8`.
The source runtime candidate is `604d4c1`, originally assessed as `aa7fef9`.
This import does not claim a new independent evaluation.

The 209 tracked source files were copied into `fintrace/`. The application,
frontend, tests and integrity manifest were preserved byte for byte. Changes
are limited to installation/repository documentation and the release download
location in `config/setup_artifacts.json`.

Runtime manifest SHA256:
`e3345d286daf6f772150e9eca1d672b627f0d54d728ef191a55d7e1bbc66b744`

Evidence bundle SHA256:
`30c874c2b9d38dface160aa3e35eda1e219516aeafd8c8c3b7e5dbcc5893ee27`

The WIL release is `fintrace-demo-2026-10-01`. Only the existing processed
evidence bundle is republished. PDFs and model weights come from their original
hosts using pinned URLs and hashes. Credentials, environments and local models
are not committed. Existing milestone files, AI declarations and Walert work
are preserved; the earlier root README is retained in `docs/MILESTONE1_README.md`.

## Installation constraint identified during import

The long local path under `SEM 3/Case Study/WIL Task 1` exceeded the Windows
path limit for one deeply nested extraction model file. The initial integrity
check and three test setups failed because Python could not see that file,
even though it was present. No application assertion or manifest was relaxed.
Use a short checkout path, such as `C:\Projects\WIL`, outside cloud-sync folders.

## Verification

Verified the WIL import commit `5dfff80` from the short local worktree
`C:\Users\lenovo\Claude\WIL-Demo`, using the existing configured Python environment.
This reuses dependencies and model artifacts; it is not a fresh-machine install.

- Source integrity passed before copying. WIL integrity passed before and after
  the HTTP run with the unchanged manifest and no mismatches.
- 597 Python regression tests passed; 10 frontend unit tests passed.
- The three existing Walert tests passed. Milestone artifacts were unchanged.
- All nine HTTP question checks passed the existing assertions, along with
  frontend HTML, health, JavaScript and source-PDF delivery checks.
- The pinned local Qwen3 8B model was used. Ollama initially was not running;
  smoke/wording runners failed at startup before answering any questions. The
  service was started and the nine-question HTTP run then completed once.
- Six HTTP responses were source-bound answers, two were partial answers and
  one was an appropriate unavailable-year refusal. These status labels are not
  an independent correctness grade. The slowest request took 87.15 seconds
  during cold retrieval/model work. Warm-up and latency limitations still apply.
- A file-by-file comparison found only five imported files changed: the README,
  setup release location and three handoff/setup documents. Runtime code, tests,
  frontend, source configuration and integrity manifest remained byte-identical.
- No credential-pattern matches were found in the staged imported text. Only
  tracked source files were imported; local data/models remain ignored.

The first completed HTTP responses and summary are retained in
[the migration run](../reports/migration/http-2026-10-01/summary.json).
The existing [30 September pre-recording audit](../reports/migration/PRE_RECORDING_CHECK_2026-09-30.txt)
is preserved separately and is not relabelled as a new run. Its 232 numerical
wording checks were not repeated for this packaging-only import.

These are portability and regression checks, not a new answer-accuracy score.
There was no interactive visual browser audit or clean-machine installation.
