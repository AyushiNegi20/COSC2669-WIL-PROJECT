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

Migration verification results are recorded after checks in the short checkout.
They are portability and regression checks, not a new answer-accuracy score.
