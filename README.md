# FinTrace: Test-Driven Financial RAG

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
| s4196173 | Ayushi Negi | Technical project lead and integration; architecture, Python, RAG integration and code review | 16.67% |
| s4188725 | Janhavi Maheshwar Ghate | Test collection and evaluation; gold questions, metrics, citation checks and error analysis | 16.67% |
| s4162697 | Shriram Varadarajan | Financial intelligence and validation; normalisation, calculations, reconciliation and automated testing | 16.67% |
| s4188084 | Guruprasad Simimath | RAG and information retrieval; chunking, BM25/vector search, embeddings and model integration | 16.67% |
| s4177991 | Yash Keswani | Knowledge base, research and data provenance; document extraction, metadata and version tracking | 16.67% |
| s4196172 | Hashini Santhanakrishnan | Prototype, responsible AI and quality assurance; evidence workflow, usability and human oversight | 16.67% |
|  |  | **Total after rounding** | **100.02%** |

Contribution shares are equal at one-sixth per member. The displayed total is
100.02% because each share is rounded to two decimal places.

## What this project is

FinTrace is planned as a financial document assistant with two connected features:

1. **Ask mode:** answer questions over corporate reports with page-level evidence.
2. **Verify mode:** classify a submitted financial statement as supported,
   mismatched, superseded or unable to verify, and show the evidence and
   deterministic calculation used.

We will write the test questions before tuning the system. This gives us one fixed
test set for comparing different retrieval and answer methods. It will include
questions that cannot be answered and questions involving older document
versions. We plan to use a small local model so there is no extra API cost.

## Planned project structure

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

We tested the evaluation process using Walert's official test collection. Our
script rebuilds BM25 from 120 passages, searches 106 questions and calculates
retrieval and refusal metrics without external Python packages.
See [method and commands](walert_reproduction/README.md) and the
[result summary](walert_reproduction/RESULTS.md).

## Planned run commands

```bash
pip install -r requirements.txt
ollama pull llama3.2        # free local model
python src/ingest.py        # build the index
python eval/evaluate.py     # run the pipeline over the test set and score it
```

## Links

- Trello board: https://trello.com/invite/b/6a8261255da0dc4322e1f514/ATTI8bd6c39e4e277596afeae19b35a24d83BEC3E26F/cosc2669-wil-project
- Private GitHub repository: https://github.com/AyushiNegi20/COSC2669-WIL-PROJECT
- [Milestone 1 report](docs/FinTrace_Milestone1_Report.pdf)
- [Condition 3 AI declaration](docs/Condition3_AI_Declaration.pdf)
