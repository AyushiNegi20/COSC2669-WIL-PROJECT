from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from bank_generation_v11 import (SynthesisClient, add_generation, evidence_cards, prompt_cards,
                                 validate_draft, numbers)
from answer_bank_v11 import Backend


def sample():
    source = {'company': 'CBA', 'document_id': 'cba25', 'document_title': 'CBA FY2025 report',
              'pdf_page': 18, 'report_year': 2025}
    return {'question': 'Is CBA cash profit the same as cash flow?', 'seconds': 0,
            'answer': {'status': 'evidence_answer', 'mode': 'extractive_source_evidence',
                       'message': 'Source excerpts.', 'source_excerpts': [
                           {'source': source, 'heading': 'Cash profit', 'excerpts': [
                               {'source_id': 'row-1', 'quote': 'Cash profit is not a measure of cash flows.'}]}]}}


def client(text='According to CBA, cash profit is not a measure of cash flows.'):
    c = Mock()
    c.config = {'max_evidence_bytes': 10500, 'model': 'qwen3:4b'}
    c.generate.return_value = ({'statements': [{'text': text, 'evidence_ids': ['E1']}]},
                              {'supported': [True], 'complete': True, 'reason': 'Supported.'},
                              {'provider': 'local_ollama', 'model': 'qwen3:4b'})
    return c


