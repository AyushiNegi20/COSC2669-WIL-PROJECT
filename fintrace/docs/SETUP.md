# Setup

These commands run from the WIL repository's `fintrace/` directory. The WIL
release provides the same verified evidence bundle as the original demo.

## Already configured laptop

Start Ollama, run `Start-FinTrace-Demo.ps1`, then open http://127.0.0.1:8771/.
The old port 8770 may belong to an earlier process. Use 8771 for this demo.
Keep the terminal open; Ctrl+C stops the server. Restart after updating code:
an existing process can still be running the old version.

The model is pinned Qwen3 8B Q4_K_M. Its application context is 16384 tokens;
definition output is capped at 900 tokens and narrative selection at 160 tokens.
Thinking is disabled, timeout is 35 seconds and keep-alive is 10 minutes.
There are no per-token API charges and no Groq key is needed.

## Local installation with the prepared corpus

Read the [handoff checklist](TEAM_HANDOFF.md) first. Install Git, GitHub CLI, Python 3.12,
Ollama and a compatible NVIDIA driver. Allow disk space for PDFs, evidence,
indexes and several GB of models. The frozen retrieval configuration requires
CUDA; CPU-only execution is not enabled automatically. Use a short local path
outside OneDrive or other sync folders.

Keep the checkout path short, for example `C:\Projects\WIL`. Deep model paths
can exceed Windows limits in nested course folders and appear missing to Python
despite being present. The WIL migration encountered this; use a shorter checkout
instead of disabling integrity checks.

```powershell
gh auth login
gh repo clone AyushiNegi20/COSC2669-WIL-PROJECT
cd COSC2669-WIL-PROJECT\fintrace
py -3.12 -m venv .venv-retrieval
.\.venv-retrieval\Scripts\python.exe -m pip install -r requirements-demo.txt
.\.venv-retrieval\Scripts\python.exe tools/prepare_demo.py
ollama pull qwen3:8b
```

For a private repository, accept the invitation and authenticate with GitHub
first. Do not put access tokens in the clone URL or repository files.

The setup tool downloads the prepared evidence/index ZIP from the repository's
GitHub Release using your GitHub CLI session. It downloads the six PDFs from
issuer URLs and model files from pinned Hugging Face revisions. It verifies all
hashes and refuses to overwrite changed files. A repeat run reuses verified
files; an interrupted individual download restarts that file on the next run.

Only processed evidence and indexes are in the release ZIP. It does not include
credentials, virtual environments, evaluation keys, original PDFs or model
weights. The artifact configuration is `config/setup_artifacts.json`.
The Ollama model is separate and is installed by `ollama pull`.
Its required digest is in `config/demo_local8b.json`; a changed model tag must
be investigated rather than silently accepted.

To inspect the artifact list for this checkout, run this read-only command
from the repository root:

```powershell
$fintraceManifest = Get-Content -Raw releases/current.json | ConvertFrom-Json
$fintraceManifest.files_sha256.PSObject.Properties.Name |
    Where-Object { $_ -match '^(data|models)/' } |
    Sort-Object
```

If GitHub CLI is unavailable, download the evidence ZIP from the
[release page](https://github.com/AyushiNegi20/COSC2669-WIL-PROJECT/releases/tag/fintrace-demo-2026-10-01)
while signed in, then run:

```powershell
.\.venv-retrieval\Scripts\python.exe tools/prepare_demo.py --bundle C:\path\to\fintrace-demo-evidence-aa7fef9.zip
```

PDF and model downloads still require internet access. `--offline` is available
only when those files are already present and verified; it does not bypass
missing files. The full integrity check verifies the received artifacts.
`quality_approved: false` is intentional: this command verifies file integrity,
not whether every answer is correct.

With Ollama running, check the environment and artifacts:

```powershell
.\.venv-retrieval\Scripts\python.exe -c "import torch; print(torch.__version__); print('CUDA available:', torch.cuda.is_available())"
ollama list
.\.venv-retrieval\Scripts\python.exe -X utf8 scripts/bank_integrity.py
.\Start-FinTrace-Demo.ps1
```

CUDA must be available and integrity must report `unchanged: true`. The server
also checks the pinned local model. Open http://127.0.0.1:8771/ after startup.
If PowerShell blocks the launcher, run its equivalent directly:

```powershell
.\.venv-retrieval\Scripts\python.exe -X utf8 scripts/serve_fintrace_demo.py --port 8771
```

This setup has not been certified end to end on a fresh machine. Driver
compatibility, disk space, dependency installation and response time still
need checking on the receiving laptop. No API key is required.

The artifact installer was tested with an isolated checkout: GitHub release
download, restoration of all 176 processed artifacts and a repeat offline run
passed. Source/model files were reused for that isolated test. Separately, all
six PDFs and each model's configuration were downloaded and hash-checked; large
weight URLs were checked for availability without downloading the weights again.
All 13 installer tests and the existing 584 Python regression tests passed.

## Rebuilding evidence: development only

Rebuilding is not the recommended first step for a teammate testing the demo.
Use a separate checkout and extraction environment so frozen artifacts are not
overwritten:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-extraction.txt
.\.venv\Scripts\python.exe -m pip install -r requirements-chunking.txt
```

Source URLs and hashes are in `config/banking_sources.json`. The retained data
preparation tools cover downloading, extraction, numeric consistency checks,
chunking, model download, indexing and full-report prose caches:

1. `scripts/download_bank_sources.py`
2. `scripts/extract_bank_reports.py --stage all`
3. `scripts/check_numeric_consistency.py`
4. `scripts/build_bank_chunks.py`
5. `scripts/download_retrieval_models.py`
6. `scripts/build_bank_index.py`
7. `scripts/bank_report_library.py`

Use the extraction environment for PDF extraction and checks, and the retrieval
environment for models, indexing and the application. Run the relevant tool's
help before a rebuild. The list is a development map, not a certified one-command
reconstruction of the frozen release. The code-only repository does not include
the generated corpus.

`releases/current.json` pins this demo's data and code. A rebuild must be checked
against that manifest. If hashes differ, investigate the source, extraction or
model environment; do not bypass checks or blindly replace expected hashes.
Maintainers can package the exact processed artifacts with
`tools/package_demo_data.py --output dist/new-evidence-bundle.zip`. Publishing a
different bundle requires an explicitly reviewed setup configuration; do not
replace an existing release asset or regenerate the runtime manifest to hide
differences. Packaging never includes entire work directories.

## Troubleshooting

- Missing or changed checkpoint: restore the correct files and rerun integrity.
  Do not bypass the check or regenerate the manifest just to boot.
- Release download denied: run `gh auth status` and check repository access.
  The private release uses the same permissions as the code repository.
- PDF or model hash mismatch: preserve the error and investigate the source.
  Do not accept an upstream replacement without reviewing it.
- CUDA unavailable: check the NVIDIA hardware, driver and installed PyTorch
  wheel. Changing the device creates a different configuration requiring tests.
- Model unavailable: check Ollama is running and the model digest matches.
- Port 8771 occupied: stop your earlier demo with Ctrl+C, or choose an unused
  port with `--port`. Do not stop another person's process blindly.

Before presenting, warm up one numeric and one narrative question. Avoid
competing GPU tasks, and demonstrate source links and evidence limits as well
as a successful answer.

Keep the application on localhost. It is not a public hosted service.
