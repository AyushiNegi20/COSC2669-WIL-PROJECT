# CBA and NAB PDF extraction

Date: 23 September 2026.

## Decision

Use Docling's standard local PDF pipeline with accurate table structure recognition and OCR disabled for the selected born-digital pages. Keep pypdf layout text as an independent audit layer. Use pdfplumber for source-glyph inspection and a narrow, logged correction for invisible accounting brackets.

This is an implemented extraction stage, not a completed RAG application. The initial structured corpus is 72 selected financial pages, not the full 1,021-page archive. All source pages have native-text extraction; sparse or image-based pages in that archive are flagged, not silently declared complete. Independent team review is still pending. No accuracy claim applies to all cells or unseen reports.

## Sources and scope

The [banking manifest](../config/banking_sources.json) contains six issuer PDFs, their URLs and SHA-256 checksums: CBA FY2024 and FY2025 profit announcements, NAB FY2024 and FY2025 results, and both NAB annual reports for supporting accounting notes and cash-flow statements.

The [page selection](../config/banking_extraction_scope.json) is explicit, one-based and inclusive. It covers group results, profit reconciliations, KPI tables, income and expense commentary, lending, deposits, balance sheets, liquidity, definitions and supporting notes. The four results documents are primary. The annual reports supplement them, rather than doubling the results corpus wholesale.

| Document | Native-text pages | Structured pages |
| --- | ---: | ---: |
| CBA FY2024 profit announcement | 149 | 16 |
| CBA FY2025 profit announcement | 151 | 16 |
| NAB FY2024 results | 80 | 17 |
| NAB FY2025 results | 84 | 16 |
| NAB FY2024 annual report | 292 | 3 |
| NAB FY2025 annual report | 265 | 4 |
| Total | 1,021 | 72 |

The older source manifest, CBA/BHP references and `eval/v1` are historical work. They were not deleted or silently rebranded as a NAB evaluation set. They must not be used to score this corpus without revision.

## Actual benchmark

Four libraries were tested in six configurations on the same 18-page development sample. The reference covers 61 financial rows with two ordered values each, plus 80 context anchors. Negative values, percentages, full-year versus half-year columns, Group versus Company columns, definitions and the NAB restatement note are represented.

| Configuration | Correct row/value pairs out of 61 | Values present in page text | Context anchors retained |
| --- | ---: | ---: | ---: |
| Docling, accurate tables | 61 | 61 | 80/80 |
| pdfplumber, text strategy | 45 | 61 | 80/80 |
| PyMuPDF, text strategy | 44 | 61 | 80/80 |
| PyMuPDF, line strategy | 9 | 61 | 80/80 |
| pdfplumber, line strategy | 8 | 61 | 80/80 |
| pypdf layout text | Not applicable: no table adapter | 61 | 80/80 |

This score requires the two expected values to follow the correct matched row in order. Merely finding a number somewhere in the page does not pass. It still does not prove that every header, merged cell, semantic basis or untested row is correct. Context-anchor presence does not prove that every footnote has been attached to the right cell.

The references are AI-assisted transcriptions checked against source text and representative rendered pages. They are development checks, not independent ground truth or a sealed holdout. A shortened Liquidity Coverage label was expanded to its full source label before final scoring; no expected values were changed. All engines were rescored with the same final reference. Lightweight table strategies were untuned; this is not a universal ranking of the libraries.

Observed sample times were about 317 seconds for Docling versus 8-20 seconds for the lightweight configurations. Docling's time includes cold setup and model loading/download activity. These are rough local observations, not controlled throughput benchmarks or user-query latency. Both production and sample conversions used CPU, not the laptop GPU.

Machine-readable results: [benchmark](../reports/extraction_benchmark.json) and [acceptance report](../reports/banking_extraction_acceptance.json).

## What the wider audit caught

Some CBA tables contain closing brackets coloured the same as their background. They are alignment artifacts that are invisible on the rendered page but remain in the PDF text stream. Both ordinary text extraction and Docling can return `908,812)` instead of the visibly printed `908,812`.

The correction is deliberately narrow:

1. The cell must be numeric with an unmatched trailing closing bracket.
2. A matching bracket glyph must be located inside the cell's PDF coordinates.
3. Its light foreground colour must match the local filled rectangle or white page.
4. Only then is that bracket removed from the cleaned cell.
5. The raw text, corrected text, glyph location, colour and rule are logged. Raw extraction stays unchanged.

Visible negative brackets are not removed. White text on a dark background is not treated as invisible. Unresolved artifacts are flagged rather than guessed. This rule is calibrated to these reports, not a general-purpose PDF visibility engine; clipping, transparency and complex overlapping shapes remain limitations.

The selected corpus received 80 source-confirmed bracket corrections. Fourteen additional acceptance cases cover income, lending, customer deposits, balance sheets, equity and LCR, including explicit column positions and period-context checks. All passed after correction. These additional checks helped develop the correction and must not be called a held-out test.

## Output and handoff

Generated files live under `data/processed/banking_v1/` and stay out of Git:

