"""Period coverage and predictions remain safe, explicit and model-free."""
import sys
from pathlib import Path
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from answer_bank_conversational import Backend
from bank_query_routing import reporting_limit
from bank_retrieval_v5 import query_plan


class ReportingLimitsTests(unittest.TestCase):
    def answer(self, question):
        core = Mock()
        backend = Backend(core)
        backend.intent_planner = Mock()
        result = backend.answer(question)
        core.answer.assert_not_called()
        backend.intent_planner.plan.assert_not_called()
        self.assertEqual(result['answer']['status'], 'unable_to_verify')
        self.assertEqual(result['generation']['status'], 'skipped')
        self.assertFalse(result['answer'].get('parts'))
        self.assertTrue(all(not p['citations'] for p in result['presentation']['paragraphs']))
        return result

    def test_predictions_explain_evidence_limit(self):
        for bank in ('CBA', 'NAB'):
            for question in (
                f'What will {bank}\u2019s profit be in FY2026?',
                f'Predict {bank} profit in FY26',
                f'What is the forecast for {bank} profit next year?',
                f'What will {bank} dividend be in FY2026?',
                f'What will {bank} earn next year?',
            ):
                with self.subTest(question=question):
                    result = self.answer(question)
                    self.assertIn("can't reliably predict", result['answer']['message'])
                    self.assertIn('historical results', result['answer']['message'])
                    self.assertIn('alone do not establish', result['answer']['limitations'][0])
                    self.assertIn('prediction rather than', result['interpretation']['notes'][0])
                    self.assertTrue(result['presentation']['qualifications'])

    def test_historical_coverage_is_not_prediction(self):
        for question in (
            'What was CBA profit in FY2026?',
            'What is NAB cash earnings in FY26?',
            'CBA profit FY2023?',
            'Will you show CBA profit in FY2026?',
        ):
            with self.subTest(question=question):
                result = self.answer(question)
                self.assertIn('outside the FY2024 and FY2025 reports', result['answer']['message'])
                self.assertIn('unpublished or unknowable', result['answer']['limitations'][0])
                self.assertNotIn("can't reliably predict", result['answer']['message'])

    def test_other_guards_and_supported_years_are_unchanged(self):
        for question in ('Westpac profit FY2026', 'What was CBA profit in FY2025?',
                         'What was NAB dividend in FY2024?', 'What is CBA share price today?'):
            with self.subTest(question=question):
                self.assertIsNone(reporting_limit(question, query_plan(question)))


if __name__ == '__main__':
    unittest.main()
