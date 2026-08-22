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

The 96 known and inferred questions have an answer key showing which passages are
relevant. The remaining 10 questions are outside the knowledge base. We used them
to check whether a system says it cannot answer instead of guessing.

## Independently executed BM25 baseline

| Question subset | Questions | MRR | nDCG@5 | Relevant evidence in top 5 |
|---|---:|---:|---:|---:|
| Known | 84 | 0.6674 | 0.4245 | 82.14% |
| Inferred | 12 | 0.4547 | 0.3798 | 66.67% |
| All answerable | 96 | 0.6408 | 0.4190 | 80.21% |

These results came from the BM25 implementation in this repository. The system
worked better on known questions than inferred questions. Relevant evidence was
15.47 percentage points less likely to appear in the top five for an inferred
question.

## Results calculated from Walert's saved retrieval runs

All 96 answerable questions are included in the denominator, including questions
for which a system returned no result.

| Supplied run | Queries with results | MRR | nDCG@5 | Hit@5 |
|---|---:|---:|---:|---:|
| Walert BM25 | 96/96 | 0.6029 | 0.4553 | 77.08% |
| Walert dense | 96/96 | 0.6845 | 0.5383 | 71.88% |
| Walert intent | 72/96 | 0.5729 | 0.1957 | 57.29% |

The saved dense run has the strongest graded ranking score, but it does not have
the best Hit@5. This shows why we need more than one measure. The intent system's
MRR would rise to 0.7639 if we counted only the 72 questions where it returned a
result. We kept all 96 questions in the calculation so missing results were not
hidden.

## Checking questions outside the knowledge base

| Supplied system/output | Retrieved contexts | Refused | Unanswered rate |
|---|---:|---:|---:|
| Intent system | 1 | 8/10 | 80% |
| BM25 + Falcon | 1 | 1/10 | 10% |
| BM25 + Falcon | 3 | 2/10 | 20% |
| BM25 + Falcon | 5 | 2/10 | 20% |
| Dense + Falcon | 1 | 0/10 | 0% |
| Dense + Falcon | 3 | 1/10 | 10% |
| Dense + Falcon | 5 | 1/10 | 10% |

For these questions, saying that there is not enough information is the safer
response. Walert's saved generative answers often attempted an answer even though
the knowledge base did not contain one. This is why FinTrace will have an
`Unable to verify` result and will test whether the system knows when to stop.

## Milestone 1 summary

We rebuilt and evaluated a Walert-style BM25 search baseline and calculated
metrics from Walert's official saved results. We did not rerun the full Falcon-7B
and Pyserini pipeline. Our baseline achieved 80.21% Hit@5 across 96 answerable
questions. Walert's saved generative outputs refused only 0-20% of the 10
questions outside the knowledge base. Based on this result, FinTrace will test
evidence retrieval and the decision not to answer as separate behaviours.

## How to reproduce the result

Detailed machine-readable results, input hashes and the generated TREC run are in
`results/`. Run the command in `README.md` to regenerate them. Metric definitions:

- **MRR:** rewards placing the first relevant passage near rank 1.
- **nDCG@5:** rewards ranking highly relevant passages near the top, using graded
  relevance.
- **Hit@5:** percentage of questions with at least one relevant passage in the
  first five results.
- **Unanswered rate:** percentage of out-of-KB questions labelled as a refusal.

Limitations:

- Our BM25 tokenizer is simpler than the original Lucene analyzer.
- We checked the supplied dense and Falcon files but did not regenerate them.
- Refusal rate alone does not show whether the answers that were given were
  correct.