- `native/<document>.json`: all pages of native layout text, dimensions and sparse-page flags.
- `structured/<document>/page_NNN.json`: untouched Docling output, conversion settings, source checksum and timing.
- `evidence/<document>/page_NNN.json`: cleaned evidence blocks, table grids and cell spans, source coordinates, page context, correction log and quality status.
- `evidence/<document>/review.md`: readable extracted pages for review.
- `summary.json`: corpus counts and extraction status.

There are 74 structured tables and 1,260 text blocks in the selected corpus. Fourteen figure objects are retained as references but not transcribed. Do not answer chart-only questions from them. No OCR pass or multimodal chart interpretation is claimed.

PDF page numbers are authoritative. Printed page labels are extracted from footers and marked as automatically detected, not independently reviewed. The report's year is document metadata; it is never assigned blindly to every table cell. Comparatives and half-year columns retain their source labels.

The extraction format is an intermediate representation. It is not yet the historical evidence-v1 chunk/fact contract. The chunking step must produce that downstream representation, or agree a revised contract, explicitly.

No metric facts are automatically declared calculation-ready. The flag `eligible_for_automatic_numeric_facts` remains false. Meaning such as statutory/cash, continuing/total, gross/net, units and measurement periods still needs explicit mapping at the next stage. This prevents an extraction success from being mistaken for financial verification.

## Reproduce

Use Python 3.12 in a project-local environment. The first Docling run needs network access to download public model weights. PDF processing itself is local, with no paid API and no report upload to an LLM service. The current model cache is under `models/huggingface/`, which is ignored by Git.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-extraction.txt
.\.venv\Scripts\python.exe scripts/download_bank_sources.py
.\.venv\Scripts\python.exe scripts/benchmark_pdf_extraction.py --engine pypdf_layout
.\.venv\Scripts\python.exe scripts/benchmark_pdf_extraction.py --engine pdfplumber_lines
.\.venv\Scripts\python.exe scripts/benchmark_pdf_extraction.py --engine pdfplumber_text
.\.venv\Scripts\python.exe scripts/benchmark_pdf_extraction.py --engine pymupdf_lines
.\.venv\Scripts\python.exe scripts/benchmark_pdf_extraction.py --engine pymupdf_text
.\.venv\Scripts\python.exe scripts/benchmark_pdf_extraction.py --engine docling
.\.venv\Scripts\python.exe scripts/benchmark_pdf_extraction.py --summarise
.\.venv\Scripts\python.exe scripts/extract_bank_reports.py --stage all
.\.venv\Scripts\python.exe scripts/validate_bank_extraction.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Once models are cached, add `--offline` to the extraction command. Successful pages are reused only when source hash, pipeline version and Docling version match. Failed pages are retried. Reference answer files are read by validators, never by the production extraction path. Reused benchmark conversions contribute only conversion content, never reference scores or answers.

For a cold independent extraction run, use `--no-benchmark-cache` with a fresh generated-output directory. The initial run reused already computed sample conversions; it was not a second independent extraction of those pages.

The downloader's existing-file verification path was tested here. Fresh source downloads in this session used PowerShell against official issuer URLs. A changed hash must be investigated, not bypassed.

Model revision identifiers observed in the local cache are recorded in `reports/extraction_environment.json`. Direct library versions are pinned; model hashes and the environment record should be retained when sharing results. Future model changes require rerunning the checks.

## What remains before claiming a gold-standard corpus

A numeric consistency guard now scans every stored table cell and checks scalar
numbers against native page text and glyphs at their source coordinates. See
[independent review and holdout handoff](EXTRACTION_HOLDOUT_HANDOFF.md) for the
commands, coverage limits, review queue and version-freeze procedure. Its results
are separate from the development sample scores above. A matching number is not
semantic verification, and pending flags are not waived by freezing the code.

- Janhavi and Hashini should independently review the acceptance references and representative output, including units, scope, footnotes and period alignment. Record corrections and reviewer names honestly.
- Inspect all rows used in the final evaluation answer keys, not just the sampled rows here.
- Agree the final metric mapping and capabilities. The selected source pages support the proposed banking coverage, but do not freeze the team's decision.
- Build table-aware chunks with heading and footnote context, then implement retrieval and answer evaluation. Keep answer keys outside the index.
- Expand extraction only when a supported question requires additional source pages. Preserve explicit source exclusions.

The correct status is: extraction implementation complete for the selected 72-page corpus, automated acceptance passed, independent semantic review pending. It is not a certified or fully verified gold-standard dataset.

## Tool references

- [Docling standard usage](https://docling-project.github.io/docling/usage/)
- [Docling document model](https://docling-project.github.io/docling/reference/docling_document/)
- [pdfplumber extraction and visual debugging](https://github.com/jsvine/pdfplumber)
- [PyMuPDF table API](https://pymupdf.readthedocs.io/en/latest/page.html#Page.find_tables)

PyMuPDF is used only in the benchmark/preview helpers here. Review each dependency's licence before commercial redistribution; using a private repository does not determine licence compliance.
