# Generative AI use log

This working log supports completion of the official assessment AI declaration.
The group must review it, add any other AI use by members and follow the current
Canvas submission instructions.

## 22 August 2026 — preliminary Walert reproduction

**Tool:** OpenAI Codex

**Purpose and prompts:** The project leader asked Codex to help reproduce Walert,
create credible preliminary evidence for Milestone 1 and work with the team's
private GitHub repository.

**AI-assisted outputs:**

- inspected the public Walert repository, source code, datasets and saved runs;
- proposed and generated a standard-library BM25 reproduction/evaluation script;
- generated unit tests and reproducibility documentation;
- calculated retrieval and out-of-knowledge-base refusal metrics by executing the
  script against official Walert artifacts;
- drafted a concise results interpretation and updated the project README; and
- assisted with Git integration after checking that remote teammate work would
  not be overwritten.

**Verification and human responsibility:**

- Inputs came from `https://github.com/rmit-ir/walert` at commit
  `9417518ade245771b2d4f1ad919b840cecb2876e`.
- The evaluator saved SHA-256 hashes for every upstream input.
- Three unit tests passed, the full script completed successfully and the
  generated results were committed to the repository.
- The full Falcon-7B/Pyserini pipeline was not claimed as independently rerun;
  that limitation is stated in the documentation.
- Team members must inspect the code and results, decide whether to use them, and
  revise the final assessment wording in accordance with the current policy.
