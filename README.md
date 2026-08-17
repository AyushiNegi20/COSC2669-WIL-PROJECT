# WIL Project: Test-Driven RAG

**Course:** COSC2669 / COSC2816 Case Studies in Data Science (PGRD Semester 2 2026)
**Group ID:** _[fill from Canvas]_
**Project:** _[optional project name]_

## Aim

_One-sentence aim statement (user story):_
As a **[role]**, I want **[what the RAG assistant does]**, so that **[the value it delivers]**.

## Team

| Student ID | Name | Role / Skills | Contribution % |
|---|---|---|---|
| s4196173 | Ayushi Negi | Team lead, RAG pipeline + evaluation | |
| _[id]_ | _[name]_ | _[role]_ | |
| _[id]_ | _[name]_ | _[role]_ | |
| _[id]_ | _[name]_ | _[role]_ | |

## What this project is

A small retrieval-augmented-generation (RAG) chatbot for **[domain]**, plus a
quantitative evaluation framework that measures whether it actually adds value.
The knowledge base is intentionally small (a handful of authoritative documents).
LLM inference runs locally and free via Ollama.

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
```

## How to run (once built)

```bash
pip install -r requirements.txt
ollama pull llama3.2        # free local model
python src/ingest.py        # build the index
python eval/evaluate.py     # run the pipeline over the test set and score it
```

## Links

- Trello board: _[link]_
- Milestone 1 report: `docs/`
