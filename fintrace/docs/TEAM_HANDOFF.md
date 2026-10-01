# Teammate handoff

## Which version to use

For the group submission use `AyushiNegi20/COSC2669-WIL-PROJECT`, with the demo
under `fintrace/` and import tag `fintrace-demo-2026-10-01`. The historical
candidate references below belong to the original FinTrace-Backend repository.
See [WIL migration checks](WIL_MIGRATION.md). The runtime manifest is unchanged.

Use `main`. The current application candidate is tagged
`demo-eval-candidate-2026-09-27`, at commit `604d4c1`. Later handoff documentation
edits and installation tools do not change that runtime. The earlier `demo-freeze-2026-09-27` tag at
`3ed019b` is retained for history. Do not launch an old versioned server just because its
filename looks familiar. The supported entry point is `Start-FinTrace-Demo.ps1`,
which starts `scripts/serve_fintrace_demo.py` on port 8771.

Commit IDs changed during metadata-only history maintenance. The assessment's
original `aa7fef9` corresponds to `604d4c1`, with application files and integrity
manifest unchanged. Existing clones should preserve any local work and use a
fresh clone; do not merge an old local branch back into the rewritten history.

## Before you download models

- The current retrieval configuration explicitly requires NVIDIA CUDA. A
  CPU-only or Mac setup is not a supported drop-in configuration for this freeze.
- Qwen3 8B runs locally through Ollama. No Groq key or paid API is needed.
- Run `tools/prepare_demo.py` as described in [setup](SETUP.md). It downloads
  the processed evidence/index release, original PDFs and pinned model files,
  verifying each against the current manifest. No manual file handoff is needed.
- Do not copy virtual environments, API keys, `.env` files or the whole working
  folder. Install your own environment using [setup](SETUP.md).
- Use a short local path outside cloud-sync folders. If you do not have a
  compatible machine, arrange to test on the configured laptop rather than
  spending time downloading models for an unsupported setup.

The integrity manifest also includes extraction model snapshots. They must be
present even when reusing the prepared corpus. The setup tool downloads them.
The prepared bundle is a release asset, not part of Git history. A clean-machine
installation of Python/CUDA/Ollama has not been certified end to end.

## Checks before testing

Follow the setup guide, then verify integrity before starting the server:

```powershell
.\.venv-retrieval\Scripts\python.exe -X utf8 scripts/bank_integrity.py
.\Start-FinTrace-Demo.ps1
```

The integrity check must report `unchanged: true`. Missing files mean setup is
incomplete, not that you should regenerate the manifest. Changed files need to
be compared with the frozen commit or the reviewed data copy first.

Open http://127.0.0.1:8771/ and try:

1. `What was CBA profit in FY2025?` Check labelled cash and statutory figures.
2. `Which sector did CBA invest more in FY2025?` Check the internal-spending
   interpretation, largest category and largest increase, with source pages.
3. `How did NAB cash earnings change from FY2024 to FY2025?` Check the
   calculation and reporting basis.
4. `Why did CBA staff expenses increase in FY2025?` Read the cited evidence.
   A grounded excerpt fallback is possible instead of generated prose.
5. `What will CBA profit be next year?` Check that no forecast is invented.

Wait for each answer before sending the next request. The first answer can be
slower while models load. This is a single-user local demo.

For an issue, share the exact question, company/year filters, downloaded answer
JSON, screenshot and Git commit (`git rev-parse --short HEAD`). A refusal is not
automatically an error: check [known limitations](LIMITATIONS.md).

## Repository checks on 27 September 2026

The current candidate was checked locally before this handoff update:

- 584 Python tests passed using `python -m unittest discover -s tests`.
- 10 frontend unit tests passed using
  `node --test web/ui-model.test.mjs web/scope-controls.test.mjs`.
- The code and local-artifact integrity check passed with no mismatches.
- The preceding candidate rehearsal preserved 24 first responses with zero
  runtime errors and passed nine HTTP question checks plus frontend asset,
  health and source-PDF checks. These were not a new visual UI audit or a
  blind accuracy assessment. See the
  [candidate review](../reports/coverage/RELEASE_CANDIDATE.md) for the partial
  answers and coverage gaps.

These are regression and integrity checks on the configured laptop, not a
fresh independent accuracy score or proof that another laptop is configured.
The earlier evaluation run snapshots remain on disk and have not been deleted.
