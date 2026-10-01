from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from answer_bank_release import (Backend, EvidenceBackend, conceptual, excluded_terms,
                                 supported_remainder, statement_request, validate_statement)
from test_contract_v12 import bound


class ReleaseTests(unittest.TestCase):
    def test_distinct_quantities_block_before_core(self):
        for bank in ('CBA', 'NAB'):
            for year in ('2024', '2025'):
                for term in ('underlying profit', 'adjusted earnings', 'normalised NPAT',
                             'credit rating', 'income tax expense', 'tax paid'):
                    with self.subTest(bank=bank, year=year, term=term):
                        core = Mock()
                        result = EvidenceBackend(core).answer(f'What was {bank} {term} FY{year}?')
                        self.assertEqual(result['answer']['status'], 'unable_to_verify')
                        core.answer.assert_not_called()

    def test_named_supported_terms_are_not_excluded(self):
        for term in ('cash profit', 'statutory NPAT', 'credit impairment charge', 'net interest margin'):
            self.assertFalse(excluded_terms('NAB '+term+' FY2024'))

    def test_generic_profit_still_uses_frozen_alternatives(self):
        core = Mock(); original = bound()
        original['answer']['parts'] += bound('statutory_npat', 'statutory')['answer']['parts']
        core.answer.return_value = original
        result = EvidenceBackend(core).answer('CBA profit FY2025?')
        self.assertEqual(result['answer'], original['answer'])
        core.answer.assert_called_once_with('CBA profit FY2025?')

    def test_conceptual_forms_and_numeric_negatives(self):
        for q in ('Is underlying profit the same as cash earnings?',
                  'What is the difference between NIM and net interest income?',
                  'How does cash profit differ from statutory profit?', 'Define cash profit'):
            self.assertTrue(conceptual(q), q)
        for q in ('How much did cash profit change?', 'Calculate the difference in profit',
                  'What was the difference in NAB cash profit from FY2024 to FY2025?',
                  'What is the difference in NAB cash profit between FY2024 and FY2025?'):
            self.assertFalse(conceptual(q), q)

    def test_definition_no_year_gate_or_numeric_substitution(self):
        core = Mock()
        with patch('answer_bank_release.NarrativeEvidence.answer', return_value=bound()):
            result = EvidenceBackend(core).answer('Is NAB underlying profit the same as cash earnings?')
        self.assertEqual(result['answer']['status'], 'unable_to_verify')
        self.assertNotIn('parts', result['answer']); core.answer.assert_not_called()

    def test_definition_requires_excluded_concept_in_real_quotes(self):
        response = {'answer': {'status': 'evidence_answer', 'source_excerpts': [
            {'excerpts': [{'quote': 'Cash earnings is an adjusted measure.'}]}]}}
        with patch('answer_bank_release.NarrativeEvidence.answer', return_value=response):
            result = EvidenceBackend(Mock()).answer('Is NAB underlying profit the same as cash earnings?')
        self.assertEqual(result['answer']['status'], 'unable_to_verify')

    def test_definition_with_source_evidence_survives(self):
        response = {'answer': {'status': 'evidence_answer', 'source_excerpts': [
            {'excerpts': [{'quote': 'Net interest margin is net interest income divided by average interest earning assets.'}]}]}}
        with patch('answer_bank_release.NarrativeEvidence.answer', return_value=deepcopy(response)):
            result = EvidenceBackend(Mock()).answer('What is the difference between NAB NIM and net interest income?')
        self.assertEqual(result['answer'], response['answer'])

    def test_partial_shared_context_list_keeps_supported_part(self):
        for q in ('What were NAB net interest income and cash earnings FY2025?',
                  'Give CBA cash profit and income tax expense FY2024.'):
            core = Mock(); core.answer.return_value = bound()
            model = Mock()
            result = Backend(EvidenceBackend(core), model).answer(q)
            self.assertEqual(result['answer']['status'], 'partial_answer')
            self.assertEqual(result['answer']['parts'], bound()['answer']['parts'])
            self.assertTrue(result['answer']['unanswered_parts'])
            self.assertEqual(result['generation']['status'], 'skipped'); model.generate.assert_not_called()

    def test_no_partial_operand_or_cross_context_guess(self):
        for q in ('Compare NAB underlying profit and cash earnings FY2025',
                  'Calculate NAB net interest income minus cash earnings FY2025',
                  'CBA underlying profit FY2024 and NAB cash profit FY2025',
                  'NAB underlying profit FY2024 and cash earnings FY2025'):
            self.assertIsNone(supported_remainder(q, excluded_terms(q)), q)

    def test_income_statement_sets_basis_before_lookup(self):
        for bank in ('CBA', 'NAB'):
            q = f'What were {bank} operating expenses in the FY2024 income statement?'
            core = Mock(); core.answer.return_value = bound('operating_expenses', 'statutory')
            result = EvidenceBackend(core).answer(q)
            self.assertIn('Statutory basis.', core.answer.call_args.args[0])
            self.assertEqual(result['answer']['parts'], core.answer.return_value['answer']['parts'])

    def test_cash_cell_cannot_pass_statement_gate(self):
        result = validate_statement(bound('operating_expenses', 'cash'), 'NAB income statement operating expenses FY2025')
        self.assertEqual(result['answer']['status'], 'unable_to_verify')
        self.assertNotIn('parts', result['answer'])

    def test_statement_conflicting_basis_stops(self):
        query, reason = statement_request('CBA cash operating expenses in the income statement FY2025')
        self.assertIsNone(query); self.assertTrue(reason)

    def test_other_bank_conceptual_is_not_bypassed(self):
        core = Mock()
        result = EvidenceBackend(core).answer('Define Westpac underlying profit')
        self.assertEqual(result['answer']['status'], 'unable_to_verify'); core.answer.assert_not_called()

    def test_unchanged_numbers_and_calcs_no_generation(self):
        from bank_source_cells import LABELS
        for metric in LABELS:
            original = bound(metric)
            original['answer']['parts'][0]['calculations'] = [{'operation': 'fixture', 'absolute_change': '-1'}]
            core = Mock(); core.answer.return_value = original; model = Mock()
            result = Backend(EvidenceBackend(core), model).answer('CBA supported measure FY2025')
            self.assertEqual(result['answer'], original['answer'], metric); model.generate.assert_not_called()

    def test_invalid_input(self):
        for q in (None, '', ' ', 'a'*2001):
            with self.assertRaises(ValueError): EvidenceBackend(Mock()).answer(q)


if __name__ == '__main__': unittest.main()
