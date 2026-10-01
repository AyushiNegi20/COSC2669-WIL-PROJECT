# Wording robustness review

This is developer-authored regression testing, not an independent accuracy
assessment. The runtime does not read the question families or their results.

## What changed

Recognised numerical questions no longer depend on an LLM approving their
opening words. Short requests, present/past wording and polite requests use the
same checked evidence path. Limited, explicit spelling corrections and short
financial years are recorded visibly in the response. FY26 is treated as FY2026
and rejected as outside the corpus, not silently replaced with a default year.

Numerical binding considers all indexed financial rows matching the bank and
metric. Similarity ranking no longer decides which required table rows the
binder is allowed to inspect. The strict row, native-number, period, basis,
scope, conflict and report-version checks remain. Nothing adds new documents,
financial values or evaluation answers to the runtime.

Definitions remain separate from amounts. Mixed questions preserve the numeric
and explanation branches. A fallback explanation cannot be labelled a complete
answer just because the numerical branch succeeded.

## Method

The protocol in `eval/wording/cases.py` covers all 13 supported measures, both
banks and both financial years. There are 52 canonical lookups and 156 wording
variants, plus eight canonical calculations and 16 calculation variants. A
further 26 cases check scope refusals, typos, company aliases, UI defaults,
filter overrides and follow-ups. Six additional cases exercise definitions,
explanations and mixed requests with the pinned local Qwen3 8B model.

Numerical comparisons check metric, bank, period, unit, basis, scope, report
version, value and calculated output. Empty responses cannot pass just because
both variants are empty. Citations must be present. Matching the canonical
response is evidence of wording consistency, not proof that the canonical
answer itself is financially correct.

Narrative rows are deliberately marked `needs_manual_review` by the runner.
Evidence presence is not a semantic-correctness score. The observations below
come from developer inspection of the returned claims and source excerpts, not
model self-review or a new independent reading of every PDF.

## First attempts are retained

The first numerical run passed 248 of 256 checks. Eight checks failed around
NAB FY2024 operating expenses and CBA cash-profit/NIM changes. Ordinary wording
changed the ranked candidate rows enough to omit required cells or compatible
comparison operands. The system refused or returned partial figures rather
than inventing missing values. Those failures motivated structural numeric
candidate selection; their summary is retained as `first_numeric_summary.json`.

After that repair, 256 numerical checks passed. Review of the six narrative
outputs found a completeness-label defect when a mixed answer used fallback
excerpts. That label and explicit out-of-scope short years received a final
repair and a new full run. `final_summary.json` preserves the final run's
case-level assessments and before/after integrity results.

## Narrative limitations

Final run: 258/258 numerical, equivalence and guard checks passed. Code/data
integrity was unchanged before and after. The maintained Python suite passed
549 tests and the frontend suite passed 10 tests.

Developer review of the final six narrative outputs:

| Case | Outcome |
| --- | --- |
| CBA cash-profit definition | Generated definition supported by the returned disclosure, PDF page 17. |
| NAB cash-earnings definition | Generated definition supported by the returned disclosures, PDF pages 9 and 82. |
| CBA staff-expense reasons | Relevant source-selected passage, plus broader operating-expense context. |
| NAB staff-expense reasons | Relevant source-selected passage, plus broader operating-expense context. |
| CBA profit plus explanation | Correctly labelled numerical alternatives; fallback excerpts and partial status. Not a complete causal explanation. |
| NAB profit plus explanation | Correctly labelled numerical alternatives; fallback excerpts and partial status. Not a complete causal explanation. |

Do not turn these results into a combined 264/264 accuracy claim. In particular,
the two mixed requests did not produce a successful generated explanation.

The definition and staff-expense cases retrieved directly relevant disclosures.
Staff-expense answers can additionally include a broader operating-expense
paragraph; that separately labelled context is not a component-only answer.
Mixed profit/reason questions can fall back to lengthy report excerpts and do
not reliably provide a concise, complete explanation of the overall change.
They are now explicitly partial when generation falls back. Source selection
and quoted evidence are not equivalent to unrestricted conversational reasoning.

Latency varies with cold model loading and GPU contention. The maintained
35-second timeout applies to individual model requests, not necessarily to a
whole answer that includes several stages. Do not promise all answers within
35 seconds or treat fallback excerpts as successful generated explanations.

## Reproduction and isolation

Run `python tools/evaluate_wording.py --stage all` in the configured retrieval
environment with Ollama available. Raw first responses are preserved under
`reports/runs/wording-<timestamp>/`; summaries and the final six narrative
responses are included here for review.

A separate evaluator edited cross-company scope rules during development. The
integrity gate detected that change. This release was tested in an isolated
worktree using the original cross-company policy, and those separate edits and
evaluation files were left untouched. No assessment of that combined version
is implied. Before another independent run, use the exact pushed commit and
verify its manifest; do not test a concurrently changing working tree.
