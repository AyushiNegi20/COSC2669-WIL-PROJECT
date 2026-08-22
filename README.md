# FinTrace — Test-Driven Financial RAG

**Course:** COSC2669 / COSC2816 Case Studies in Data Science (PGRD Semester 2 2026)
**Canvas Group ID:** WIL Project 9

**Tentative project:** FinTrace

**Tagline:** Ask. Trace. Verify.

## Aim

To develop and evaluate a test-driven RAG system that enables finance and
investor-relations analysts to ask questions about authoritative corporate
reports and verify financial statements using traceable page-level evidence,
deterministic calculations and document-version awareness before human approval.

**Working user story:** As a finance or investor-relations analyst, I want to ask
questions and verify financial information against authoritative corporate
documents, so that I can identify potential inconsistencies quickly and review
the supporting evidence before approval.

## Team

| Student ID | Name | Role / Skills | Contribution % |
|---|---|---|---|
| s4196173 | Ayushi Negi | Technical project lead; architecture, Python, Walert reproduction, integration and code review | _[agree]_ |
| _[id]_ | _[name]_ | RAG and information-retrieval engineering | _[agree]_ |
| _[id]_ | _[name]_ | Knowledge-base, PDF processing and data provenance | _[agree]_ |
| _[id]_ | _[name]_ | Test collection and quantitative evaluation | _[agree]_ |
| _[id]_ | _[name]_ | Financial verification and deterministic computation | _[agree]_ |
| _[id]_ | _[name]_ | Prototype, responsible AI and quality assurance | _[agree]_ |

> The five remaining names/IDs and all agreed contribution percentages must be
> completed by the team before Milestone 1 submission.

## What this project is

A bounded financial-document assistant with two connected capabilities:

1. **Ask mode:** answer questions over corporate reports with page-level evidence.
2. **Verify mode:** classify a submitted financial statement as supported,
   mismatched, superseded or unable to verify, and show the evidence and
   deterministic calculation used.

The test collection is defined before system tuning. The team will compare
retrieval and answer variants on the same questions, including unanswerable and
document-version cases. The graded system will use a small local model without
additional API cost.

## Repository structure

```
data/                 knowledge base documents (the corpus)
src/
  ingest.py           load, chunk, and embed the documents
  retriever.py        embedding search over the corpus
  generate.py         answer generation via a local Ollama model
  rag.py              end-to-end pipeline
eval/
  test_questions.json test set, written before building (test-driven)
  evaluate.py         metrics: % unanswered, retrieval hit@k, faithfulness
  results/            output tables and figures
docs/                 milestone report + AI declaration
walert_reproduction/  repeatable preliminary Walert baseline and results
```

## Preliminary Walert reproduction

The first repeatable baseline has been completed using the official Walert test
collection. It rebuilds BM25 from 120 passages, searches 106 questions and
recalculates retrieval and refusal metrics without external Python packages.
See [method and commands](walert_reproduction/README.md) and the
[result summary](walert_reproduction/RESULTS.md).

## How to run (once built)

```bash
pip install -r requirements.txt
ollama pull llama3.2        # free local model
python src/ingest.py        # build the index
python eval/evaluate.py     # run the pipeline over the test set and score it
```

## Links

- Trello board: https://trello.com/invite/b/6a8261255da0dc4322e1f514/ATTI8bd6c39e4e277596afeae19b35a24d83BEC3E26F/cosc2669-wil-project
- Private GitHub repository: https://github.com/AyushiNegi20/COSC2669-WIL-PROJECT
- Milestone 1 report: `docs/`
