# Walert preliminary results

Run date: 22 August 2026

Official upstream commit: `9417518ade245771b2d4f1ad919b840cecb2876e`

## Test collection

| Item | Count |
|---|---:|
| FAQ passages | 120 |
| Questions | 106 |
| Topics | 43 |
| Known/paraphrased questions | 84 |
| Inferred questions | 12 |
| Out-of-knowledge-base questions | 10 |

The 96 known and inferred questions have relevance judgments. The remaining 10
questions are deliberately outside the knowledge base and are used to test
whether a system abstains instead of inventing an answer.

## Independently executed BM25 baseline

| Question subset | Questions | MRR | nDCG@5 | Relevant evidence in top 5 |
|---|---:|---:|---:|---:|
| Known | 84 | 0.6674 | 0.4245 | 82.14% |
| Inferred | 12 | 0.4547 | 0.3798 | 66.67% |
| All answerable | 96 | 0.6408 | 0.4190 | 80.21% |

These are new results from the standard-library BM25 implementation in this
repository. They show a useful but imperfect baseline and a clear generalisation
gap: inferred questions were 15.47 percentage points less likely than known
questions to retrieve relevant evidence in the top five.

## Recalculation from Walert-supplied retrieval runs

All 96 answerable questions are included in the denominator, including questions
for which a system returned no result.

| Supplied run | Queries with results | MRR | nDCG@5 | Hit@5 |
|---|---:|---:|---:|---:|
| Walert BM25 | 96/96 | 0.6029 | 0.4553 | 77.08% |
| Walert dense | 96/96 | 0.6845 | 0.5383 | 71.88% |
| Walert intent | 72/96 | 0.5729 | 0.1957 | 57.29% |

The dense supplied run has the strongest graded ranking score, but not the best
binary Hit@5. This is why the project should report more than one retrieval
measure. The intent system's MRR would rise to 0.7639 if the denominator included
only its 72 returned queries; retaining all 96 avoids hiding unanswered cases.

## Out-of-knowledge-base refusal audit

| Supplied system/output | Retrieved contexts | Refused | Unanswered rate |
|---|---:|---:|---:|
| Intent system | 1 | 8/10 | 80% |
| BM25 + Falcon | 1 | 1/10 | 10% |
| BM25 + Falcon | 3 | 2/10 | 20% |
| BM25 + Falcon | 5 | 2/10 | 20% |
| Dense + Falcon | 1 | 0/10 | 0% |
| Dense + Falcon | 3 | 1/10 | 10% |
| Dense + Falcon | 5 | 1/10 | 10% |

For out-of-knowledge-base questions, a higher refusal rate is desirable. The
supplied generative RAG outputs frequently answered despite the absence of a gold
answer. This motivates FinTrace's explicit `Unable to verify` outcome and its
evaluation of both evidence retrieval and appropriate abstention.

## What may be stated in Milestone 1

The team independently rebuilt and evaluated a Walert-style BM25 retrieval
baseline and recalculated metrics from the official Walert artifacts. The full
legacy Falcon-7B/Pyserini pipeline was not re-executed. The preliminary baseline
achieved 80.21% Hit@5 over 96 answerable questions, while the supplied generative
outputs refused only 0–20% of 10 deliberately out-of-KB questions. These findings
support testing evidence retrieval and abstention separately in FinTrace.

## Reproducibility

Detailed machine-readable results, input hashes and the generated TREC run are in
`results/`. Run the command in `README.md` to regenerate them. Metric definitions:

- **MRR:** rewards placing the first relevant passage near rank 1.
- **nDCG@5:** rewards ranking highly relevant passages near the top, using graded
  relevance.
- **Hit@5:** percentage of questions with at least one relevant passage in the
  first five results.
- **Unanswered rate:** percentage of out-of-KB questions labelled as a refusal.

Limitations: the local BM25 tokenizer is intentionally transparent and is not an
exact Lucene analyzer reproduction; supplied dense/Falcon files are audited, not
regenerated; refusal rate does not by itself measure correctness.
