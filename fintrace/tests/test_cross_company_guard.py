"""Regression test for the cross-company scope guard.

The project scope states that cross-company ranking and equivalence across CBA
and NAB are not supported. An independent fresh-question evaluation
(eval/fresh_qa_v1) found that a cross-company question ("Did CBA or NAB have the
higher net interest margin in FY2025?") was answered with source-bound cells
instead of being declined.

The pre-model guard bank_contract_v12.preflight() is what answer_bank_v12
consults before any expansion or model call (see answer_bank_v12.py). This test
pins the guard so the behaviour cannot silently regress: any question naming
both issuers must be blocked, while single-company and within-company
comparison questions must still pass through.
"""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from bank_contract_v12 import preflight
from answer_bank_release import cross_company

# Both guard entry points must agree: the v12-core pre-model guard (preflight)
# and the deployed release-layer guard (cross_company).
BLOCKED = [
    'Did CBA or NAB have the higher net interest margin in FY2025?',
    'Which bank had higher profit in FY2025, CBA or NAB?',
    'Compare CBA and NAB net interest margin in FY2025.',
    "Is CBA's cash earnings bigger than NAB's in FY2025?",
    "How does CBA's CET1 ratio compare to NAB's in FY2024?",
    'Rank Commonwealth Bank and National Australia Bank by total assets in FY2025.',
    "Is NAB's cash earnings definition the same as CommBank's?",
]
ALLOWED = [
    'What was CBA net interest margin in FY2025?',
    'What was NAB cash earnings in FY2025?',
    "Compare why CBA's loan impairment expense changed in FY2024 versus FY2025.",
    'How much did NAB gross loans grow in FY2025?',
    'What was CBA full-year dividend per share in FY2025?',
    'What does cash earnings mean?',
]


class CrossCompanyGuardTests(unittest.TestCase):
    def test_preflight_blocks_cross_company(self):
        for question in BLOCKED:
            with self.subTest(question=question):
                reason = preflight(question)
                self.assertIsNotNone(reason, 'cross-company question must be declined')
                self.assertIn('scope', reason.lower())

    def test_release_layer_blocks_cross_company(self):
        for question in BLOCKED:
            with self.subTest(question=question):
                self.assertTrue(cross_company(question), 'deployed answer path must decline cross-company')

    def test_single_and_within_company_not_blocked(self):
        # In scope and must not be caught by the cross-company guard at either layer.
        for question in ALLOWED:
            with self.subTest(question=question):
                self.assertIsNone(preflight(question), 'in-scope question must pass preflight')
                self.assertFalse(cross_company(question), 'in-scope question must pass release guard')


if __name__ == '__main__':
    unittest.main()
