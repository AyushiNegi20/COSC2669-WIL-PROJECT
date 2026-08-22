# Preliminary Walert reproduction

This folder contains our preliminary test of the retrieval and evaluation process
used in the official [Walert repository](https://github.com/rmit-ir/walert).
For Milestone 1, we rebuilt the BM25 search step and checked Walert's saved result
files. We did not rerun the full Falcon and Pyserini setup.

## What we tested

- We rebuilt a BM25 index from Walert's 120 public FAQ passages using only the
  Python standard library.
- We searched all 106 public questions and saved the rankings in TREC format.
- We scored our run and Walert's saved BM25, dense and intent runs against the
  supplied relevance judgments using MRR, nDCG@1/3/5 and Hit@1/3/5.
- We checked how often Walert's saved Falcon outputs refused questions that could
  not be answered from the knowledge base.
- We saved SHA-256 hashes so the exact input files can be checked later.

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

## What this result covers

The locally rebuilt BM25 run is the part we ran ourselves. Rows labelled
`*_supplied` use result files already provided by Walert's authors. We did not
rerun the original dense retrieval or Falcon-7B generation because that setup
depends on Python 3.9, Pyserini, Java and hardware suitable for Falcon-7B. In a
later sprint, we will test generation with a smaller local Ollama model and our
finance documents.

Source: S. Pathiyan Cherumanal et al., "Walert: Putting Conversational Information
Seeking Knowledge into Action by Building and Evaluating a Large Language
Model-Powered Chatbot," CHIIR 2024, DOI: 10.1145/3627508.3638309.
