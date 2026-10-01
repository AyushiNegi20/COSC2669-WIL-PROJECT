from copy import deepcopy
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from answer_bank_release import conceptual
from bank_narrative_routing import narrative_decision, narrative_evidence
from cba_report_library import Library, SCHEMA


class CoverageTests(unittest.TestCase):
    def test_informal_definitions_not_numerical_growth(self):
        for question in ('Does cash profit mean cash flowing in?', 'Does liquidity coverage represent available cash?',
                         'Do statutory results refer to accounting profit?', 'Does dividend yield mean a guaranteed return?'):
            self.assertTrue(conceptual(question), question)
        for question in ('How much did cash profit grow?', 'Does cash profit growth mean better results?',
                         'Calculate the change in ROE between FY2024 and FY2025'):
            self.assertFalse(conceptual(question), question)

    def library(self):
        source = {'company': 'CBA', 'report_year': 2025, 'document_id': 'fixture', 'pdf_page': 1}
        blocks = [
            {'source_id': 'one', 'quote': 'Cash profit increased due to revenue growth.'},
            {'source_id': 'two', 'quote': 'PACC is a measure of risk-adjusted profitability.'},
            {'source_id': 'three', 'quote': 'Cash profit is a measure of adjusted results. This basis is not cash flows.'},
            {'source_id': 'four', 'quote': 'Reserve ratio represents reserves divided by the disclosed denominator.'}]
        return Library({'schema': SCHEMA, 'records': [{'source': source, 'text': ' '.join(b['quote'] for b in blocks), 'blocks': blocks}]})

    def test_definition_search_prefers_requested_phrase_and_meaning(self):
        sections = self.library().search('Does cash profit mean cash flowing in?', 2025, purpose='definition')
        self.assertEqual([e['source_id'] for s in sections for e in s['excerpts']], ['three'])

    def test_definition_filter_generalises_beyond_profit(self):
        sections = self.library().search('Define reserve ratio', 2025, purpose='definition')
        self.assertEqual(sections[0]['excerpts'][0]['source_id'], 'four')
        self.assertEqual(self.library().search('Define unsupported idea', 2025, purpose='definition'), [])

    def test_year_filter_preserved(self):
        self.assertEqual(self.library().search('Define cash profit', 2024, purpose='definition'), [])

    def test_lists_search_wider_but_keep_evidence_budget(self):
        depths = []
        def search(q, year, top_k):
            depths.append(top_k)
            return [{'source': {'company': 'CBA', 'report_year': year}, 'heading': 'Annual results',
                     'excerpts': [{'source_id': str(i), 'quote': 'Customer lending balances increased across this business.'}]}
                    for i in range(top_k)]
        q = 'List the kinds of CBA customer lending that increased in FY2025'
        evidence = narrative_evidence(q, narrative_decision(q, topic_hint='lending'), lambda q: {'answer': {}}, search)
        self.assertEqual(depths, [30])
        self.assertLessEqual(len(evidence['answer']['source_excerpts']), 4)
        q = 'Explain CBA technology investment in FY2025'
        narrative_evidence(q, narrative_decision(q, topic_hint='general'), lambda q: {'answer': {}}, search)
        self.assertEqual(depths[-1], 10)


if __name__ == '__main__': unittest.main()
