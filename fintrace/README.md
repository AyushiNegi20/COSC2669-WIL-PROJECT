# FinTrace

This demo is maintained under `fintrace/` in the official
[WIL repository](https://github.com/AyushiNegi20/COSC2669-WIL-PROJECT).
Run the commands below from that subdirectory. See
[migration and verification](docs/WIL_MIGRATION.md) for the imported candidate.

Source-grounded financial report research for Commonwealth Bank of Australia
(CBA) and National Australia Bank (NAB), covering FY2024 and FY2025.

FinTrace combines report retrieval, checked numerical calculations and local
language-model assistance. Answers include source pages, reporting context and
evidence limitations. Developed for COSC2669, WIL Project 9.

## Quick start: prepared environment

On the configured laptop, start Ollama and run:

```powershell
.\Start-FinTrace-Demo.ps1
```

Open [FinTrace](http://127.0.0.1:8771/). Keep the terminal running.
Restart the server after pulling code. An already running server still uses
the version it loaded at startup.

## Local installation

The tested setup is Windows with Python 3.12, an NVIDIA CUDA-capable GPU and
Ollama. CPU-only, Mac and Linux configurations have not been validated. No
model-provider API key is required. Allow disk space for Python dependencies,
approximately 2 GB of source/model artifacts and the separate Ollama model.

The setup command downloads the prepared evidence/index bundle from
[GitHub Releases](https://github.com/AyushiNegi20/COSC2669-WIL-PROJECT/releases/tag/fintrace-demo-2026-10-01),
the six PDFs from their issuers and pinned model files from Hugging Face.
Every file is checked against `releases/current.json`. Matching files are
reused; changed files are not overwritten. No manual file transfer is required.

1. Install Git, GitHub CLI, Python 3.12, Ollama and a compatible NVIDIA driver. Accept the
   GitHub invitation if the repository is private. Use a local folder outside
   OneDrive or other cloud-sync folders.
2. Open PowerShell in that folder and run:

   ```powershell
   gh auth login
   gh repo clone AyushiNegi20/COSC2669-WIL-PROJECT
   cd COSC2669-WIL-PROJECT\fintrace
   py -3.12 -m venv .venv-retrieval
   .\.venv-retrieval\Scripts\python.exe -m pip install -r requirements-demo.txt
   .\.venv-retrieval\Scripts\python.exe tools/prepare_demo.py
   ollama pull qwen3:8b
   ```

3. Start Ollama and verify the setup:

   ```powershell
   .\.venv-retrieval\Scripts\python.exe -c "import torch; print('CUDA available:', torch.cuda.is_available())"
   .\.venv-retrieval\Scripts\python.exe -X utf8 scripts/bank_integrity.py
   .\Start-FinTrace-Demo.ps1
   ```

   CUDA must be available and integrity must report `unchanged: true`. A missing
   file means setup is incomplete. Do not regenerate the manifest to bypass it.
4. Open http://127.0.0.1:8771/ and keep the terminal open. Try
   `What was CBA profit in FY2025?`, then read the sources. Ctrl+C stops the app.

If PowerShell blocks the launcher, use:

```powershell
.\.venv-retrieval\Scripts\python.exe -X utf8 scripts/serve_fintrace_demo.py --port 8771
```

The release bundle contains only manifest-listed processed evidence and indexes.
Source PDFs and third-party model weights are downloaded from their original
hosts, not copied into Git history. Credentials and evaluation answer keys are
not part of the bundle.

The first response can take longer while models load. This is a single-user
localhost prototype, not a hosted service. Installation and performance on
other machines may require additional configuration. See [setup](docs/SETUP.md)
for troubleshooting and a browser-download alternative to GitHub CLI, or the
[handoff checklist](docs/TEAM_HANDOFF.md) for acceptance checks.

## How answers work

1. Interpret the question and its company, year and financial meaning.
2. Retrieve report evidence with its source and reporting context.
3. Use Python for supported financial calculations, local Qwen3 8B for checked
   definitions, or model-selected literal passages for narrative questions.
4. Display the answer, page references, workings and any evidence limits.

The current demo uses **Ollama locally**, not Groq. Numerical support is bounded
to checked metrics. Narrative answers are not unrestricted generated reasoning.

## Repository structure

| Folder | Purpose |
| --- | --- |
| `scripts/` | Active application modules and data preparation |
| `web/` | Browser interface and its shared components |
| `config/` | Sources, models, financial concepts and retrieval settings |
| `tests/` | Regression tests for retained functionality |
| `tools/` | Setup, packaging and evaluation commands |
| `eval/` | Evaluation protocols and source-reference checks |
| `reports/demo/` | Earlier demo rehearsal and review, retained as history |
| `reports/coverage/` | Follow-up coverage fixes, exposed regressions and remaining gaps |
| `tools/evaluate_release_candidate.py` | Run questions through the configured demo and preserve full responses |
| `releases/` | Current integrity manifest and extraction/chunk provenance |

Read [architecture](docs/ARCHITECTURE.md), [evaluation](docs/EVALUATION.md) and
[known limitations](docs/LIMITATIONS.md).

## Release and checks

Use `main` for the current installation tools and documentation. The WIL import
is tagged `fintrace-demo-2026-10-01`. In the original FinTrace-Backend repository,
the application candidate is pinned at tag `demo-eval-candidate-2026-09-27` (commit `604d4c1`);
its pinned runtime files remain unchanged. The earlier demo remains at
`demo-freeze-2026-09-27` (`3ed019b`). Do not mix the two releases' data files.

Metadata-only history maintenance changed commit IDs. The assessment originally
recorded `aa7fef9`; `604d4c1` has identical application files and the same integrity
manifest. Development question-set attribution metadata changed, not its
questions or reference answers. This is not a new independent evaluation.

The candidate passed 584 Python regression tests, 10 frontend tests and 232
supported numerical wording checks on the development machine. The current
suite also includes setup-tool tests. The development
rehearsal preserved 24 first responses without runtime errors; incomplete
answers and refusals are documented in the
[candidate review](reports/coverage/RELEASE_CANDIDATE.md), not counted as correct
answers. This is not a new independent accuracy score.

To rerun the unit suites in the prepared environment (Node.js is needed only
for the frontend tests, not to serve the app):

```powershell
.\.venv-retrieval\Scripts\python.exe -m unittest discover -s tests
node --test web/ui-model.test.mjs web/scope-controls.test.mjs
```

Local first-response snapshots remain under ignored `reports/runs/` folders.
They are not inputs to the answer pipeline. Historical reports describe their
own runs and should not be read as results for the latest candidate.

For the final read-only candidate assessment, follow
[the evaluator handoff](docs/EVALUATOR_HANDOFF.md). It specifies the actual demo
backend, full-response scoring and the candidate tag. Use the documented backend
and configuration for reproducible comparisons.

Some imported modules retain version suffixes in their filenames. They are
dependencies of this application, not separate demos to launch. Unused versions,
model comparisons and historical runs have been removed from the current tree.
They remain recoverable at Git commit `ba7f42d`.

This is a research prototype, not investment advice or a production financial
assurance service. Passing regression tests does not establish universal accuracy.