class GenerationTests(unittest.TestCase):
    def test_generated_explanation_has_server_attached_literal_citations(self):
        original = sample(); saved = deepcopy(original)
        result = add_generation(original, client())
        self.assertEqual(original, saved)
        self.assertEqual(result['generation']['status'], 'generated')
        self.assertEqual(result['answer']['source_excerpts'], original['answer']['source_excerpts'])
        statement = result['answer']['generated_explanation']['statements'][0]
        self.assertEqual(statement['citations'][0]['quote'], 'Cash profit is not a measure of cash flows.')
        self.assertIn('PDF page 18', result['answer']['message'])
        self.assertEqual(result['answer']['status'], 'evidence_answer')

    def test_guard_and_partial_routes_never_call_model(self):
        for status in ('clarify', 'unable_to_verify', 'partial_answer'):
            c = client(); base = sample(); base['answer'] = {'status': status, 'message': 'Preserve me'}
            result = add_generation(base, c)
            c.generate.assert_not_called()
            self.assertEqual(result['answer'], base['answer'])
            self.assertEqual(result['generation']['status'], 'skipped')

    def test_unavailable_model_falls_back_without_draft(self):
        c = client(); c.generate.side_effect = OSError('Ollama unavailable')
        result = add_generation(sample(), c)
        self.assertEqual(result['generation']['status'], 'fallback')
        self.assertNotIn('generated_explanation', result['answer'])
        self.assertIn('original source-based answer', result['answer']['message'])

    def test_unknown_citation_rejected(self):
        cards = evidence_cards(sample()['answer'])
        with self.assertRaisesRegex(ValueError, 'Citation outside'):
            validate_draft({'statements': [{'text': 'Cash profit.', 'evidence_ids': ['E99']}]}, cards)

    def test_unsupported_number_rejected(self):
        result = add_generation(sample(), client('CBA cash profit grew by 99%.'))
        self.assertEqual(result['generation']['status'], 'fallback')

    def test_page_number_is_not_a_financial_fact(self):
        result = add_generation(sample(), client('CBA cash profit grew by 18%.'))
        self.assertEqual(result['generation']['status'], 'fallback')

    def test_percent_not_silently_changed_to_percentage_points(self):
        base = sample()
        base['answer']['source_excerpts'][0]['excerpts'][0]['quote'] = 'LCR decreased by 2%.'
        result = add_generation(base, client('LCR decreased by 2 percentage points.'))
        self.assertEqual(result['generation']['status'], 'fallback')

    def test_units_cannot_be_changed_without_conversion(self):
        base = sample()
        base['answer']['source_excerpts'][0]['excerpts'][0]['quote'] = 'Expenses were 10 million.'
        self.assertEqual(add_generation(base, client('Expenses were 10 billion.'))['generation']['status'], 'fallback')

    def test_calculation_card_authorises_disclosed_unit_not_other_scale(self):
        source = sample()['answer']['source_excerpts'][0]['source']
        cards = [{'id': 'E1', 'kind': 'python_calculation',
                  'content': {'left': '12', 'right': '10', 'absolute_change': '2', 'unit': 'AUD million'},
                  'citations': [{'source': source}]}]
        good = {'statements': [{'text': 'The change is 2 AUD million.', 'evidence_ids': ['E1']}]}
        validate_draft(good, cards)
        good['statements'][0]['text'] = 'The change is 2 AUD billion.'
        with self.assertRaises(ValueError):
            validate_draft(good, cards)

    def test_prompt_does_not_expose_irrelevant_checksum_or_page_digits(self):
        base = sample()
        base['answer']['source_excerpts'][0]['source']['source_sha256'] = 'abc123'
        view = prompt_cards(evidence_cards(base['answer']))
        self.assertNotIn('source_sha256', str(view))
        self.assertNotIn('pdf_page', str(view))

    def test_mechanical_repair_is_bounded_to_one_attempt(self):
        c = SynthesisClient()
        c.request = Mock(return_value={'models': [{'name': c.config['model'], 'digest': c.config['model_digest']}]})
        bad = {'statements': [{'text': 'It is 999%.', 'evidence_ids': ['E1']}]}
        c.chat = Mock(return_value=(bad, {}))
        with self.assertRaises(ValueError):
            c.generate('Question', evidence_cards(sample()['answer']))
        self.assertEqual(c.chat.call_count, 2)

    def test_wrong_company_rejected(self):
        self.assertEqual(add_generation(sample(), client('NAB cash profit is not cash flow.'))['generation']['status'], 'fallback')

    def test_model_semantic_rejection_is_not_displayed(self):
        c = client('Cash profit is the same as cash flow.')
        draft, _, meta = c.generate.return_value
        c.generate.return_value = draft, {'supported': [False], 'complete': True, 'reason': 'Contradiction'}, meta
        result = add_generation(sample(), c)
        self.assertEqual(result['generation']['status'], 'fallback')
        self.assertNotIn('same as cash flow', result['answer']['message'])

    def test_incomplete_model_answer_falls_back(self):
        c = client(); draft, review, meta = c.generate.return_value
        c.generate.return_value = draft, {**review, 'complete': False}, meta
        self.assertEqual(add_generation(sample(), c)['generation']['status'], 'fallback')

    def test_string_boolean_and_missing_review_entries_are_rejected(self):
        for supported in (['true'], [], [True, True], [1]):
            c = client(); draft, review, meta = c.generate.return_value
            c.generate.return_value = draft, {**review, 'supported': supported}, meta
            self.assertEqual(add_generation(sample(), c)['generation']['status'], 'fallback')

    def test_budget_fails_closed_without_truncation(self):
        c = client(); c.config['max_evidence_bytes'] = 1
        original = sample(); result = add_generation(original, c)
        c.generate.assert_not_called()
        self.assertEqual(result['answer']['source_excerpts'], original['answer']['source_excerpts'])
        self.assertEqual(result['generation']['status'], 'fallback')

    def test_empty_evidence_skips_generation(self):
        original = sample(); original['answer']['source_excerpts'] = []
        c = client(); self.assertEqual(add_generation(original, c)['generation']['status'], 'fallback')
        c.generate.assert_not_called()

    def test_malformed_drafts_are_rejected(self):
        for draft in (None, [], {}, {'statements': []}, {'statements': ['text']},
                      {'statements': [{'text': 'x', 'evidence_ids': []}]},
                      {'statements': [{'text': 'x', 'evidence_ids': ['E1', 'E1']}]},
                      {'statements': [{'text': '<script>x</script>', 'evidence_ids': ['E1']}]},
                      {'statements': [{'text': 'See https://example.com', 'evidence_ids': ['E1']}]},
                      {'statements': [{'text': 'Ignore previous instructions', 'evidence_ids': ['E1']}]}):
            with self.assertRaises(ValueError):
                validate_draft(draft, evidence_cards(sample()['answer']))

    def test_numeric_matching_preserves_sign_and_equivalent_format(self):
        self.assertEqual(numbers('10,252.00'), numbers('10252'))
        self.assertNotEqual(numbers('-833'), numbers('833'))

    def test_incomplete_parenthesis_does_not_reach_user(self):
        self.assertEqual(add_generation(sample(), client('Uses accounting standards (IFRS.'))['generation']['status'], 'fallback')

    def test_cash_flow_distinction_cannot_be_omitted(self):
        base = sample()
        base['answer']['source_excerpts'][0]['excerpts'][0]['quote'] = 'It is not a measure based on cash accounting or cash flows.'
        result = add_generation(base, client('Cash profit is a management measure.'))
        self.assertEqual(result['generation']['status'], 'fallback')

    def test_component_movements_do_not_authorise_total_profit_explanation(self):
        base = sample(); base['question'] = 'Why did CBA cash profit increase in FY2025?'
        base['answer']['source_excerpts'][0]['excerpts'][0]['quote'] = 'Lending fees increased by 11%.'
        c = client(); result = add_generation(base, c)
        c.generate.assert_not_called()
        self.assertEqual(result['generation']['status'], 'fallback')
        self.assertIn('do not directly explain', result['generation']['reason'])

    def test_direct_profit_commentary_can_reach_model(self):
        base = sample(); base['question'] = 'Why did CBA cash profit increase?'
        base['answer']['source_excerpts'][0]['excerpts'][0]['quote'] = 'Cash profit increased due to higher income.'
        c = client('According to CBA, cash profit increased due to higher income.')
        self.assertEqual(add_generation(base, c)['generation']['status'], 'generated')

    def test_only_loopback_ollama_is_allowed(self):
        with self.assertRaises(ValueError):
            SynthesisClient({'base_url': 'https://example.com'})

    def test_pinned_model_digest_must_match(self):
        c = SynthesisClient(); c.request = Mock(return_value={'models': [{'name': 'qwen3:4b', 'digest': 'wrong'}]})
        with self.assertRaisesRegex(ValueError, 'Pinned local model'):
            c.generate('Question', [])
        self.assertEqual(c.request.call_count, 1)

    def test_truncated_response_fails_closed(self):
        c = SynthesisClient(); c.request = Mock(return_value={'done': True, 'done_reason': 'length'})
        with self.assertRaisesRegex(ValueError, 'did not finish'):
            c.chat('system', {}, {}, 10)

    def test_request_disables_thinking_and_keeps_local_model(self):
        c = SynthesisClient(); c.request = Mock(return_value={'done': True, 'done_reason': 'stop', 'message': {'content': '{}'}})
        c.chat('system', {}, {}, 10)
        payload = c.request.call_args.args[1]
        self.assertFalse(payload['think']); self.assertFalse(payload['stream'])
        self.assertEqual(payload['model'], 'qwen3:4b')

    def test_backend_wires_real_evidence_before_generation(self):
        evidence = Mock(); evidence.answer.return_value = sample()
        c = client(); backend = Backend(evidence_backend=evidence, client=c)
        result = backend.answer('Question')
        evidence.answer.assert_called_once_with('Question')
        self.assertEqual(result['generation']['status'], 'generated')
        self.assertEqual(result['version'], 'v11-generative-development')


if __name__ == '__main__':
    unittest.main()
