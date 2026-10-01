# Generative AI use log

This working log supports completion of the official assessment AI declaration.
The group must review it, add any other AI use by members and follow the current
Canvas submission instructions.

## 1 October 2026: Demo repository handoff

**Tool:** OpenAI Codex

The project leader asked Codex to bring the existing FinTrace demo into the
official WIL repository, preserve earlier assessment files, update installation
instructions, run migration checks and link the resulting evidence from Trello.
Codex copied the tracked release, updated repository and download references,
and performed regression and integrity checks. This was a packaging and
verification task, not a new independent evaluation or a rewrite of the answer
pipeline. Details and limitations are in `fintrace/docs/WIL_MIGRATION.md`.

This entry covers the repository handoff only. The group still needs to review
and record the full AI assistance used during development and evaluation in its
final Condition 3 declaration. The existing Milestone 1 declaration is historical,
not a completed declaration for the final submission.

## 22 August 2026: Preliminary Walert reproduction

**Tool:** OpenAI Codex

**Purpose and prompts:** The project leader asked Codex to help reproduce Walert,
create credible preliminary evidence for Milestone 1 and work with the team's
private GitHub repository.

**What Codex helped with:**

- It inspected the public Walert repository, source code, datasets and saved runs.
- It proposed and generated a Python BM25 evaluation script.
- It generated unit tests and instructions for running the script.
- It ran the script against official Walert files and calculated retrieval and
  refusal metrics.
- It drafted the first version of the results explanation and README changes.
- It helped integrate the changes into Git after checking the remote branch.

**What we checked:**

- The input files came from `https://github.com/rmit-ir/walert` at commit
  `9417518ade245771b2d4f1ad919b840cecb2876e`.
- The evaluator saved SHA-256 hashes for each input file.
- Three unit tests passed, the full script completed successfully and the
  generated results were committed to the repository.
- The documentation states that we did not rerun the full Falcon-7B and Pyserini
  pipeline.
- Team members must inspect the code and results, decide whether to use them, and
  revise the final assessment wording in accordance with the current policy.

## 23 August 2026: Milestone 1 planning and report preparation

**Tool:** OpenAI Codex

**Purpose and prompts:** The project leader asked Codex to help refine the
tentative finance RAG concept, explain technical choices, allocate specific team
roles, organise the next three-week plan and prepare a two-page Milestone 1
report from information confirmed by the group.

**What Codex helped with:**

- It compared possible finance use cases and helped frame FinTrace as a bounded
  question-answering and financial-verification project.
- It suggested a tentative aim, stakeholder description, technical roles,
  work packages, definitions of done and project risks.
- It explained Walert, Falcon-7B, RAG, retrieval metrics and local model options
  in plain language for team discussion.
- It drafted and formatted the two-page report using member details, links,
  contribution percentages and project confirmations supplied by the leader.
- It updated the repository README with the confirmed six-member table and
  generated an editable Word file and PDF for group review.

**What we accepted, rejected or revised:**

- The leader confirmed all names, student IDs, GitHub usernames, the tentative
  FinTrace direction, equal contribution allocation and project links.
- Unsupported claims that other members had completed technical work were not
  included. Their technical responsibilities are described as planned work for
  the next sprint.
- FinTrace remains labelled tentative because it has not yet received final
  mentor approval.
- The report retains the limitation that only the BM25 baseline was rebuilt;
  the complete Falcon-7B and Pyserini pipeline was not rerun.
- All members must review the final wording, verify the numerical results and
  complete the official Condition 3 declaration before submission.
