from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from bank_contract_v12 import prepare, preflight, metric_tags, audit_bindings, Planner
from answer_bank_v12 import Backend, EvidenceBackend, validate_generated_labels


def bound(metric='cash_profit', basis='cash'):
    source = {'company': 'CBA', 'document_title': 'Test report', 'pdf_page': 2,
              'document_id': 'test', 'report_year': 2025}
    cell = {'metric': metric, 'basis': basis, 'company': 'CBA', 'value': '100', 'unit': 'AUD million',
            'scope': 'continuing', 'period_end': '2025-06-30', 'report_year': 2025,
            'source': source, 'source_id': 'row1'}
    return {'question': 'What was CBA cash profit FY2025?', 'answer': {'status': 'source_bound_answer', 'parts': [
        {'request': {'metric': metric, 'company': 'CBA', 'value_years': [2025], 'scope': 'continuing', 'report_year': 2025},
         'claims': [{'text': 'CBA cash profit was 100 AUD million in FY2025.', 'cell': cell,
                     'evidence': [{'source': source, 'source_id': 'row1', 'quote': 'Cash profit 100'}]}],
         'calculations': [], 'issues': []}]}}


class ContractTests(unittest.TestCase):
    def test_unspecified_profit_returns_both(self):
        for term in ('profit', 'net profit', 'NPAT', 'earnings'):
            q, notes = prepare(f'What was NAB {term} in FY2025?')
            self.assertEqual(metric_tags(q), {'cash_profit', 'statutory_npat'})
            self.assertTrue(notes)

    def test_cash_npat_stays_cash(self):
        q, _ = prepare('CBA cash NPAT from continuing operations in FY2025')
        self.assertEqual(metric_tags(q), {'cash_profit'})
        self.assertEqual(metric_tags(prepare('CBA NPAT on a cash basis FY2025')[0]), {'cash_profit'})

    def test_explicit_basis_not_expanded(self):
        for text, metric in [('statutory profit', 'statutory_npat'), ('cash profit', 'cash_profit')]:
            self.assertEqual(metric_tags(prepare(f'CBA {text} FY2025')[0]), {metric})

    def test_unsupported_components_and_other_companies_block_before_model(self):
        for text in ('Westpac profit FY2025', 'NAB housing loans FY2025', 'NAB mortgage lending FY2024',
                     'CBA net interest income FY2025', 'NAB individually assessed credit impairment charge',
                     'NAB collectively assessed impairment expense', 'NAB share price in September 2025',
                     'CBA cash and cash equivalents FY2025', 'CBA statutory EPS FY2025',
                     'CBA dividend paid in FY2025', 'NAB average assets FY2025', 'NAB profit before income tax FY2025'):
            with self.subTest(text=text): self.assertIsNotNone(preflight(text))

    def test_supported_not_blocked(self):
        for text in ('NAB credit impairment charge FY2025', 'CBA net interest margin FY2025',
                     'CBA cash profit same as cash flow?', 'NAB gross loans FY2025',
                     'CBA dividend per share FY2025'):
            self.assertIsNone(preflight(text), text)

    def test_yoy_percent_and_previous_year_interpretation_explicit(self):
        q, notes = prepare('How much did CBA profit grow in FY2025?')
        self.assertIn('FY2024', q); self.assertIn('percentage change', q)
        self.assertTrue(any('preceding' in n for n in notes))

    def test_explicit_absolute_only_not_overridden(self):
        q, _ = prepare('NAB cash profit change FY2024 to FY2025, absolute only')
        self.assertNotIn('percentage change', q)

    def test_unspecified_eps_and_margin_expose_supported_basis(self):
        for term in ('EPS', 'NIM'):
            _, notes = prepare(f'CBA {term} FY2025')
            self.assertTrue(notes)

    def test_binding_contract_checks_all_fields(self):
        self.assertEqual(audit_bindings(bound()), [])
        for field, bad in [('metric', 'statutory_npat'), ('basis', 'statutory'), ('company', 'NAB'),
                           ('scope', 'including_discontinued'), ('period_end', '2024-06-30'), ('report_year', 2024)]:
            r = bound(); r['answer']['parts'][0]['claims'][0]['cell'][field] = bad
            self.assertTrue(audit_bindings(r), field)

    def test_semantic_nearest_metric_is_not_a_contract(self):
        planner = Planner.__new__(Planner)
        planner.base = Mock()
        planner.base.plan.return_value = {'behavior': 'answer', 'intent': 'find', 'requests': [{'metric': 'gross_loans'}],
            'metrics': ['gross_loans'], 'constraints': {}, 'value_years': [2025]}
        # Exercise the guard with the inherited planning function replaced only in this test.
        from unittest.mock import patch
        with patch('bank_contract_v12.PreviousPlanner.plan', return_value=planner.base.plan.return_value):
            result = planner.plan('What is NAB the mystery amount FY2025?', None)
        self.assertEqual(result['behavior'], 'abstain')

    def test_generation_cannot_relabel_a_valid_cell(self):
        r = bound()
        for text in ('CBA statutory profit was 100 AUD million.', 'CBA housing lending was 100 AUD million.',
                     'CBA profit was 100 AUD million.'):
            r['answer']['generated_explanation'] = {'statements': [{'text': text, 'evidence_ids': ['E1']}]}
            with self.assertRaises(ValueError): validate_generated_labels(r)
        r['answer']['generated_explanation']['statements'][0]['text'] = 'CBA cash profit was 100 AUD million.'
        validate_generated_labels(r)

    def test_model_self_approval_does_not_override_label_failure(self):
        original = bound(); evidence = Mock(); evidence.answer.return_value = deepcopy(original)
        client = Mock(); client.config = {'model': 'test', 'max_evidence_bytes': 10000}
        client.generate.return_value = ({'statements': [{'text': 'CBA statutory profit was 100 AUD million.', 'evidence_ids': ['E1']}]},
            {'supported': [True], 'complete': True, 'reason': 'Yes'}, {})
        result = Backend(evidence_backend=evidence, client=client).answer(original['question'])
        self.assertEqual(result['generation']['status'], 'fallback')
        self.assertNotIn('generated_explanation', result['answer'])
        self.assertEqual(result['answer']['parts'], original['answer']['parts'])

    def test_report_year_not_treated_as_value_year(self):
        from unittest.mock import patch
        p = {'behavior': 'answer', 'intent': 'compare', 'report_year': 2025, 'value_years': [2024,2025],
             'requests': [{'metric': 'operating_income', 'value_years': [2024,2025]}]}
        planner = Planner.__new__(Planner)
        with patch('bank_contract_v12.PreviousPlanner.plan', return_value=p):
            result = planner.plan('In NAB FY2025 report what FY2024 net operating income comparative is shown?', None)
        self.assertEqual(result['value_years'], [2024]); self.assertEqual(result['intent'], 'find')

    def test_different_original_years_not_reinterpreted_as_same_period(self):
        backend = EvidenceBackend.__new__(EvidenceBackend)
        self.assertIsNone(backend.vintage_answer('Compare NAB cash profit originally reported in FY2024 with the FY2025 report.'))

    def test_segment_qualifier_cannot_hide_inside_total_label(self):
        self.assertIsNotNone(preflight('What were NAB total gross housing loans in FY2025?'))

    def test_nim_generation_must_label_basis(self):
        r = bound('nim', 'cash')
        r['answer']['generated_explanation'] = {'statements': [{'text': 'CBA net interest margin was 100 percent.', 'evidence_ids': ['E1']}]}
        with self.assertRaises(ValueError): validate_generated_labels(r)
        r['answer']['generated_explanation']['statements'][0]['text'] = 'CBA cash net interest margin was 100 percent.'
        validate_generated_labels(r)

    def test_generation_must_cover_both_requested_profit_measures(self):
        r = bound(); statutory = bound('statutory_npat', 'statutory')['answer']['parts'][0]
        r['answer']['parts'].append(statutory)
        r['answer']['generated_explanation'] = {'statements': [{'text': 'CBA cash profit was 100 AUD million.', 'evidence_ids': ['E1']}]}
        with self.assertRaisesRegex(ValueError, 'omitted'): validate_generated_labels(r)


if __name__ == '__main__': unittest.main()
