"""Lookup wording must not let a model veto checked numerical retrieval."""
import sys
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from answer_bank_conversational import Backend, direct_numeric_lookup
from bank_conversation import followup
from bank_ui_scope import resolve_scope
from bank_query_routing import normalise_query, definition_request


class NumericLookupRoutingTests(unittest.TestCase):
    def test_lookup_variants_bypass_a_wrong_model_classification(self):
        questions = (
            'what is CBA profit in year 2025',
            'What was CBA profit in FY2025?',
            "What's NAB cash profit in FY2024?",
            'whats CBA profit in 2025',
            'What are NAB total assets in FY2025?',
            'How much statutory profit did CBA report in 2024?',
            'Show NAB customer deposits for FY2025',
            'List CBA cash profit and statutory profit in FY2025',
            'CBA 2025 profit?',
            'tell me NAB profit in 2024',
            'Could you please show me CBA proift fy25?',
            'How did NAB net interest margin change from FY2024 to FY2025?',
            resolve_scope('What is profit?', {'company': 'CBA', 'year': '2025'})['effective_question'],
        )
        for question in questions:
            with self.subTest(question=question):
                core = Mock()
                core.answer.return_value = {
                    'answer': {'status': 'source_bound_answer', 'parts': []},
                    'generation': {'status': 'skipped'},
                }
                backend = Backend(core)
                backend.use_cba_reports = True
                backend.intent_planner = Mock()
                backend.intent_planner.plan.return_value = {
                    'topic': 'unsupported', 'task': 'comparison', 'status': 'interpreted',
                }
                with patch('bank_report_library.get_library') as library:
                    library.return_value.unmatched_subject.return_value = []
                    result = backend.answer(question)
                backend.intent_planner.plan.assert_not_called()
                core.answer.assert_called_once_with(normalise_query(question)[0])
                self.assertEqual(result['answer']['status'], 'source_bound_answer')
                self.assertEqual(result['question'], question)

    def test_not_a_keyword_override_for_narrative_or_definitions(self):
        for question in (
            'What is cash profit?',
            'What is the difference between cash and statutory profit in FY2025?',
            'What was driving CBA profit in 2025?',
            'What was the reason for CBA profit growth in 2025?',
            'What is CBA profit telling us about its strategy in 2025?',
            'What sector is CBA investing more in 2025?',
        ):
            with self.subTest(question=question):
                self.assertFalse(direct_numeric_lookup(question))

    def test_definition_forms_do_not_become_amounts(self):
        for question in ('What is NIM?', 'What does cash profit mean?', 'Define NAB cash earnings',
                         'What is the difference between cash profit and statutory profit?'):
            self.assertTrue(definition_request(question), question)

    def test_normalisation_never_fuzzily_changes_distinct_measures(self):
        for question in ('CBA housing lending 2025', 'NAB net interest income 2024',
                         'Westpac underlying profit FY2026', 'CBA Project Helios budget',
                         'NAB individually assessed impairment 2025'):
            self.assertEqual(normalise_query(question), (question, []))

    def test_normalisation_is_visible_and_idempotent(self):
        question = "whats commbank statutroy proift fy25"
        text, changes = normalise_query(question)
        self.assertEqual(text, 'what is CBA statutory profit FY2025')
        self.assertTrue(changes)
        self.assertEqual(normalise_query(text), (text, []))

    def test_standalone_lookup_never_inherits_investment_subject(self):
        question = 'what is CBA profit in year 2025'
        self.assertEqual(followup(question, 'What sector is CBA investing more in 2025'), (question, []))

    def test_explicit_guards_are_not_bypassed(self):
        for question in (
            'What is Westpac profit in year 2025?',
            'What is CBA profit next year and will it keep growing?',
            'NAB profit FY26?',
            'CBA proift FY23?',
        ):
            with self.subTest(question=question):
                core = Mock()
                backend = Backend(core)
                backend.use_cba_reports = True
                backend.intent_planner = Mock()
                result = backend.answer(question)
                self.assertEqual(result['answer']['status'], 'unable_to_verify')
                core.answer.assert_not_called()
                backend.intent_planner.plan.assert_not_called()


if __name__ == '__main__':
    unittest.main()
