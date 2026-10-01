from copy import deepcopy
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import sys
from threading import Thread
import unittest
from unittest.mock import Mock
from urllib.error import HTTPError
from urllib.request import Request, urlopen

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from bank_conversation import followup, present, paragraphs
from bank_research_answer import supported_statements, evidence_cards
from answer_bank_conversational import Backend
from serve_fintrace_conversational import handler_for


def cell(value='120', year='2025', metric='cash_profit', basis='cash'):
    return {'metric':metric,'value':value,'company':'CBA','unit':'AUD million','period_kind':'annual',
            'basis':basis,'scope':'continuing','period_end':year+'-06-30',
            'source':{'document_id':'fixture','pdf_page':1,'document_title':'Synthetic report','report_year':2025}}


def numeric():
    early, late = cell('100','2024'),cell()
    calc={'operation':'change','left':'120','right':'100','absolute_change':'20','unit':'AUD million',
          'source_cells':[late,early],'relative_change_percent':'20'}
    return {'answer':{'status':'source_bound_answer','parts':[{'claims':[{'cell':early},{'cell':late}],
                     'calculations':[calc],'issues':[]}]},'generation':{'status':'skipped'}}


class FollowupTests(unittest.TestCase):
    def test_bank(self):
        result,notes=followup('What about NAB?','What was CBA cash profit in FY2025?')
        self.assertEqual(result,'What was NAB cash profit in FY2025?');self.assertTrue(notes)
    def test_year(self):
        result,_=followup('And in 2024?','CBA statutory profit FY2025')
        self.assertEqual(result,'CBA statutory profit FY2024')
    def test_no_prior_no_invention(self):
        self.assertEqual(followup('What about NAB?'),('What about NAB?',[]))
    def test_new_subject_not_rewritten(self):
        q='What were NAB customer deposits FY2024?'
        self.assertEqual(followup(q,'CBA profit FY2025'),(q,[]))
    def test_no_carry_from_two_year_comparison(self):
        q='And in 2024?'
        self.assertEqual(followup(q,'Compare CBA cash profit FY2024 and FY2025'),(q,[]))
    def test_no_carry_from_multi_bank_comparison(self):
        q='What about NAB?'
        self.assertEqual(followup(q,'Compare CBA and NAB profit FY2025'),(q,[]))
    def test_context_validation(self):
        for value in ({},'x'*2001):
            with self.assertRaises(ValueError):followup('What about NAB?',value)


class ParagraphTests(unittest.TestCase):
    def test_preserves_numbers_basis_and_source(self):
        result=numeric();original=deepcopy(result);p=present(result)['presentation']['paragraphs']
        self.assertEqual(result,original)
        self.assertIn('120 AUD million',p[0]['text']);self.assertIn('cash basis, continuing operations',p[0]['text'])
        self.assertEqual(p[0]['citations'][0]['pdf_page'],1)
        self.assertIn('+20.00%',p[1]['text'])
    def test_percentage_points_not_growth(self):
        result=numeric();c=result['answer']['parts'][0]['calculations'][0];c.update(unit='percent',absolute_change='0.09')
        p=paragraphs(result)[1]['text'];self.assertIn('0.09 percentage points',p);self.assertNotIn('+20.00%',p)
    def test_explicit_subtraction_not_chronological_claim(self):
        result=numeric();result['answer']['parts'][0]['calculations'][0].update(operation='year_difference',absolute_change='-20')
        text=paragraphs(result)[1]['text'];self.assertIn('requested operand order',text);self.assertNotIn('a decrease',text)
    def test_profit_gap_order_not_reversed(self):
        result=numeric();c=result['answer']['parts'][0]['calculations'][0];c['operation']='profit_gap'
        c['source_cells']=[cell(metric='statutory_npat',basis='statutory'),cell()]
        self.assertIn('statutory profit after tax minus cash profit',paragraphs(result)[1]['text'])
    def test_guard_stays_guard(self):
        result=present({'answer':{'status':'unable_to_verify','message':'Outside the available reports.'}})
        self.assertEqual(result['answer']['status'],'unable_to_verify');self.assertEqual(result['presentation']['paragraphs'][0]['citations'],[])
    def test_generic_clarification_is_actionable(self):
        result=present({'answer':{'status':'clarify','message':'The requested measure is not clear enough. Name a measure.'}})
        self.assertNotIn('Name a measure',result['presentation']['paragraphs'][0]['text'])
        self.assertIn('Which part',result['presentation']['paragraphs'][0]['text'])
    def test_report_year_punctuation_is_not_a_financial_number(self):
        source={'company':'CBA','report_year':2025,'document_id':'fixture','pdf_page':1}
        cards=evidence_cards({'source_excerpts':[{'heading':'Results','source':source,
             'excerpts':[{'source_id':'test','quote':'In FY2025, CBA reported higher statutory profit.'}]}]})
        review={'supported':[True],'complete':True,'reason':'Supported.'}
        draft={'statements':[{'text':'In FY2025, CBA reported higher statutory profit.','evidence_ids':['E1']}]}
        self.assertEqual(len(supported_statements(draft,review,cards,'')),1)


