"""Synthetic generation checks. No gold answers or network calls."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from bank_generation_v11 import evidence_cards
from bank_research_answer import supported_statements,render_research,subject_mismatch


def evidence(text,question='Why did NAB staff expenses rise in FY2025?'):
    return {'question':question,'narrative_request':{'topic':'spending','comparative':True},
        'full_report_search':True,'interpretation':{'notes':[]},
        'research_coverage':[{'company':'NAB','year':2025,'topic':'spending'}],
        'answer':{'status':'partial_answer','source_excerpts':[{'heading':'Annual',
            'research_scope':{'company':'NAB','year':2025,'topic':'spending'},
            'source':{'company':'NAB','report_year':2025,'document_id':'fixture','document_title':'Fixture',
                      'pdf_page':1,'report_period_end':'2025-09-30'},
            'excerpts':[{'source_id':'source','quote':text}]}]}}


class GenerationFrozenTests(unittest.TestCase):
    def test_cost_subjects_do_not_substitute_totals_for_components(self):
        self.assertTrue(subject_mismatch('Why did staff expenses rise?', 'Operating expenses rose.'))
        self.assertTrue(subject_mismatch('Why did IT costs rise?', 'Personnel expenses increased.'))
        self.assertFalse(subject_mismatch('Why did profit rise?', 'Higher income contributed to profit growth.'))
        self.assertFalse(subject_mismatch('Explain staff and operating expenses.', 'Operating expenses increased.'))
        self.assertFalse(subject_mismatch('Why did payroll costs rise?', 'Personnel expenses rose with salary inflation.'))

    def test_self_review_cannot_approve_metric_substitution(self):
        source=evidence('Personnel expenses rose with inflation. Total operating expenses rose with acquisition costs.')
        cards=evidence_cards(source['answer'])
        draft={'statements':[{'text':'NAB FY2025 operating expenses rose with acquisition costs.','evidence_ids':['E1']}]}
        review={'supported':[True],'complete':True,'reason':'Fixture model approves.'}
        self.assertEqual(supported_statements(draft,review,cards,source['question']),[])

    def test_plain_cost_explanation_has_no_investment_ranking_footer(self):
        source=evidence('Personnel expenses rose with salary inflation.')
        client=Mock();client.config={'model':'fixture','max_evidence_bytes':10500}
        client.generate_research.return_value=({'statements':[{
            'text':'NAB FY2025 personnel expenses rose with salary inflation.','evidence_ids':['E1']}]},
            {'supported':[True],'complete':True,'reason':'Supported.'},{})
        result=render_research(source,client)
        self.assertEqual(result['generation']['status'],'generated')
        self.assertNotIn('most money',result['answer']['message'])

    def test_empty_evidence_uses_no_model_and_does_not_claim_report_absence(self):
        source=evidence('');source['answer']['source_excerpts']=[]
        client=Mock();client.config={'model':'fixture','max_evidence_bytes':10500}
        result=render_research(source,client)
        client.generate_research.assert_not_called()
        self.assertIn('retrieved',result['answer']['message'])
        self.assertNotIn('report does not',result['answer']['message'])


if __name__=='__main__':unittest.main()
