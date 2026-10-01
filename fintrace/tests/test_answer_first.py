from pathlib import Path
import sys
import unittest
from unittest.mock import Mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from bank_answer_first import numeric_alternatives
from bank_narrative_routing import narrative_decision, narrative_evidence, relevant_sections
from bank_research_answer import ResearchClient, supported_statements, render_research
from bank_generation_v11 import evidence_cards
from test_narrative_routing import section


def numeric_reply(question):
    return {'question': question, 'answer': {'status': 'source_bound_answer',
            'parts': [{'claims': [{'text': 'synthetic'}]}]}}


class AnswerFirstTests(unittest.TestCase):
    def test_yearless_profit_returns_available_years(self):
        core = Mock(side_effect=numeric_reply)
        result = numeric_alternatives('CBA profit?', core)
        self.assertEqual(core.call_count, 2)
        self.assertIn('FY2024', core.call_args_list[0].args[0])
        self.assertIn('FY2025', core.call_args_list[1].args[0])
        self.assertIn('No year', result['answer']['message'])

    def test_bankless_profit_returns_both_banks(self):
        core = Mock(side_effect=numeric_reply)
        result = numeric_alternatives('profit FY2025?', core)
        self.assertEqual(core.call_count, 2)
        self.assertIn('For CBA', core.call_args_list[0].args[0])
        self.assertIn('For NAB', core.call_args_list[1].args[0])
        self.assertEqual(result['answer']['status'], 'source_bound_answer')

    def test_explicit_context_does_not_change(self):
        core = Mock()
        self.assertIsNone(numeric_alternatives('CBA profit FY2025?', core))
        core.assert_not_called()

    def test_two_explicit_years_not_duplicated(self):
        core = Mock(side_effect=numeric_reply)
        numeric_alternatives('profit FY2024 and FY2025?', core)
        self.assertEqual(core.call_count, 2)

    def test_missing_alternative_is_not_hidden(self):
        core = Mock(side_effect=[numeric_reply('a'), {'answer': {'status': 'unable_to_verify', 'message': 'No evidence'}}])
        result = numeric_alternatives('CBA profit?', core)
        self.assertEqual(result['answer']['status'], 'partial_answer')
        self.assertIn('No evidence', result['answer']['limitations'])

    def test_no_implicit_arithmetic_operands_or_current_year(self):
        for question in ('CBA profit last year', 'CBA profit today', 'CBA profit from 100 to 200',
                         'CBA profit minus expenses', 'CBA profit 2026'):
            self.assertIsNone(numeric_alternatives(question, Mock()), question)

    def test_yearless_growth_labels_window(self):
        core = Mock(side_effect=numeric_reply)
        result = numeric_alternatives('CBA profit growth?', core)
        self.assertEqual(core.call_count, 1)
        self.assertIn('comparison window', result['answer']['message'])

    def test_lending_filters_fees_and_funding_not_destinations(self):
        question = 'Which lending sector is CBA investing in FY2025?'
        decision = narrative_decision(question)
        good = section('Home loans and business loans contributed to asset growth.', uid='portfolio')
        noise = [section('Lending fees increased.', uid='fees'),
                 section('Customer deposits funded lending growth.', uid='funding'),
                 section('Home loans impairment expense increased.', uid='impairment'),
                 section('Non-lending interest earning assets increased.', uid='nonlending')]
        selected = relevant_sections(noise + [good], decision, question)
        self.assertEqual(selected, [good])

    def test_excludes_half_year_for_full_year(self):
        bad = section('Home loans increased.'); bad['heading'] = 'Half Year Ended June'
        decision = narrative_decision('CBA lending sectors FY2025')
        self.assertFalse(relevant_sections([bad], decision, 'CBA lending sectors FY2025'))

    def test_followup_is_bounded_when_first_search_fails(self):
        core = Mock(return_value={'answer': {'source_excerpts': []}})
        decision = narrative_decision('CBA investment priorities FY2025')
        result = narrative_evidence('CBA investment priorities FY2025', decision, core)
        self.assertEqual(core.call_count, 2)
        self.assertEqual(result['answer']['status'], 'unable_to_verify')
        self.assertEqual(len(result['research_searches']), 2)

    def fixture(self):
        evidence = narrative_evidence('CBA lending sectors FY2025', narrative_decision('CBA lending sectors FY2025'),
            lambda q: {'answer': {'source_excerpts': [section('Home loans increased.', uid='loans')]}})
        cards = evidence_cards(evidence['answer'])
        draft = {'statements': [{'text': 'CBA FY2025 reported growth in home loans.', 'evidence_ids': ['E1']}]}
        review = {'supported': [True], 'complete': False, 'reason': 'No industry breakdown.'}
        return evidence, cards, draft, review

    def test_supported_partial_statement_survives_incomplete_review(self):
        evidence, cards, draft, review = self.fixture()
        self.assertEqual(supported_statements(draft, review, cards, evidence['question']), draft['statements'])

    def test_unsupported_statement_not_displayed(self):
        evidence, cards, draft, review = self.fixture()
        review['supported'] = [False]
        self.assertFalse(supported_statements(draft, review, cards, evidence['question']))

    def test_no_invented_citation_or_amount(self):
        evidence, cards, draft, review = self.fixture()
        draft['statements'][0]['evidence_ids'] = ['E999']
        with self.assertRaises(ValueError): supported_statements(draft, review, cards, evidence['question'])
        draft['statements'][0]['evidence_ids'] = ['E1']
        draft['statements'][0]['text'] = 'CBA FY2025 home loans increased by $900 million.'
        with self.assertRaises(ValueError): supported_statements(draft, review, cards, evidence['question'])

    def test_no_unscoped_claim_or_largest_ranking(self):
        evidence, cards, draft, review = self.fixture()
        for text in ('Home loans increased.', 'CBA FY2025 invested most in home loans.'):
            draft['statements'][0]['text'] = text
            self.assertFalse(supported_statements(draft, review, cards, evidence['question']))

    def test_render_partial_answer_and_bank_year_citations(self):
        evidence, cards, draft, review = self.fixture()
        client = Mock(); client.config = {'model': 'fixture', 'max_evidence_bytes': 10500}
        client.generate_research.return_value = draft, review, {}
        result = render_research(evidence, client)
        self.assertEqual(result['generation']['status'], 'generated')
        self.assertEqual(result['answer']['status'], 'partial_answer')
        self.assertIn('PDF page 1', result['answer']['message'])
        self.assertIn('not a complete borrower-industry breakdown', result['answer']['message'])

    def test_offline_keeps_useful_literal_evidence(self):
        evidence, cards, draft, review = self.fixture()
        client = Mock(); client.config = {'model': 'fixture', 'max_evidence_bytes': 10500}
        client.generate_research.side_effect = OSError('offline')
        result = render_research(evidence, client)
        self.assertIn('Home loans increased.', result['answer']['message'])
        self.assertEqual(result['generation']['status'], 'fallback')

    def test_discarded_alternative_is_reported_not_silently_omitted(self):
        evidence, cards, draft, review = self.fixture()
        evidence['research_coverage'].append({'company': 'CBA', 'year': 2025, 'topic': 'spending', 'sections': 1})
        client = Mock(); client.config = {'model': 'fixture', 'max_evidence_bytes': 10500}
        client.generate_research.return_value = draft, review, {}
        result = render_research(evidence, client)
        self.assertIn('CBA FY2025 (spending)', result['answer']['message'])
        self.assertIn('could not be produced', result['answer']['message'])

    def test_research_review_has_exact_count_and_short_reason(self):
        evidence, cards, draft, review = self.fixture()
        client = ResearchClient.__new__(ResearchClient)
        client.config = {'model': 'fixture', 'model_digest': 'digest', 'output_tokens': 900}
        client.request = Mock(return_value={'models': [{'name': 'fixture', 'digest': 'digest'}]})
        client.chat = Mock(side_effect=[(draft, {}), (review, {})])
        client.generate_research(evidence['question'], cards, evidence['research_coverage'], [])
        schema = client.chat.call_args.args[2]
        self.assertEqual(schema['properties']['supported']['minItems'], 1)
        self.assertEqual(schema['properties']['supported']['maxItems'], 1)
        self.assertEqual(schema['properties']['reason']['maxLength'], 180)

    def test_one_scope_repair_before_review_not_after_rejection(self):
        evidence, cards, draft, review = self.fixture()
        bad = {'statements': [{'text': 'CBA FY2025 reported growth in home loans and other assets.', 'evidence_ids': ['E1']}]}
        client = ResearchClient.__new__(ResearchClient)
        client.config = {'model': 'fixture', 'model_digest': 'digest', 'output_tokens': 900}
        client.request = Mock(return_value={'models': [{'name': 'fixture', 'digest': 'digest'}]})
        client.chat = Mock(side_effect=[(bad, {}), (draft, {}), (review, {})])
        client.generate_research(evidence['question'], cards, evidence['research_coverage'], [])
        self.assertEqual(client.chat.call_count, 3)
        self.assertIn('Omit non-lending assets', client.chat.call_args_list[1].args[1]['formatting_error'])


if __name__ == '__main__': unittest.main()
