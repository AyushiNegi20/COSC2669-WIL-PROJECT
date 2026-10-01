from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from bank_narrative_routing import narrative_decision, narrative_evidence, relevant_sections
from answer_bank_release import EvidenceBackend, Backend


def section(text='The bank invested in technology to improve customer service.', bank='CBA', year=2025, uid='fixture:unit'):
    return {'source': {'company': bank, 'report_year': year, 'document_title': 'Synthetic report', 'pdf_page': 1},
            'heading': 'Priorities', 'excerpts': [{'source_id': uid, 'quote': text}]}


class NarrativeRoutingTests(unittest.TestCase):
    def test_ambiguous_investment_searches_labelled_alternatives(self):
        for bank in ('CBA', 'NAB', 'Commonwealth Bank'):
            for phrase in ('which sector {b} is investing more in 2025',
                           'which direction {b} is investing more in 2025',
                           'Where did {b} invest in FY2025?',
                           'Where is {b} putting more money in 2025?'):
                decision = narrative_decision(phrase.format(b=bank))
                self.assertEqual(decision['status'], 'search')
                self.assertEqual({r['topic'] for r in decision['requests']}, {'spending', 'lending'})
                self.assertIn('Both interpretations', ' '.join(decision['notes']))

    def test_strategy_paraphrases_reach_search(self):
        for question in ("What were CBA's investment priorities in FY2025?",
                         'What did NAB focus on in 2024?',
                         'Summarise CBA strategic initiatives in 2025',
                         'Tell me about NAB digital investment in 2025',
                         'Which lending sectors did CBA discuss in 2024?'):
            with self.subTest(question=question):
                self.assertEqual(narrative_decision(question)['status'], 'search')

    def test_numeric_and_existing_definition_questions_unchanged(self):
        for question in ('CBA profit FY2025?', 'What was NAB NIM in 2024?',
                         'Calculate CBA cash profit growth from 2024 to 2025',
                         'Define cash profit', 'What were NAB gross loans in 2025?'):
            self.assertIsNone(narrative_decision(question), question)

    def test_missing_context_uses_labelled_available_reports(self):
        result = narrative_decision('What were investment priorities in 2025?')
        self.assertEqual({r['company'] for r in result['requests']}, {'CBA', 'NAB'})
        result = narrative_decision('What were CBA investment priorities?')
        self.assertEqual({r['year'] for r in result['requests']}, {2024, 2025})
        self.assertTrue(result['notes'])

    def test_out_of_scope_precedes_investment_clarification(self):
        for question in ('Where was Westpac investing in 2025?',
                         'Where is CBA investing in 2026?',
                         'Predict NAB investment priorities next year',
                         'Should I invest in CBA in 2025?'):
            self.assertEqual(narrative_decision(question)['status'], 'unable_to_verify', question)

    def test_amount_not_substituted_with_other_metric(self):
        for question in ('How much did CBA spend on technology in 2025?',
                         'Calculate NAB investment spending growth in 2025'):
            self.assertTrue(narrative_decision(question)['amount_requested'])

    def test_comparative_intent_is_preserved(self):
        decision = narrative_decision('Which CBA technology initiatives received more investment in 2025?')
        self.assertTrue(decision['comparative'])

    def test_no_cross_bank_or_year_guess(self):
        for question in ('Compare CBA and NAB investment priorities in 2025',
                         'Compare CBA investment priorities in 2024 and 2025'):
            result = narrative_decision(question)
            self.assertEqual(result['status'], 'search')
            self.assertGreater(len(result['requests']), 1)

    def test_relevance_and_provenance_filters(self):
        question = 'What were CBA investment priorities in 2025?'
        decision = narrative_decision(question)
        source = section()
        sections = [section(bank='NAB'), section(year=2024),
                    section('Cash profit increased.', uid='irrelevant'), source, source]
        self.assertEqual(relevant_sections(sections, decision, question), [source])

    def test_specific_topic_must_be_in_source_not_only_heading(self):
        question = 'What were CBA AI investment priorities in 2025?'
        decision = narrative_decision(question)
        wrong = section(); wrong['heading'] = 'AI priorities'
        correct = section('The bank discussed artificial intelligence investment.', uid='ai')
        self.assertEqual(relevant_sections([wrong, correct], decision, question), [correct])

    def test_source_units_are_not_cut_to_budget(self):
        source = section('Technology investment ' + 'text ' * 1500)
        decision = narrative_decision('CBA technology priorities 2025')
        self.assertFalse(relevant_sections([source], decision, 'CBA technology priorities 2025'))

    def test_specific_expense_does_not_take_total_cost_explanation(self):
        question = 'Why did CBA technology service expenses rise in FY2025?'
        decision = narrative_decision(question, topic_hint='spending')
        broad = section('Operating expenses increased due to wages and technology investment.', uid='total')
        narrow = section('Information technology services expenses increased due to cloud computing volumes.', uid='it')
        self.assertEqual(relevant_sections([broad, narrow], decision, question), [narrow])

    def test_lending_growth_not_inferred_from_security_or_systems(self):
        question = 'What types of customer lending expanded at CBA in FY2025?'
        decision = narrative_decision(question, topic_hint='lending')
        noise = [section('The home lending book remains well secured.', uid='security'),
                 section('Commercial lending systems improved loan origination.', uid='systems')]
        relevant = section('Assets increased due to an increase in home loans and business loans.', uid='growth')
        self.assertEqual(relevant_sections(noise + [relevant], decision, question), [relevant])

    def test_no_evidence_does_not_claim_whole_report_lacks_answer(self):
        question = 'CBA investment priorities 2025'
        result = narrative_evidence(question, narrative_decision(question),
                                    lambda query: {'answer': {'status': 'clarify'}})
        self.assertEqual(result['answer']['status'], 'unable_to_verify')
        self.assertIn('does not establish', result['answer']['message'])
        self.assertNotIn('parts', result['answer'])

    def test_comparative_evidence_starts_partial(self):
        question = 'Where did CBA spend more on technology in 2025?'
        evidence = narrative_evidence(question, narrative_decision(question),
            lambda query: {'answer': {'source_excerpts': [section()]}})
        self.assertEqual(evidence['answer']['status'], 'partial_answer')
        self.assertIn('do not establish', evidence['answer']['message'])

    def test_ambiguous_investment_searches_both_meanings(self):
        core, client = Mock(), Mock()
        with patch('answer_bank_release.NarrativeEvidence.answer', return_value={'answer': {'source_excerpts': []}}) as retrieve:
            result = Backend(EvidenceBackend(core), client).answer('where is CBA investing in 2025')
        self.assertEqual(result['answer']['status'], 'unable_to_verify')
        self.assertGreaterEqual(retrieve.call_count, 2)
        core.answer.assert_not_called(); client.generate.assert_not_called()

    def test_context_budget_gives_both_years_a_turn(self):
        q = 'Compare CBA technology initiatives in FY2024 and FY2025'
        def search(query, year, **options):
            return [section('Technology investment supported customer service. ' * 32,
                            year=year, uid=f'{year}-{i}') for i in range(4)]
        result = narrative_evidence(q, narrative_decision(q), lambda _: {'answer': {}}, search)
        self.assertEqual({s['source']['report_year'] for s in result['answer']['source_excerpts']}, {2024, 2025})
        self.assertTrue(all(c['sections'] for c in result['research_coverage']))

    def test_existing_exclusions_cannot_be_bypassed_by_strategy_word(self):
        core = Mock()
        result = EvidenceBackend(core).answer('What were NAB housing lending figures and priorities in 2025?')
        self.assertEqual(result['answer']['status'], 'unable_to_verify')
        core.answer.assert_not_called()

    def test_priority_question_uses_existing_narrative_retriever(self):
        core = Mock()
        question = 'What were CBA investment priorities in 2025?'
        original = section()
        with patch('answer_bank_release.NarrativeEvidence.answer', return_value={
                'answer': {'source_excerpts': [original]}}) as retrieve:
            result = EvidenceBackend(core).answer(question)
        core.answer.assert_not_called()
        self.assertTrue(retrieve.call_args.args[1].startswith('Explain'))
        self.assertEqual(result['question'], question)
        self.assertEqual(result['answer']['source_excerpts'][0]['source'], original['source'])
        self.assertEqual(result['answer']['source_excerpts'][0]['excerpts'], original['excerpts'])
        self.assertIn('CBA FY2025', result['answer']['source_excerpts'][0]['heading'])
        self.assertEqual(result['answer']['status'], 'partial_answer')

    def test_partial_research_calls_separate_synthesis(self):
        question = 'CBA investment priorities 2025'
        evidence = narrative_evidence(question, narrative_decision(question),
            lambda query: {'answer': {'source_excerpts': [section()]}})
        generated = {**evidence, 'generation': {'status': 'generated'}}
        with patch('answer_bank_release.render_research', return_value=generated) as render:
            result = Backend(Mock(), Mock()).finish(evidence, question)
        render.assert_called_once()
        self.assertEqual(result['generation']['status'], 'generated')


if __name__ == '__main__':
    unittest.main()
