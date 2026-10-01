"""Broad performance questions use prose evidence, not an invented metric."""
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from bank_narrative_routing import narrative_decision, narrative_evidence, relevant_sections
from bank_research_answer import render_research, ResearchClient
from answer_bank_release import EvidenceBackend


def section(text, uid='performance', bank='CBA', year=2025):
    return {'source': {'company': bank, 'report_year': year, 'document_title': 'Synthetic report', 'pdf_page': 1},
            'heading': 'Annual results', 'excerpts': [{'source_id': uid, 'quote': text}]}


class PerformanceResearchTests(unittest.TestCase):
    def test_broad_paraphrases_are_research_not_metric_clarification(self):
        for q in ['Choose a major change in CBA\u2019s financial performance',
                  'Highlight a notable financial change at NAB in FY2025',
                  'Summarise CBA financial performance in 2025',
                  'Give me CBA earnings highlights FY2024',
                  'Explain the key changes in NAB results in FY2025']:
            with self.subTest(q=q):
                d = narrative_decision(q)
                self.assertEqual(d['status'], 'search')
                self.assertEqual(d['topic'], 'performance')
                self.assertTrue(all(r['topic'] == 'performance' for r in d['requests']))

    def test_specific_numeric_request_unchanged(self):
        for q in ['Calculate CBA cash profit growth FY2025',
                  'CBA financial performance: what was statutory NPAT FY2025?',
                  'NAB underlying profit FY2025']:
            with self.subTest(q=q):
                self.assertIsNone(narrative_decision(q))

    def test_unsupported_period_or_bank_still_stops(self):
        for q in ['Choose a major change in Westpac financial performance in 2025',
                  'Summarise NAB financial performance FY2026']:
            self.assertEqual(narrative_decision(q)['status'], 'unable_to_verify')

    def test_missing_year_uses_available_years_separately(self):
        d = narrative_decision('Choose a major change in CBA financial performance')
        self.assertEqual({r['year'] for r in d['requests']}, {2024, 2025})
        self.assertEqual({r['company'] for r in d['requests']}, {'CBA'})

    def test_movement_and_financial_measure_required(self):
        q = 'Choose a major change in CBA financial performance FY2025'
        d = narrative_decision(q)
        good = section('Cash profit increased, supported by higher operating income.')
        noise = [section('Profit is a financial measure.', 'definition'),
                 section('Executive remuneration increased with profit.', 'remuneration'),
                 section('New technology initiatives improved customer service.', 'strategy'),
                 section('Cash profit increased.', 'wrongbank', bank='NAB'),
                 section('Cash profit increased.', 'wrongyear', year=2024)]
        self.assertEqual(relevant_sections(noise + [good], d, q), [good])

    def fixture(self):
        q = 'Choose a major change in CBA financial performance FY2025'
        return narrative_evidence(q, narrative_decision(q), lambda query: {'answer': {
            'source_excerpts': [section('Cash profit increased, supported by higher operating income.')]}})

    def test_evidence_has_performance_not_investment_caveats(self):
        result = self.fixture()
        self.assertEqual(result['answer']['status'], 'partial_answer')
        self.assertIn('financial changes', result['answer']['message'])
        self.assertNotIn('received the most money', result['answer']['message'])
        self.assertNotIn('investment areas', ' '.join(result['answer']['limitations']))

    def test_empty_retrieval_is_honest_non_answer_not_clarification(self):
        q = 'Choose a major change in CBA financial performance FY2025'
        result = narrative_evidence(q, narrative_decision(q), lambda _: {'answer': {}})
        self.assertEqual(result['answer']['status'], 'unable_to_verify')
        self.assertIn('does not establish', result['answer']['message'])

    def test_backend_calls_narrative_retriever(self):
        core = Mock()
        with patch('answer_bank_release.NarrativeEvidence.answer', return_value={'answer': {
                'source_excerpts': [section('Cash profit increased.')]}}) as retrieve:
            result = EvidenceBackend(core).answer('Choose a major change in CBA financial performance FY2025')
        self.assertEqual(result['narrative_request']['topic'], 'performance')
        core.answer.assert_not_called()
        self.assertTrue(retrieve.call_args.args[1].startswith('Explain'))

    def test_offline_fallback_keeps_literal_change_with_citation(self):
        client = Mock()
        client.config = {'model': 'fixture', 'max_evidence_bytes': 10500}
        client.generate_research.side_effect = OSError('offline')
        result = render_research(self.fixture(), client)
        self.assertIn('Cash profit increased', result['answer']['message'])
        self.assertIn('PDF page 1', result['answer']['message'])
        self.assertNotIn('investment ranking', result['answer']['message'])
        self.assertIn('A reported financial change to examine:', result['answer']['message'])
        self.assertNotIn('could not safely summarise all', result['answer']['message'])

    def test_generation_receives_selection_not_ranking_instruction(self):
        client = ResearchClient.__new__(ResearchClient)
        client.config = {'model': 'fixture', 'model_digest': 'digest', 'output_tokens': 900}
        client.request = Mock(return_value={'models': [{'name': 'fixture', 'digest': 'digest'}]})
        client.chat = Mock(return_value=({'statements': []}, {}))
        client.generate_research('Choose a major change', [], [{'topic': 'performance'}], [])
        prompt = client.chat.call_args.args[0]
        self.assertIn('choose ONE', prompt)
        self.assertIn('cash/statutory', prompt)
        self.assertIn('not a ranking', prompt)

    def test_incomplete_review_is_visible_not_just_internal_metadata(self):
        client = Mock()
        client.config = {'model': 'fixture', 'max_evidence_bytes': 10500}
        client.generate_research.return_value = (
            {'statements': [{'text': 'CBA cash profit increased in FY2025.', 'evidence_ids': ['E1']}]},
            {'supported': [True], 'complete': False, 'reason': 'Only one part is covered.'}, {})
        result = render_research(self.fixture(), client)
        self.assertEqual(result['generation']['status'], 'generated')
        self.assertIn('partial answer', ' '.join(result['answer']['important_notes']))

    def test_support_review_gets_only_each_claims_cited_evidence(self):
        from bank_generation_v11 import evidence_cards
        client = ResearchClient.__new__(ResearchClient)
        client.config = {'model': 'fixture', 'model_digest': 'digest', 'output_tokens': 900}
        client.request = Mock(return_value={'models': [{'name': 'fixture', 'digest': 'digest'}]})
        draft = {'statements': [{'text': 'CBA cash profit increased in FY2025.', 'evidence_ids': ['E1']}]}
        client.chat = Mock(side_effect=[(draft, {}), ({'supported': [True], 'complete': True, 'reason': 'Supported.'}, {})])
        cards = evidence_cards({'source_excerpts': [section('Cash profit increased.', uid='correct'),
                                                   section('Unrelated technology initiative.', uid='noise')]})
        client.generate_research('Explain CBA profit FY2025', cards, [{'topic': 'performance'}], [])
        review_payload = client.chat.call_args.args[1]
        self.assertEqual([c['id'] for c in review_payload['claims'][0]['cited_evidence']], ['E1'])
        self.assertNotIn('evidence', review_payload)


if __name__ == '__main__':
    unittest.main()
