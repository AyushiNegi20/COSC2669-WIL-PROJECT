# Generative AI use log

This working log supports completion of the official assessment AI declaration.
The group must review it, add any other AI use by members and follow the current
Canvas submission instructions.

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
