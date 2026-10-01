from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from answer_bank_simplified import Backend, split_mixed
from test_contract_v12 import bound
from test_generation_v11 import sample, client


class SimplifiedTests(unittest.TestCase):
    def test_numeric_payload_unchanged_and_client_not_called(self):
        original = bound(); evidence = Mock(); evidence.answer.return_value = original
        model = Mock()
        result = Backend(evidence, model).answer(original['question'])
        self.assertEqual(result['answer'], original['answer'])
        self.assertEqual(result['route'], 'numeric'); self.assertEqual(result['generation']['status'], 'skipped')
        model.generate.assert_not_called()
        self.assertEqual(original, bound())

    def test_numeric_does_not_even_construct_generation_client(self):
        evidence = Mock(); evidence.answer.return_value = bound()
        with patch('answer_bank_simplified.ContractSynthesisClient') as constructor:
            Backend(evidence).answer('CBA cash profit FY2025?')
            constructor.assert_not_called()

    def test_guard_never_calls_model(self):
        for status in ('unable_to_verify', 'clarify'):
            evidence = Mock(); evidence.answer.return_value = {'question': 'q', 'answer': {'status': status, 'message': 'Keep me'}}
            model = Mock(); result = Backend(evidence, model).answer('q')
            self.assertEqual(result['answer']['message'], 'Keep me'); model.generate.assert_not_called()

    def test_partial_numbers_remain_partial(self):
        original = bound(); original['answer']['status'] = 'partial_answer'
        original['answer']['limitations'] = ['Second requested year is missing.']
        evidence = Mock(); evidence.answer.return_value = original; model = Mock()
        result = Backend(evidence, model).answer('CBA cash profit FY2025?')
        self.assertEqual(result['answer'], original['answer']); model.generate.assert_not_called()

    def test_narrative_still_generates(self):
        evidence = Mock(); evidence.answer.return_value = sample(); model = client()
        result = Backend(evidence, model).answer(sample()['question'])
        self.assertEqual(result['route'], 'narrative'); self.assertEqual(result['generation']['status'], 'generated')
        model.generate.assert_called_once()

    def test_narrative_failure_keeps_literal_evidence(self):
        evidence = Mock(); evidence.answer.return_value = sample(); model = client(); model.generate.side_effect = OSError('offline')
        result = Backend(evidence, model).answer(sample()['question'])
        self.assertEqual(result['generation']['status'], 'fallback')
        self.assertEqual(result['answer']['source_excerpts'], sample()['answer']['source_excerpts'])

    def test_mixed_preserves_figures_and_separate_narrative(self):
        numeric = bound(); narrative = sample(); evidence = Mock(); evidence.answer.side_effect = [numeric, narrative]
        model = client(); question = 'How much did CBA cash profit change in FY2025, and why?'
        result = Backend(evidence, model).answer(question)
        self.assertEqual(result['route'], 'mixed')
        self.assertEqual(result['answer']['parts'], numeric['answer']['parts'])
        self.assertEqual(result['answer']['source_excerpts'], narrative['answer']['source_excerpts'])
        model.generate.assert_called_once()
        cards = model.generate.call_args.args[1]
        self.assertTrue(all(c['kind'] == 'report_excerpt' for c in cards))

    def test_mixed_missing_explanation_not_marked_complete(self):
        evidence = Mock(); evidence.answer.side_effect = [bound(), {'answer': {'status': 'unable_to_verify', 'message': 'No explanation'}}]
        model = Mock(); result = Backend(evidence, model).answer('How much did CBA cash profit grow FY2025 and why?')
        self.assertEqual(result['answer']['status'], 'partial_answer'); model.generate.assert_not_called()
        self.assertTrue(result['answer']['parts'])

    def test_unsplit_mixed_request_cannot_hide_missing_explanation(self):
        evidence = Mock(); evidence.answer.return_value = bound(); model = Mock()
        result = Backend(evidence, model).answer('Why did CBA cash profit change and by how much?')
        self.assertEqual(result['answer']['status'], 'partial_answer'); model.generate.assert_not_called()

    def test_mixed_fallback_excerpts_do_not_claim_complete_explanation(self):
        evidence = Mock(); evidence.answer.side_effect = [bound(), sample()]
        model = client(); model.generate.side_effect = OSError('offline')
        result = Backend(evidence, model).answer('What is CBA cash profit in FY2025 and why?')
        self.assertEqual(result['generation']['status'], 'fallback')
        self.assertEqual(result['answer']['status'], 'partial_answer')
        self.assertTrue(result['answer']['parts'])
        self.assertTrue(result['answer']['source_excerpts'])

    def test_narrative_suffix_is_not_discarded(self):
        result = split_mixed('What was CBA profit FY2025; explain how cash differs from statutory?')
        self.assertIn('cash differs from statutory', result[1])
        self.assertIsNone(split_mixed('What does cash profit mean and why is it different from cash flow?'))

    def test_both_profit_alternatives_preserved(self):
        numeric = bound(); numeric['answer']['parts'] += bound('statutory_npat', 'statutory')['answer']['parts']
        evidence = Mock(); evidence.answer.return_value = numeric
        result = Backend(evidence, Mock()).answer('CBA profit FY2025?')
        self.assertEqual(len(result['answer']['parts']), 2)

    def test_all_metric_families_keep_calculations_untouched(self):
        from bank_source_cells import LABELS
        for metric in LABELS:
            original = bound(metric); original['answer']['parts'][0]['calculations'] = [{'operation':'fixture', 'absolute_change':'-1.25', 'unit':'percent', 'basis_points':'-125'}]
            evidence = Mock(); evidence.answer.return_value = original; model = Mock()
            result = Backend(evidence, model).answer('Give the annual change in the requested figure.')
            self.assertEqual(result['answer'], original['answer'], metric); model.generate.assert_not_called()


if __name__ == '__main__': unittest.main()
