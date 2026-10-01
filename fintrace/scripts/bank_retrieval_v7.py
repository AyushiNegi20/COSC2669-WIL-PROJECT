"""Development follow-up: operation, reporting-period and reconciliation constraints.

The locked v6 runtime and its first fresh scores remain unchanged.
"""
from collections import defaultdict
from copy import deepcopy
import re
from bank_retrieval_v4 import norm
from bank_retrieval_v5 import SemanticPlanner
from bank_retrieval_v6 import (RequestRetriever as RetrieverV6,plan_question as plan_v6,
    explicit_metrics,intent_v6)


def operation(question):
    s=norm(question)
    if re.search(r'description|stress horizon|what .*cover\b|what .*adjusted|does it .*cash flows?',s):
        return 'define'
    if re.search(r'underlying.*(?:headline|restructur)|(?:continuing|discontinued).*(?:resulting total|bridg)',s):
        return 'reconcile'
    if re.search(r'explanation|how did.*(?:combine|contribut)|direction.*contribution',s):
        return 'explain'
    return intent_v6(question)


def query_for_planning(question):
    text=question
    if re.search(r'balance.sheet total.*assets|all (?:group )?assets',question,re.I):
        text+='\nFinancial measure: total assets.'
    kind=operation(question)
    if kind in ('define','explain','reconcile'):
        text=kind.capitalize()+': '+text
    return text


def company_metrics(question,companies):
    """Bind locally named measures, but retain shared-list questions for both banks."""
    names={'CBA':r'CBA|Commonwealth Bank(?: of Australia)?','NAB':r'NAB|National Australia Bank'}
    mentions=list(re.finditer(r'\b(?:'+'|'.join(names.values())+r')\b',question,re.I))
    found={c:set() for c in companies}
    for i,m in enumerate(mentions):
        company=next(c for c,pattern in names.items() if re.fullmatch(pattern,m.group(),re.I))
        segment=question[m.end():mentions[i+1].start() if i+1<len(mentions) else len(question)]
        found[company].update(explicit_metrics(segment))
    return found if len(companies)>1 and all(found.values()) else None


def finish_plan(question,p):
    p=deepcopy(p);s=norm(question);kind=operation(question)
    p.update(version='v7',original_question=question)
    if re.search(r'not decided|undecided|not sure which|unsure which',s) and re.search(r'profit|earnings',s):
        p.update(behavior='clarify',reason='Choose statutory or management-adjusted profit, or explicitly request both.',requests=[])
        return p
    if p['behavior']!='answer': return p
    tags=p['metrics']
    if 'nim' in tags and kind not in ('define','explain') and re.search(r'quarter alone|three months|january.*march|jan.*mar',s):
        p.update(behavior='abstain',reason='The supported NIM evidence is full-year or half-year, not this requested quarter.',requests=[])
        return p
    if 'lcr' in tags and kind not in ('define','explain') and re.search(r'(?:lowest|highest|minimum|maximum).*daily|daily.*(?:minimum|maximum)|minimum across days',s):
        p.update(behavior='abstain',reason='Quarterly-average LCR cannot establish the daily minimum or maximum.',requests=[])
        return p
    # Explicit publication vintage takes priority over dates of comparative values.
    named=re.findall(r'\b(?:FY\s*)?(20\d{2})\s+(?:results publication|publication|accounts|description|expense commentary|explanation)',question,re.I)
    vintage=int(named[0]) if len(set(named))==1 else p.get('report_year')
    # Explanations must use the requested year's management commentary.
    if not vintage and len(p['value_years'])==1 and kind in ('define','explain'):
        vintage=p['value_years'][0]
    if vintage:
        p['report_year']=vintage;p['constraints']['report_year']=vintage
        for request in p['requests']: request['report_year']=vintage
    bindings=company_metrics(question,p['companies'])
    if bindings and kind not in ('explain','reconcile'):
        p['requests']=[r for r in p['requests'] if r['metric'] in bindings[r['company']] or r['definition_contrast']]
    return p


