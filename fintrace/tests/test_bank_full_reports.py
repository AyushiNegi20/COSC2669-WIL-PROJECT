from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from bank_report_library import BankLibrary,nab_period,cba_division
from cba_report_library import SCHEMA,words
from bank_narrative_routing import narrative_evidence,narrative_decision,relevant_sections


def raw(x,y,text):return (x,y,x+230,y+10,text,0,0)


class BankReportTests(unittest.TestCase):
    def test_division_requires_explicit_unique_result_declaration(self):
        group='Group or general disclosure'
        self.assertEqual(cba_division('Business Banking cash net profit after tax grew.',group),'Business Banking')
        self.assertEqual(cba_division('Retail Banking Services generated $2 billion of organic capital.',group),'Retail Banking Services')
        self.assertEqual(cba_division('Growth included Business Banking and Retail Banking Services.',group),group)
        self.assertEqual(cba_division('Business Banking cash net profit after tax rose. Retail Banking Services cash net profit after tax fell.',group),group)

    def test_strategy_morphology(self):
        self.assertEqual(words('strategic priorities'),words('strategy priority'))

    def test_it_costs_expand_but_pronoun_does_not(self):
        data={'schema':SCHEMA,'records':[{'source':{'company':'NAB','report_year':2024,'document_id':'test'},
            'text':'Information technology services.', 'blocks':[{'source_id':'test','quote':'Information technology services improved.'}]}]}
        lib=BankLibrary(data)
        self.assertTrue(lib.search('IT costs',2024,company='NAB'))
        self.assertEqual(lib.search('Did it become safer?',2024,company='NAB'),[])

    def test_nab_annual_and_half_year_do_not_cross_columns(self):
        headings=[raw(50,100,'September 2025 v September 2024'),raw(310,100,'September 2025 v March 2025')]
        self.assertTrue(nab_period(raw(50,130,'Annual text.'),headings).startswith('Year comparison'))
        self.assertTrue(nab_period(raw(310,130,'Half text.'),headings).startswith('Half year comparison'))

    def test_company_year_and_period_filters(self):
        records=[]
        for company in ('CBA','NAB'):
            for year in (2024,2025):
                records.append({'source':{'company':company,'report_year':year,'document_id':company+str(year)},
                    'text':'Staff expenses salary inflation.',
                    'blocks':[{'source_id':f'{company}{year}a','quote':'Staff expenses rose due to salary inflation.','period_context':'Year comparison'},
                              {'source_id':f'{company}{year}h','quote':'Staff expenses rose due to salary inflation.','period_context':'Half year comparison'}]})
        lib=BankLibrary({'schema':SCHEMA,'records':records})
        for company in ('CBA','NAB'):
            hits=lib.search('Why did staff expenses rise?',2025,company=company)
            self.assertEqual([h['excerpts'][0]['source_id'] for h in hits],[company+'2025a'])
            half=lib.search('Staff expenses in the half year',2025,company=company)
            self.assertEqual([h['excerpts'][0]['source_id'] for h in half],[company+'2025h'])
        self.assertEqual(lib.search('staff expenses',2026,company='NAB'),[])
        self.assertEqual(lib.search('staff expenses',2025,company='ANZ'),[])

    def test_nab_staff_wording_keeps_personnel_expenses(self):
        section={'source':{'company':'NAB','report_year':2025},'heading':'Annual',
                 'excerpts':[{'source_id':'s','quote':'Personnel expenses increased with salary inflation.'}]}
        self.assertEqual(relevant_sections([section],{'company':'NAB','year':2025,'topic':'spending'},
                         'Why did NAB staff expenses rise?'),[section])

    def test_nab_uses_full_search_and_preserves_scope(self):
        section={'source':{'company':'NAB','report_year':2025,'document_id':'test','pdf_page':20},
                 'heading':'Annual','excerpts':[{'source_id':'s','quote':'Personnel expenses increased with salary inflation.'}]}
        search=Mock(return_value=[section]);fallback=Mock()
        question='Why did NAB staff expenses rise in FY2025?'
        result=narrative_evidence(question,narrative_decision(question,topic_hint='spending'),fallback,search)
        self.assertEqual(search.call_args.kwargs['company'],'NAB')
        fallback.assert_not_called()
        self.assertTrue(result['full_report_search'])
        self.assertNotIn('NAB remains',str(result))

    def test_runtime_does_not_read_evaluation_keys(self):
        source=(Path(__file__).resolve().parents[1]/'scripts/bank_report_library.py').read_text()
        self.assertNotIn('metric_scope_13.json',source)
        self.assertNotIn('answer_key.json',source)
        self.assertNotIn('eval/',source)


if __name__=='__main__':unittest.main()
