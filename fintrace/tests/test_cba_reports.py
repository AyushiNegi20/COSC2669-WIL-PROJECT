from copy import deepcopy
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from cba_report_library import annual_rows, ROW_LABELS, words, Library
from cba_investment_answer import answer, eligible
from bank_conversation import present


def fixture():
    return {'source':{'company':'CBA','document_id':'test','pdf_page':7,'report_year':2025,'document_title':'Synthetic table'},
        'years':[2025,2024],'rows':dict(zip(ROW_LABELS,[['50','40'],['100','60'],['150','100'],['60','30'],['40','35'],['50','35']])),
        'validation':'fixture','blocks':[]}


def native(table):
    return 'Full Year Ended Half Year Ended\n30 Jun 25 30 Jun 24 Jun 25 vs 30 Jun 25 31 Dec 24\n$M $M % $M $M %\n'+ '\n'.join(f'{k} {v[0]} {v[1]} 0 1 2 0' for k,v in table['rows'].items())+'\n'


class TableTests(unittest.TestCase):
    def test_two_extractors_and_reconciliation(self):
        text=native(fixture());self.assertEqual(annual_rows(text,text)['years'],[2025,2024])
    def test_changed_digit_rejected(self):
        text=native(fixture())
        with self.assertRaises(ValueError):annual_rows(text,text.replace('60 30','61 30'))
    def test_wrong_sum_rejected_even_if_extractors_agree(self):
        text=native(fixture()).replace('60 30','61 30')
        with self.assertRaises(ValueError):annual_rows(text,text)
    def test_halfyear_header_is_not_annual(self):
        text=native(fixture()).replace('Full Year Ended','Half Year Ended')
        with self.assertRaises(ValueError):annual_rows(text,text)
    def test_missing_unit_rejected(self):
        text=native(fixture()).replace('$M','')
        with self.assertRaises(ValueError):annual_rows(text,text)
    def test_duplicate_conflicting_row_rejected(self):
        text=native(fixture())+'Investment spend 151 100 0 1 2 0\n'
        with self.assertRaises(ValueError):annual_rows(text,text)
    def test_nonconsecutive_dates_rejected(self):
        text=native(fixture()).replace('30 Jun 24','30 Jun 23')
        with self.assertRaises(ValueError):annual_rows(text,text)


class AnswerTests(unittest.TestCase):
    context={'banks':['CBA'],'years':[2025],'defaults':[]}
    def run_answer(self,table=None,q='Which direction is CBA investing more in FY2025?'):
        return answer(q,self.context,SimpleNamespace(data={'investment_tables':[table or fixture()]}))
    def test_values_are_source_derived_not_report_constants(self):
        result=present(self.run_answer());text=' '.join(p['text'] for p in result['presentation']['paragraphs'])
        self.assertIn('150 AUD million',text);self.assertIn('Productivity and growth',text);self.assertNotIn('2,297',text)
    def test_ranking_changes_when_source_values_change(self):
        t=fixture();t['rows']['Productivity and growth']=['40','30'];t['rows']['Risk and compliance']=['60','35']
        text=' '.join(p['text'] for p in present(self.run_answer(t))['presentation']['paragraphs'])
        self.assertIn('largest disclosed category in FY2025 was Risk and compliance',text)
    def test_tie_not_arbitrary_winner(self):
        t=fixture();t['rows']['Productivity and growth']=['50','30'];t['rows']['Risk and compliance']=['50','35']
        text=' '.join(p['text'] for p in present(self.run_answer(t))['presentation']['paragraphs'])
        self.assertIn('Productivity and growth and Risk and compliance and Infrastructure',text)
    def test_ai_budget_not_substituted(self):
        r=self.run_answer(q='How much was CBA AI investment in FY2025?')
        self.assertEqual(r['answer']['status'],'partial_answer');self.assertIn('not a substitute',r['answer']['message'])
    def test_no_bank_portfolio_conflation(self):
        for q in ('CBA lending investment by industry FY2025','Should I invest in CBA shares?','CBA investment in Bank of Hangzhou?'):
            self.assertFalse(eligible(q,self.context))
    def test_nab_does_not_use_cba_table(self):
        self.assertFalse(eligible('NAB investment in FY2025',{'banks':['NAB']}))
    def test_missing_table_no_fabrication(self):
        r=answer('CBA investment FY2025',self.context,SimpleNamespace(data={'investment_tables':[]}))
        self.assertEqual(r['answer']['status'],'unable_to_verify')
    def test_original_fixture_not_mutated(self):
        t=fixture();before=deepcopy(t);self.run_answer(t);self.assertEqual(t,before)
    def test_share_of_increase_is_not_category_growth(self):
        r=self.run_answer(q='How much of the extra investment went to productivity and growth?')
        shares=[c for p in r['answer']['parts'] for c in p['calculations'] if c['operation']=='share' and len(c['source_cells'])==4]
        self.assertTrue(any(c['left']=='30' and c['right']=='50' and c['result']=='60.0' for c in shares))
    def test_expensed_and_capitalised_are_separately_answered(self):
        text=' '.join(p['text'] for p in self.run_answer(q='Was all investment expensed?')['answer']['summary_statements'])
        self.assertIn('50 AUD million was expensed',text)
        self.assertIn('100 AUD million was capitalised',text)
    def test_stopwords_do_not_rank_by_report_year(self):
        self.assertEqual(words('What does CBA say in FY2025?'),[])
    def test_named_subject_cannot_be_lost(self):
        lib=object.__new__(Library);lib.vocabulary=set('investment technology branch project'.split())
        for q in ('How much on Atlantis branch?','How much on atlantis branch?','Explain the Atlantis investment'):
            self.assertTrue(lib.unmatched_subject(q))
        self.assertFalse(lib.unmatched_subject('Explain technology investment'))
    def test_research_rejects_future_tense_without_future_evidence(self):
        from bank_research_answer import supported_statements, evidence_cards
        cards=evidence_cards({'source_excerpts':[{'source':{'company':'CBA','report_year':2025,'document_id':'fixture','pdf_page':1},
             'heading':'AI','excerpts':[{'source_id':'s1','quote':'The Bank continued using AI to automate processes.'}]}]})
        draft={'statements':[{'text':'CBA plans to automate processes in FY2025','evidence_ids':['E1']}]}
        self.assertEqual(supported_statements(draft,{'supported':[True],'complete':True,'reason':'Test'},cards,''),[])
    def test_research_rejects_subsidiary_as_whole_group(self):
        from bank_research_answer import supported_statements, evidence_cards
        cards=evidence_cards({'source_excerpts':[{'source':{'company':'CBA','report_year':2025,'document_id':'fixture','pdf_page':1,'report_section':'New Zealand'},
             'heading':'New Zealand','excerpts':[{'source_id':'s1','quote':'Staff increased to support technology.'}]}]})
        draft={'statements':[{'text':'CBA increased staff in FY2025','evidence_ids':['E1']}]}
        self.assertEqual(supported_statements(draft,{'supported':[True],'complete':True,'reason':'Test'},cards,''),[])


if __name__=='__main__':unittest.main()
