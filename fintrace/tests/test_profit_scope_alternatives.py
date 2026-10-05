"""General profit lookups retain both accounting basis and operational scope."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from bank_contract_v12 import general_profit_lookup, audit_bindings, preflight
from answer_bank_v12 import EvidenceBackend
from bank_source_cells import BoundCell
from bank_conversation import present


def cell(metric, scope, value, year=2025, company='CBA', vintage=None):
    source={'document_id':company.lower()+str(vintage or year), 'company':company,
            'report_year':vintage or year, 'document_title':'Synthetic test report', 'pdf_page':2}
    return BoundCell(metric,company,str(value),str(value),'AUD million',
        'cash' if metric=='cash_profit' else 'statutory',scope,'annual',
        f'{year}-' + ('06-30' if company=='CBA' else '09-30'),vintage or year,
        1,metric+'-'+scope,(),metric+'-'+scope,source,metric+' '+str(value))


def fixture(cells):
    backend=EvidenceBackend.__new__(EvidenceBackend)
    records=[{'kind':'financial_row','source':c.source,'metric_tags':[c.metric],
              'chunk_id':c.record_id,'cell':c} for c in cells]
    backend.retriever=SimpleNamespace(engine=SimpleNamespace(records=records))
    backend.binder=Mock()
    backend.binder.units={c.source_id:c.row_quote for c in cells}
    backend.binder.bind.side_effect=lambda record,metric:[record['cell']]
    def select(records,request,question):
        options=[r['cell'] for r in records if r['cell'].scope==request['scope']
                 and int(r['cell'].period_end[:4]) in request['value_years']
                 and (not request.get('report_year') or r['cell'].report_year==request['report_year'])]
        return options, []
    backend.binder.select.side_effect=select
    parts=[]
    for metric in ('cash_profit','statutory_npat'):
        parts.append({'request':{'id':metric,'metric':metric,'company':cells[0].company,
                     'value_years':[2025],'report_year':None,'scope':None},
                     'claims':[], 'calculations':[], 'issues':[]})
    result={'question':'profit','answer':{'status':'unable_to_verify','parts':parts,'issues':[]}}
    return backend,result


class GeneralProfitScopeTests(unittest.TestCase):
    def test_plain_lookup_variants_qualify(self):
        for q in ('What was CBA profit in FY2025?', 'NAB net profit FY2024?',
                  'Show CBA NPAT in 2025', 'CBA earnings FY2025',
                  'What was CBA net income in FY2025?',
                  'CBA profit from continuing operations FY2025'):
            self.assertTrue(general_profit_lookup(q),q)

    def test_specific_measures_and_nonlookup_requests_do_not_expand(self):
        for q in ('CBA cash profit FY2025', 'NAB cash earnings FY2024',
                  'CBA statutory NPAT FY2025', 'CBA basic cash EPS FY2025',
                  'Why did CBA profit rise in FY2025?', 'What does profit mean?',
                  'Compare CBA profit FY2024 and FY2025', 'How much did CBA profit grow in FY2025?',
                  'CBA total assets FY2025', 'Calculate CBA cash minus statutory profit FY2025'):
            self.assertFalse(general_profit_lookup(q),q)

    def test_all_available_variants_and_provenance_are_retained(self):
        cells=[cell(m,s,v) for m,s,v in (
            ('cash_profit','continuing',100), ('cash_profit','including_discontinued',101),
            ('statutory_npat','continuing',90), ('statutory_npat','including_discontinued',88))]
        backend,result=fixture(cells)
        answer=backend.profit_scope_alternatives(result,'What was CBA profit FY2025?')
        returned=[c['cell'] for p in answer['answer']['parts'] for c in p['claims']]
        self.assertEqual({(c['metric'],c['scope'],c['value']) for c in returned},
                         {(c.metric,c.scope,c.value) for c in cells})
        self.assertEqual(len(returned),4)
        self.assertEqual(answer['answer']['status'],'source_bound_answer')
        self.assertEqual(audit_bindings(answer),[])
        rendered=present(answer)['presentation']['paragraphs']
        self.assertEqual(len(rendered),4)
        self.assertTrue(all(p['citations'][0]['pdf_page']==2 for p in rendered))

    def test_bank_with_two_available_variants_does_not_invent_four(self):
        backend,result=fixture([cell('cash_profit','continuing',80,company='NAB'),
                                cell('statutory_npat','including_discontinued',78,company='NAB')])
        answer=backend.profit_scope_alternatives(result,'NAB profit FY2025?')
        self.assertEqual(sum(len(p['claims']) for p in answer['answer']['parts']),2)
        self.assertEqual(answer['answer']['status'],'source_bound_answer')

    def test_explicit_scope_filters_both_profit_bases(self):
        cells=[cell(m,s,100+i) for i,(m,s) in enumerate((
            ('cash_profit','continuing'),('cash_profit','including_discontinued'),
            ('statutory_npat','continuing'),('statutory_npat','including_discontinued')))]
        for wording,scope in [('from continuing operations','continuing'),
                              ('including discontinued operations','including_discontinued')]:
            backend,result=fixture(cells)
            answer=backend.profit_scope_alternatives(result,f'CBA profit {wording} FY2025')
            returned=[c['cell'] for p in answer['answer']['parts'] for c in p['claims']]
            self.assertEqual(len(returned),2)
            self.assertEqual({c['scope'] for c in returned},{scope})

    def test_comparative_vintage_restriction_is_preserved(self):
        cells=[cell(m,'continuing',100+i,vintage=v) for i,(m,v) in enumerate((
            ('cash_profit',2024),('statutory_npat',2024),
            ('cash_profit',2025),('statutory_npat',2025)))]
        backend,result=fixture(cells)
        for p in result['answer']['parts']: p['request']['report_year']=2025
        answer=backend.profit_scope_alternatives(result,'CBA profit FY2025 in the FY2025 report')
        returned=[c['cell'] for p in answer['answer']['parts'] for c in p['claims']]
        self.assertTrue(all(c['report_year']==2025 for c in returned))

    def test_missing_explicit_scope_is_visible_not_substituted(self):
        backend,result=fixture([cell('cash_profit','continuing',100),cell('statutory_npat','continuing',90)])
        answer=backend.profit_scope_alternatives(result,'CBA profit including discontinued operations FY2025')
        self.assertEqual(answer['answer']['status'],'unable_to_verify')
        self.assertFalse(any(p['claims'] for p in answer['answer']['parts']))
        self.assertTrue(all(p['issues'] for p in answer['answer']['parts']))

    def test_unavailable_unit_conversion_keeps_its_limitation(self):
        backend,result=fixture([cell('cash_profit','continuing',100),cell('statutory_npat','continuing',90)])
        answer=backend.profit_scope_alternatives(result,'CBA profit FY2025 in billions')
        self.assertEqual(answer['answer']['status'],'partial_answer')
        self.assertTrue(all(any('unit conversion' in i for i in p['issues']) for p in answer['answer']['parts']))

    def test_discontinued_only_never_means_including_discontinued(self):
        for q in ('CBA profit from discontinued operations FY2025',
                  'CBA profit from discontinued operations only FY2025',
                  'NAB profit for only discontinued operations FY2024'):
            self.assertIsNotNone(preflight(q),q)
        self.assertIsNone(preflight('CBA profit including discontinued operations FY2025'))


if __name__=='__main__': unittest.main()
