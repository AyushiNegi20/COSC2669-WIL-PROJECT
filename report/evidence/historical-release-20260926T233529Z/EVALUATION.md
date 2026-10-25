# Independent release evaluation — FinTrace demo candidate

- **Commit:** `aa7fef9b82ade8f13bdfacb448008c69be7aabfe` (tag `demo-eval-candidate-2026-09-27`)
- **Entry point:** `serve_fintrace_demo.build_backend()` via sanctioned runner `tools/evaluate_release_candidate.py`; model Qwen3 8B, `config/demo_local8b.json`.
- **Integrity:** `bank_integrity` verified clean **before and after** (unchanged). Working tree clean. No edits made.
- **Questions:** 24 fresh, independently authored mentor-style questions, written before reading the developer's regression cases, kept outside the repo. Full responses in `reports/runs/release-20260926T233529Z`.

## Release verdict: PASS — approved for the demo, leave unchanged

No wrong financial figures, no wrong reporting bases, no misleading citations, no crashes, and no reproducible failure of an essential capability. Per the handoff's block criteria, none are present. Ship as frozen.

## Taxonomy

**Serious financial errors / misleading citations: 0.** Every stated figure is correct with the right basis, scope, unit, page and vintage. Profit ambiguity returns labelled cash + statutory alternatives for both banks (D01, D10). Year-on-year changes are computed correctly (dividend +20/+4.3%, cash profit +416/+4.2%, impairment -76/-9.5%, NIM +0.03pp, deposits +57,130/+6.7%). Vintage is disclosed on comparatives (D09, D20).

**Correct and sufficiently complete (~12):** D01, D02, D03, D04, D08, D09, D10, D11, D12, D14, D19, plus D23 (ROE, grounded and correct at 13.5%).

**Partial / over-refusal on answerable content (gaps, not errors):**
- D06 cost-to-income → clean over-refusal (45.7% is in the report). Documented gap.
- D13 "why did NAB opex rise" → gave the figures and change, not the drivers.
- D15 capital strength → on-topic CET1-movement commentary but no headline 12.35% → 11.70%.
- D07 cash-basis definition → grounded, cited, but definition-adjacent (could be crisper).
- D05 investment → correct category data (Productivity & growth 1,023 largest; Infrastructure +128 biggest increase) but verbose and also surfaces out-of-window FY2023.

**Correct handling of genuinely unavailable / out-of-scope:** D16 cross-company, D17 prediction, D18 FY2023 out-of-range, D21 out-of-universe, D22 advice, D24 live share price — all clean, graceful, no fabrication.

**Timing / errors / fallbacks:** 0 runtime errors, 0 model/excerpt fallbacks this run. One timing outlier: D08 ~178s (~3 min); D07 35s, D01 21s; most numeric answers <1s. The slow synthesis answers are a demo-smoothness risk, not a correctness issue.

## Note on my own earlier finding
An earlier pass of mine used the bare `answer_bank_conversational.Backend()`, which the handoff warns is under-configured. Four "demo-breaking" symptoms I reported then (profit footnote, investment miss, total-loans miss, capital-topic miss) **did not reproduce** on the correctly-configured `build_backend()` path. They were entry-point artifacts.

## Non-blocking suggestions (not required for release)
Left for after the demo, not conditions of this pass: trim the D08 timing outlier; close the cost-to-income coverage gap; make "why opex" and capital-strength answers give drivers / headline figures; tighten the investment answer to the requested year.
