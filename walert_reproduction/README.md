# Preliminary Walert reproduction

This folder records a small, honest reproduction of the retrieval and evaluation
ideas in the official [Walert repository](https://github.com/rmit-ir/walert).
It is intended as Milestone 1 evidence, not as a claim that the complete legacy
Falcon/Pyserini stack has been rerun.

## What is reproduced

- A BM25 index is rebuilt from Walert's 120 public FAQ passages using only the
  Python standard library.
- All 106 public questions are searched, and a TREC-format run is saved.
- The new run and Walert's supplied BM25, dense and intent runs are scored against
  Walert's public relevance judgments using MRR, nDCG@1/3/5 and Hit@1/3/5.
- Walert's supplied Falcon outputs are audited for the percentage of deliberately
  out-of-knowledge-base questions that received a refusal.
- SHA-256 hashes identify every upstream input used.

## Run it

From a folder next to this project, clone the official repository:

```powershell
git clone --depth 1 https://github.com/rmit-ir/walert.git _reference_walert
git -C _reference_walert rev-parse HEAD
```

Then run the evaluator, replacing the paths if necessary:

```powershell
python walert_reproduction/evaluate_walert.py `
  --walert-root ..\_reference_walert `
  --upstream-commit 9417518ade245771b2d4f1ad919b840cecb2876e
```

No Python packages are required. Results are written to
`walert_reproduction/results/`.

## Interpretation boundary

The locally rebuilt BM25 run is the independently executed preliminary baseline.
The rows labelled `*_supplied` are metrics recalculated from artifacts committed
by Walert's authors. The original dense retrieval and Falcon-7B generation are not
re-executed because the research stack targets Python 3.9, Pyserini/Java, a legacy
dense model and Falcon-7B hardware. A later sprint can reproduce generation with a
small local Ollama model on the team's bounded finance corpus.

Source: S. Pathiyan Cherumanal et al., “Walert: Putting Conversational Information
Seeking Knowledge into Action by Building and Evaluating a Large Language
Model-Powered Chatbot,” CHIIR 2024, DOI: 10.1145/3627508.3638309.