def plan_question(question):
    return finish_plan(question,plan_v6(query_for_planning(question)))


class RequestPlanner:
    def __init__(self): self.base=SemanticPlanner()

    def plan(self,question,focus_vector):
        text=query_for_planning(question)
        return finish_plan(question,plan_v6(text,self.base.plan(text,focus_vector)))


class RequestRetriever(RetrieverV6):
    def definition_passages(self,request,query_vector):
        """Definitions also occur in narrative sections, not only a glossary."""
        found=[]
        for i,r in enumerate(self.records):
            if r['kind']!='passage' or request['metric'] not in r['metric_tags']: continue
            if r['source']['company']!=request['company']: continue
            if request['report_year'] and r['source']['report_year']!=request['report_year']: continue
            if re.search(r'\bmeasures? (?:the |of )|\bdefined\b|\brepresents\b|\bconsists\b|not a measure',r['body'],re.I):
                found.append(i)
        found.sort(key=lambda i:(-float(self.vectors[i]@query_vector),self.records[i]['chunk_id']))
        return [self.records[i] for i in found[:2]]

    def bridge_rows(self,p,candidates):
        """Assemble literal contiguous table components, never inferred adjustments."""
        text=norm(p['original_question']);tables=defaultdict(list)
        for r in self.records:
            if r['kind']!='financial_row' or r['source']['company'] not in p['companies']: continue
            if p['report_year'] and r['source']['report_year']!=p['report_year']: continue
            tables[r['table_id']].append(r)
        ranked={r['chunk_id']:len(candidates)-i for i,r in enumerate(candidates)}
        alternatives=[]
        for rows in tables.values():
            if re.search(r'underlying|restructur|one off',text):
                start=[r for r in rows if re.search(r'underlying.*(?:expense|cost)',norm(r['row_label']))]
                end=[r for r in rows if re.fullmatch(r'total operating expenses(?: .*?)?',norm(r['row_label']))]
            elif 'statutory' in text and 'discontinued' in text:
                start=[r for r in rows if re.search(r'profit.*continuing',norm(r['row_label']))]
                end=[r for r in rows if 'statutory_npat' in r['metric_tags'] and not re.search(r'continuing|discontinued',norm(r['row_label']))]
            else: continue
            for lo in start:
                for hi in end:
                    if not 0<hi['row']-lo['row']<=12: continue
                    bundle=sorted([r for r in rows if lo['row']<=r['row']<=hi['row']],key=lambda r:r['row'])
                    if not any(r['chunk_id'] in ranked for r in bundle): continue
                    score=sum(ranked.get(r['chunk_id'],0) for r in bundle)
                    alternatives.append((score,bundle))
        if not alternatives: return candidates
        bundle=max(alternatives,key=lambda pair:pair[0])[1]
        seen={r['chunk_id'] for r in bundle}
        return bundle+[r for r in candidates if r['chunk_id'] not in seen]

    def search_plan(self,p,query_vector,method='hybrid'):
        result=super().search_plan(p,query_vector,method)
        if p['behavior']=='answer' and p['intent']=='define':
            additions=[]
            for request in p['requests']:
                if request['intent']!='define': continue
                extra=self.definition_passages(request,query_vector)
                additions+=extra
                result['request_records'][request['id']]=list(dict.fromkeys(
                    [r['chunk_id'] for r in extra]+result['request_records'][request['id']]))
            result['records']=list({r['chunk_id']:r for r in additions+result['records']}.values())
        if p['behavior']=='answer' and p['intent']=='reconcile':
            # Apply within each request so source ownership remains correct.
            records=[];mapping={}
            lookup={r['chunk_id']:r for r in result['records']}
            for request in p['requests']:
                selected=[lookup[i] for i in result['request_records'][request['id']]]
                sub={**p,'companies':[request['company']],'report_year':request['report_year']}
                selected=self.bridge_rows(sub,selected)
                mapping[request['id']]=[r['chunk_id'] for r in selected]
                records+=selected
            result['records']=list({r['chunk_id']:r for r in records}.values())
            result['request_records']=mapping
        return result
