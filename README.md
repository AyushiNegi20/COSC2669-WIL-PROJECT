# FinTrace: Financial Report Research

COSC2669 Case Studies in Data Science | WIL Project 9

This is the team's submission repository. It contains the FinTrace demo,
evaluation tools, setup documentation and earlier Milestone 1 work.

## Problem and scope

Financial analysts reviewing Australian banks need to locate, compare and
interpret information across lengthy reports. Similar figures can use different
periods, units, reporting bases or report versions. FinTrace helps users inspect
the evidence behind an answer instead of relying on an unsupported response.

The prototype uses six official CBA and NAB reports covering FY2024 and FY2025.
It combines retrieval, source-bound numerical answers, Python calculations and
local Qwen3 8B assistance. Answers show source pages and evidence limitations.
Numerical support is bounded to checked measures; searching a full report does
not make every table or possible question independently verified.

This is a research demo, not investment advice or a production assurance tool.

## Run the demo

The tested configuration is Windows, Python 3.12, an NVIDIA CUDA-capable GPU
and Ollama. CPU-only, Mac and Linux configurations have not been validated.
No paid model API or API key is required. Use a local folder outside OneDrive.
Install Git, GitHub CLI, Python 3.12, Ollama and a compatible NVIDIA driver first.

```powershell
gh auth login
gh repo clone AyushiNegi20/COSC2669-WIL-PROJECT
cd COSC2669-WIL-PROJECT\fintrace
py -3.12 -m venv .venv-retrieval
.\.venv-retrieval\Scripts\python.exe -m pip install -r requirements-demo.txt
.\.venv-retrieval\Scripts\python.exe tools/prepare_demo.py
ollama pull qwen3:8b
```

With Ollama running:

```powershell
.\.venv-retrieval\Scripts\python.exe -c "import torch; print('CUDA available:', torch.cuda.is_available())"
.\.venv-retrieval\Scripts\python.exe -X utf8 scripts/bank_integrity.py
.\Start-FinTrace-Demo.ps1
```

CUDA must be available and integrity must report `unchanged: true`. Open
[the local demo](http://127.0.0.1:8771/). Keep the terminal running.
Do not regenerate the integrity manifest to bypass missing or changed files.

The installer downloads the verified evidence bundle from this repository's
[demo release](https://github.com/AyushiNegi20/COSC2669-WIL-PROJECT/releases/tag/fintrace-demo-2026-10-01),
the original PDFs from their issuers and pinned model files from Hugging Face.
Access to the separate FinTrace-Backend repository is not needed for setup.
Allow several GB of disk space. Do not copy another person's virtual environment
or credentials. See the [setup guide](fintrace/docs/SETUP.md) for details.

## Code, evidence and assessment files

| Location | Contents |
| --- | --- |
| [fintrace/](fintrace/) | Application, frontend, source configuration and regression tests |
| [Architecture](fintrace/docs/ARCHITECTURE.md) | Retrieval and answer pipeline |
| [Evaluation](fintrace/docs/EVALUATION.md) | Evaluation methods and their limitations |
| [Migration checks](fintrace/docs/WIL_MIGRATION.md) | Imported release, integrity and WIL checkout checks |
| [Known limitations](fintrace/docs/LIMITATIONS.md) | Coverage and answer-quality boundaries |
| [Evaluator handoff](fintrace/docs/EVALUATOR_HANDOFF.md) | Use the configured demo, preserve first responses and score evidence |
| [walert_reproduction/](walert_reproduction/) | Preliminary BM25 reproduction, tests and results |
| [docs/](docs/) | Milestone 1 submission and AI-use records |

From `fintrace/`, run the regression suites with:

```powershell
.\.venv-retrieval\Scripts\python.exe -m unittest discover -s tests
node --test web/ui-model.test.mjs web/scope-controls.test.mjs
```

Node.js is required for the frontend tests, not for serving the demo. Passing
regressions is not a universal accuracy claim. Historical evaluation reports
retain their original scope and must not be presented as fresh blind results.

## Team and coordination

Ayushi Negi, Janhavi Maheshwar Ghate, Shriram Varadarajan, Guruprasad Simimath,
Yash Keswani and Hashini Santhanakrishnan.

- [Trello board](https://trello.com/b/TlRdAYBm/cosc2669-wil-project)
- [Milestone 1 report](docs/FinTrace_Milestone1_Report.pdf)
- [Milestone 1 planning record and role table](docs/MILESTONE1_README.md)
- [AI-use working log](docs/AI_USE.md)
- [Milestone 1 Condition 3 declaration](docs/Condition3_AI_Declaration.pdf)

The historical plan is retained as a record, not as the current installation
guide or final contribution statement. Final contributions and the assessment
declaration must reflect the work actually completed by each member.
