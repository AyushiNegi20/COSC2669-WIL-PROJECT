"""Prioritise literal conceptual exclusions before spending the context budget."""
import re
from bank_retrieval_service_v9 import RetrievalService as V9Service


def direct_contrast(records,request):
    return [r for r in records if r['kind'] in ('passage','definition') and
            r['source']['company']==request['company'] and
            (not request.get('report_year') or r['source']['report_year']==request['report_year']) and
            re.search(r'cash (?:profit|earnings|basis)',r['body'],re.I) and
            re.search(r'not a measure based on cash accounting|not.*cash flows or liquidity',r['body'],re.I)]


class RetrievalService(V9Service):
    def retrieve(self,question):
        plan,context=super().retrieve(question)
        requests=[r for r in plan.get('requests',[]) if r.get('definition_contrast')]
        if plan['behavior']!='answer' or not requests or self.engine is None: return plan,context
        extras=[];mapping={k:list(v['included_ids']) for k,v in context['request_coverage'].items()}
        for request in requests:
            direct=direct_contrast(self.engine.records,request)
            extras+=direct
            mapping[request['id']]=list(dict.fromkeys([r['chunk_id'] for r in direct]+mapping.get(request['id'],[])))
        if not extras: return plan,context
        records=list({r['chunk_id']:r for r in extras+context['records']}.values())
        assembled={'plan':plan,'records':records,'candidates':[],'request_records':mapping}
        return plan,self.engine.context(assembled,self.tokenizer)
