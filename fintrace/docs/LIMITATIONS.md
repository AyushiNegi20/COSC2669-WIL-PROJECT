# Known limitations

- Ambiguous CBA investment questions can use the checked internal-spending
  table, explicitly distinguished from lending by industry. Largest spending,
  largest annual increase and fastest percentage growth are different answers.
  The local intent planner can still route some phrasings to prose instead.
- The checked numerical path supports a bounded metric catalogue. It does not
  understand every number in the PDFs. Narrative quotations may contain other
  disclosed figures; these are not new verified calculations.
- Additional checked NAB statement and reconciliation tables extend that
  catalogue. This is not a universal table parser. In particular, a requested
  parent-company figure or a specific note may still lack validated operands.
  Prose questions are not limited to the numerical catalogue, but retrieval and
  passage selection can still miss or incompletely answer a question.
- Narrative answers select literal report passages. They can include extra
  context, omit relevant evidence, or be lengthy instead of conversational.
- Subject/scope relevance screens reject known mismatches before ranking,
  selection and fallback display. They are conservative rules, not proof of
  semantic correctness or completeness. A related passage can still be partial.
- Plain annual movement questions about FY2025 can be interpreted as comparison
  with FY2024. The response discloses this assumption. Missing-year requests
  still show the available report years rather than silently choosing a new year.
- An unqualified total-loans lookup may show the explicitly labelled gross-loans
  measure as an alternative, never claim gross and net loans are identical.
- Definitions use model paraphrasing and automated checks, not independent
  verification. Source citations should still be reviewed.
- Prose search covers the six reports' extractable text, not all image-only
  content. Unvalidated tables are not calculation-ready.
- CBA ends its financial year in June and NAB in September. Explicit questions
  naming both banks are currently declined by a cross-company guard. Test
  each bank separately; do not promise a cross-bank comparison capability.
- Multi-year answers can use a later report's restated comparative to keep a
  calculation on the same reporting basis. The answer discloses that vintage;
  it can differ from the figure originally published for the earlier year.
- Cold model/index startup is slower than warm responses. This is a local,
  single-user research demo, not a deployed multi-user service.
- No prediction of future returns or personalised investment recommendation is
  supported. A missing answer does not prove the full report lacks information.