class OrchestrationTests(unittest.TestCase):
    def test_production_routing_cannot_bypass_false_premise_check(self):
        core=Mock();core.answer.return_value=numeric()
        backend=Backend(core);backend.use_cba_reports=True
        backend.intent_planner=Mock()
        result=backend.answer('Why did CBA cash profit fall in FY2025?')
        self.assertFalse(result['premise_check'][0]['matches_question'])
        backend.intent_planner.plan.assert_not_called()
        core.research.assert_not_called()

    def test_false_premise_stops_before_narrative(self):
        core=Mock();core.answer.return_value=numeric()
        result=Backend(core).answer('Why did CBA cash profit fall in FY2025?')
        self.assertFalse(result['premise_check'][0]['matches_question'])
        core.answer.assert_called_once();self.assertIn('does not match',result['answer']['message'])
    def test_supported_premise_can_retrieve_explanation(self):
        core=Mock();core.answer.side_effect=[numeric(),{'answer':{'status':'evidence_answer','message':'Reported reasons.'}}]
        result=Backend(core).answer('Why did CBA cash profit increase in FY2025?')
        self.assertTrue(result['premise_check'][0]['matches_question']);self.assertEqual(core.answer.call_count,2)
    def test_no_comparison_no_invented_cause(self):
        core=Mock();core.answer.return_value={'answer':{'status':'unable_to_verify'}}
        result=Backend(core).answer('Why did CBA cash profit fall in FY2025?')
        core.answer.assert_called_once();self.assertIn('could not verify',result['answer']['message'])
    def test_direction_is_checked_chronologically(self):
        r=numeric();c=r['answer']['parts'][0]['calculations'][0];c['source_cells'].reverse()
        core=Mock();core.answer.return_value=r
        result=Backend(core).answer('Why did CBA cash profit fall in FY2025?')
        self.assertEqual(result['premise_check'],{'verified':False})
    def test_ranking_is_qualified_not_invented(self):
        core=Mock();core.answer.return_value=numeric()
        result=Backend(core).answer('Which bank performed better in FY2025?')
        self.assertTrue(result['comparison_policy']);self.assertEqual(result['answer']['status'],'partial_answer')
        self.assertIn('30 September',' '.join(result['answer']['limitations']))
    def test_unsupported_company_stops_before_core(self):
        core=Mock();r=Backend(core).answer('Which bank performed better, Westpac or CBA, FY2025?')
        core.answer.assert_not_called();self.assertEqual(r['answer']['status'],'unable_to_verify')
    def test_causal_disclosure(self):
        core=Mock();core.answer.return_value={'answer':{'status':'unable_to_verify','message':'No relevant evidence.'}}
        result=Backend(core).answer('Did CBA technology spending cause profit to increase FY2025?')
        self.assertIn('do not independently prove',result['causality_note'])
    def test_missing_followup_context_is_specific(self):
        core=Mock();r=Backend(core).answer('What about that?')
        core.answer.assert_not_called();self.assertIn('earlier subject',r['answer']['message'])


class Stub:
    version='conversation-test'
    def answer(self,q):
        r=numeric();r.update(question=q,received_question=q,version=self.version)
        return present(r)


class ConversationServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),handler_for(Stub()))
        cls.thread=Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.url='http://127.0.0.1:'+str(cls.server.server_port)
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join()
    def test_new_ui_served_with_csp(self):
        with urlopen(self.url) as r:
            html=r.read().decode();self.assertIn("script-src 'self'",r.headers['Content-Security-Policy'])
        self.assertIn('Ask the reports.',html);self.assertNotIn('Refine this question',html)
        self.assertEqual(html.count('id="company-filter"'),1)
    def test_health_identifies_started_candidate(self):
        with urlopen(self.url+'/health') as response:
            health=json.load(response)
        self.assertEqual(health['status'],'ready')
        self.assertRegex(health['startup_fingerprint'],r'^[0-9a-f]{64}$')
    def test_assets_served(self):
        for path in ['/conversation.css','/conversation.mjs','/ui-model.mjs']:
            with urlopen(self.url+path) as r:self.assertEqual(r.status,200)
    def test_followup_and_export(self):
        payload={'question':'What about NAB?','previous_question':'What was CBA cash profit FY2025?'}
        req=Request(self.url+'/ask',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
        with urlopen(req) as r:result=json.load(r)
        self.assertEqual(result['received_question'],'What was NAB cash profit FY2025?')
        self.assertEqual(result['question'],'What about NAB?')
        self.assertTrue(result['ui_scope']['notes']);self.assertIn('cash basis',result['display_text'])
    def test_host_security_still_applies(self):
        with self.assertRaises(HTTPError) as error:urlopen(Request(self.url,headers={'Host':'example.com'}))
        self.assertEqual(error.exception.code,403)


if __name__=='__main__':unittest.main()
