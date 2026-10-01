import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from bank_answer import (validate_draft,finalise_draft,evidence_registry,guard_response,
                         OllamaClient,numeric_tokens,evidence_numbers)


def fixture():
    registry={'test:row':{'text':'Cash profit | 2025 | 10,252 | AUD million',
        'source':{'company':'CBA','document_title':'Test report','pdf_page':18},
        'quality':{'status':'development_unreviewed'}}}
    draft={'status':'answered','claims':[{'text':'CBA cash profit was AUD 10,252 million.',
        'company':'CBA','period':'2025','basis':'cash','unit':'AUD million',
        'evidence':[{'source_id':'test:row','quote':registry['test:row']['text']}]}],
        'limitations':[]}
    return draft,registry


class AnswerTests(unittest.TestCase):
    def test_valid_cited_draft_remains_unreviewed(self):
        draft,registry=fixture();result=finalise_draft(draft,registry)
        self.assertEqual(result['status'],'draft_answer')
        self.assertEqual(result['validation']['semantic_entailment'],'not_verified')
        self.assertFalse(result['validation']['calculation_ready'])
        self.assertEqual(result['claims'][0]['evidence'][0]['source']['pdf_page'],18)

    def test_unknown_source_fails_closed(self):
        draft,registry=fixture();draft['claims'][0]['evidence'][0]['source_id']='invented'
        self.assertEqual(finalise_draft(draft,registry)['claims'],[])

    def test_invented_quote_fails(self):
        draft,registry=fixture();draft['claims'][0]['evidence'][0]['quote']='Cash profit | 99,999'
        self.assertTrue(validate_draft(draft,registry))

    def test_uncited_number_fails(self):
        draft,registry=fixture();draft['claims'][0]['text']='Cash profit rose 99%.'
        self.assertTrue(validate_draft(draft,registry))

    def test_invented_period_label_fails(self):
        draft,registry=fixture();draft['claims'][0]['period']='2024'
        self.assertTrue(validate_draft(draft,registry))

    def test_cross_company_citation_fails(self):
        draft,registry=fixture();draft['claims'][0]['company']='NAB'
        self.assertTrue(validate_draft(draft,registry))

    def test_missing_basis_fails(self):
        draft,registry=fixture();draft['claims'][0]['basis']=''
        self.assertTrue(validate_draft(draft,registry))

    def test_uncited_summary_rejected(self):
        draft,registry=fixture();draft['summary']='All profits increased.'
        self.assertTrue(validate_draft(draft,registry))

    def test_limitation_cannot_smuggle_uncited_findings(self):
        draft,registry=fixture();draft.update(status='unable_to_verify',claims=[],
            limitations=['CBA cash profit was AUD 999,999 million.'])
        self.assertEqual(finalise_draft(draft,registry)['claims'],[])
        self.assertIn('validation_errors',finalise_draft(draft,registry))

    def test_limitation_codes_render_fixed_text(self):
        draft,registry=fixture();draft['limitations']=['partial_answer']
        self.assertIn('Only part',finalise_draft(draft,registry)['limitations'][0])

    def test_partial_digit_quote_rejected(self):
        draft,registry=fixture();claim=draft['claims'][0]
        claim.update(text='Cash profit was 2 million.',period='not applicable')
        claim['evidence'][0]['quote']='2'
        self.assertTrue(validate_draft(draft,registry))

    def test_negative_sign_flip_rejected(self):
        for value in ['-10,252','\u221210,252','- 10,252','\ufe6310,252','\uff0d10,252']:
            draft,registry=fixture();draft['claims'][0]['text']='Cash profit was '+value+' million.'
            with self.subTest(value=value): self.assertTrue(validate_draft(draft,registry))

    def test_parentheses_keep_negative_sign(self):
        self.assertEqual(numeric_tokens('(10,252)'),numeric_tokens('-10,252'))
        self.assertNotEqual(numeric_tokens('(10,252)'),numeric_tokens('10,252'))

    def test_lookup_cannot_repeat_question_without_value(self):
        draft,registry=fixture();draft['claims'][0]['text']='CBA cash profit in 2025.'
        self.assertTrue(validate_draft(draft,registry,{'intent':'find','metrics':['cash_profit']}))

    def test_date_expansion_requires_explicit_month(self):
        self.assertIn('2025',evidence_numbers('Header | 30 Jun 25',{'report_year':2025},table_dates=True))
        self.assertNotIn('2025',evidence_numbers('Cash profit | 25',{'report_year':2025}))
        self.assertNotIn('2030',evidence_numbers('The board met on June 30.',{'report_year':2025}))
        self.assertNotIn('2030',evidence_numbers('Notes | The board met on June 30.',{'report_year':2025},table_dates=True))

    def test_header_dependency_attached_and_checked(self):
        draft,registry=fixture();registry['test:row']['text']='Cash profit | 10,252 | AUD million'
        registry['test:r0']={'text':'Full year ended | 30 Jun 25',
            'source':{'company':'CBA','report_year':2025},'quality':{'status':'development_unreviewed'}}
        registry['test:row']['dependencies']=['test:r0']
        draft['claims'][0]['evidence'][0]['quote']=registry['test:row']['text']
        result=finalise_draft(draft,registry,{'intent':'find','metrics':['cash_profit']})
        self.assertEqual(result['status'],'draft_answer')
        self.assertEqual(result['claims'][0]['source_context'][0]['source_id'],'test:r0')

    def test_narrative_excerpt_cannot_remove_negative_prefix(self):
        for spelling in ['\u221210,252','- 10,252','(10,252)']:
            draft,registry=fixture()
            registry={'test:paragraph':{**registry['test:row'],'text':'Cash profit was '+spelling+' million.'}}
            claim=draft['claims'][0]
            claim.update(text='Cash profit was 10,252 million.',period='not applicable')
            claim['evidence']=[{'source_id':'test:paragraph','quote':'10,252 million.'}]
            self.assertTrue(validate_draft(draft,registry))

    def test_report_year_alone_cannot_establish_numeric_value_year(self):
        draft,registry=fixture();registry['test:row']['text']='Cash profit | 10,252 | AUD million'
        registry['test:row']['source']['report_year']=2025
        draft['claims'][0]['evidence'][0]['quote']=registry['test:row']['text']
        self.assertTrue(validate_draft(draft,registry,{'intent':'find','metrics':['cash_profit']}))

    def test_abstention_cannot_smuggle_claims(self):
        draft,registry=fixture();draft['status']='unable_to_verify'
        self.assertTrue(validate_draft(draft,registry))

    def test_empty_answer_rejected(self):
        draft,registry=fixture();draft['claims']=[]
        self.assertTrue(validate_draft(draft,registry))

    def test_no_false_semantic_verification_claim(self):
        draft,registry=fixture();draft['claims'][0]['text']='CBA statutory profit was AUD 10,252 million.'
        result=finalise_draft(draft,registry)
        # Mechanical checks cannot detect this basis contradiction. Preserve the limitation.
        self.assertEqual(result['validation']['semantic_entailment'],'not_verified')

    def test_profit_clarification_teaches_and_offers_both(self):
        result=guard_response({'behavior':'clarify','companies':['CBA'],'original_question':'Why did profit rise?'})
        self.assertIn('Show both, clearly labelled',result['options'])
        self.assertIn('does not mean cash',result['message'])

    def test_remote_provider_rejected(self):
        with self.assertRaises(ValueError): OllamaClient({'base_url':'https://external.invalid'})

    def test_noninstalled_model_not_downloaded(self):
        client=OllamaClient()
        with patch.object(client,'request',return_value={'models':[]}) as request:
            with self.assertRaises(RuntimeError): client.generate('question','evidence')
            request.assert_called_once_with('/api/tags')

    def test_truncated_generation_rejected(self):
        client=OllamaClient()
        replies=[{'models':[{'name':client.config['model'],'digest':'test'}]},
                 {'done':True,'done_reason':'length','message':{'content':'{}'}}]
        with patch.object(client,'request',side_effect=replies):
            with self.assertRaises(ValueError): client.generate('question','evidence')

    def test_context_limit_never_silently_trims(self):
        client=OllamaClient()
        with patch.object(client,'request',return_value={'models':[{'name':client.config['model'],'digest':'test'}]}) as request:
            with self.assertRaises(ValueError): client.generate('question','x'*20000)
            self.assertEqual(request.call_count,1)

    def test_only_packed_source_units_are_citable(self):
        _,registry=fixture();r=registry['test:row']
        context={'records':[{'unit_ids':['test:row'],'source':r['source'],'quality':r['quality']}],'text':'not the packed row'}
        with self.assertRaises(ValueError): evidence_registry(context,{'test:row':r['text']})

    def test_quarantined_evidence_rejected(self):
        _,registry=fixture();r=registry['test:row'];r['quality']['status']='quarantined'
        context={'records':[{'unit_ids':['test:row'],'source':r['source'],'quality':r['quality']}],
                 'text':'[test:row] '+r['text']}
        with self.assertRaises(ValueError): evidence_registry(context,{'test:row':r['text']})


if __name__=='__main__': unittest.main()
