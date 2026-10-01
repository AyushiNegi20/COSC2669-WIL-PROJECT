"""Explicit financial request planning over unchanged, source-preserving retrieval.

No bank values, expected source pages or evaluation keys are runtime inputs.
"""
from copy import deepcopy
import re
import numpy as np
from bank_retrieval import ROOT,read
from bank_retrieval_v4 import norm,metrics
from bank_retrieval_v5 import (SemanticPlanner as PlannerV5,HybridEvidenceRetriever,
                               query_plan as plan_v5,normalise_question)

CONFIG=ROOT/'config/banking_retrieval_v6.json'
CATALOG=ROOT/'config/financial_concepts_v5.json'


def explicit_metrics(question):
    s=norm(question);tags=metrics(question)
    aliases={
        'basic_cash_eps':r'earnings.*(?:each|per|ordinary).*share|per.share earnings|before dilution',
        'dividend_per_share':r'(?:ordinary|annual|whole year|full year).*dividend|dividend.*(?:share|whole year|full year)',
        'total_assets':r'total (?:group |consolidated |bank )?assets|total asset balance',
        'operating_income':r'(?:total|net) (?:operating )?income',
        'operating_expenses':r'(?:total )?operating expenses|operating costs',
    }
    for tag,pattern in aliases.items():
        if re.search(pattern,s) and tag not in tags: tags.append(tag)
    # Earnings per share is not also an aggregate profit request unless separately named.
    if 'basic_cash_eps' in tags and not re.search(r'cash profit|(?:total|aggregate) cash earnings|statutory',s):
        tags=[t for t in tags if t!='cash_profit']
    return tags


def intent_v6(question):
    from bank_retrieval_v5 import operation
    s=norm(question)
    if re.search(r'(?:mean|definition|description|basis|difference|distinguish|same as|equivalent)',s) and re.search(r'cash flow|cash accounting',s):
        return 'define'
    if re.search(r'which (?:forces|factors|pressures)|what (?:lifted|lowered|supported|offset)|pulled.*back',s):
        return 'explain'
    return operation(question)


def report_vintage(question,years,intent):
    patterns=[r'\b(?:FY\s*)?(20\d{2})\s+(?:profit announcement|results(?: publication| report)?|annual report|report|disclosures|publication)',
              r'\b(?:report|publication|disclosures)\s+(?:for|of|from)\s+(?:FY\s*)?(20\d{2})']
    named=[int(y) for pattern in patterns for y in re.findall(pattern,question,re.I)]
    if len(set(named))==1: return named[0]
    if len(years)==1 and (intent=='define' or re.search(r'original',question,re.I)):
        return years[0]
    return None


def company_years(question,companies,years):
    """Bind nearby explicit bank-year pairs; avoid an unwanted full cross product."""
    result={company:years[:] for company in companies}
    if len(companies)<2 or len(years)<2: return result
    names={'CBA':r'CBA|Commonwealth Bank(?: of Australia)?','NAB':r'NAB|National Australia Bank'}
    mentions=list(re.finditer(r'\b(?:'+ '|'.join(names.values())+r')\b',question,re.I))
    bound={company:[] for company in companies}
    for i,mention in enumerate(mentions):
        company=next(k for k,v in names.items() if re.fullmatch(v,mention.group(),re.I))
        segment=question[mention.end():mentions[i+1].start() if i+1<len(mentions) else len(question)]
        local=[int(y) for y in re.findall(r'\b(?:FY\s*)?(20\d{2})\b',segment,re.I)]
        bound[company]+=local
    if all(bound.values()): return {k:sorted(set(v)) for k,v in bound.items()}
    return result


def request_scopes(question,tag):
    s=norm(question)
    if tag not in ('cash_profit','statutory_npat','basic_cash_eps'): return [None]
    metric_patterns={'cash_profit':r'cash (?:profit|earnings)',
        'statutory_npat':r'statutory (?:profit|net profit)|statutory accounts',
        'basic_cash_eps':r'(?:basic )?cash eps|earnings per share'}
    mentions=list(re.finditer('|'.join('(?:'+x+')' for x in metric_patterns.values()),s))
    fragments=[]
    for i,m in enumerate(mentions):
        if re.fullmatch(metric_patterns[tag],m.group()):
            fragments.append(s[m.start():mentions[i+1].start() if i+1<len(mentions) else len(s)])
    focus=' '.join(fragments) if fragments else s
    both='continuing operations' in focus and 'including discontinued' in focus and bool(re.search(r'both|two scopes',s))
    if both: return ['continuing','including_discontinued']
    if re.search(r'including discontinued|after discontinued',focus): return ['including_discontinued']
    if 'continuing operations' in focus: return ['continuing']
    if 'entire' in s and 'group' in s and tag=='statutory_npat': return ['including_discontinued']
    return [None]


def plan_question(question,base=None):
    p=deepcopy(base) if base is not None else plan_v5(question)
    text=normalise_question(question)[0];s=norm(text);kind=intent_v6(text)
    p.update(version='v6',intent=kind,requests=[],constraints={},requirements_complete=False)
    explicit=explicit_metrics(text)
    tags=explicit or p.get('metrics',[])
    p['metrics']=tags
    # Recover an interpretable operation/alias, never bypass a real v5 scope guard.
    recoverable=(p.get('reason') or '').startswith('The requested measure is not clear enough')
    if recoverable and (explicit or kind in ('explain','define','reconcile')):
        p.update(behavior='answer',reason=None)
    if p['behavior']!='answer': return p
    def stop(reason):
        p.update(behavior='abstain',reason=reason,requests=[])
        return p
    if kind not in ('define','explain'):
        if re.search(r'parent company|company (?:alone|only)|standalone company|excluding subsidiaries',s):
            return stop('The supported metric scope is consolidated Group, not parent Company-only figures.')
        calendar=bool(re.search(r'calendar year|january (?:to|through) december|jan (?:to|through) dec',s))
        if calendar:
            return stop('These selected annual metrics use the bank financial year, not a calendar-year series.')
    if 'lcr' in tags:
        asks_definition=bool(re.search(r'whether|is (?:it|that).*average|mean|defined|definition',s))
        point=re.search(r'single day|daily value|spot value|end of day|on .* alone',s)
        if point and not asks_definition:
            return stop('The selected LCR disclosures are quarterly averages, not the requested single-day value.')
        if re.search(r'annual average|average.*(?:whole|full) year',s):
            return stop('A full-year average LCR is not established by the selected quarterly-average disclosures.')
    cashflow=bool(re.search(r'cash flow|cashflow|cash inflow|operating cash',s))
    if cashflow and kind not in ('define','explain'):
        return stop('Cash profit must not substitute for cash flow; cash-flow figures are outside the supported metric scope.')
    years=p['value_years'];vintage=report_vintage(text,years,kind)
    p['report_year']=vintage if vintage is not None else p.get('report_year')
    p['constraints']={'report_year':p['report_year'],'entity_scope':'Group',
        'requested_years':years,'preserve_source_basis':True,'preserve_period_kind':True,
        'requires_new_calculation':bool(re.search(r'calculate|quantify.*(?:increase|change)|by how much|percentage change',s))}
    inferred=company_years(text,p['companies'],years)
    contrast=cashflow and kind in ('define','explain')
    p['constraints']['cash_profit_cashflow_distinction']=contrast
    tags_for_requests=tags or [None]
    # A prose explanation is one evidence task, not a forced numeric metric lookup.
    if kind in ('explain','reconcile'): tags_for_requests=[None]
    for company in p['companies']:
        requested_years=inferred[company]
        # One branch can retain comparative columns; original vintages are separate.
        branch_years=requested_years if re.search(r'original',s) and len(requested_years)>1 else [None]
        for branch_year in branch_years:
            for tag in tags_for_requests:
                for scope in request_scopes(text,tag):
                    p['requests'].append({'id':f"request-{len(p['requests'])+1}",
                        'company':company,'metric':tag,'intent':kind,'scope':scope,
                        'value_years':requested_years,'report_year':branch_year or p['report_year'],
                        'definition_contrast':False})
        if contrast:
            p['requests'].append({'id':f"request-{len(p['requests'])+1}",'company':company,
                'metric':'cash_profit','intent':'explain','scope':None,
                'value_years':requested_years,'report_year':p['report_year'],'definition_contrast':True})
    if len(p['requests'])>read(CONFIG)['max_requests']:
        p.update(behavior='clarify',reason='Please split this question into fewer company/metric requests.',requests=[])
    return p


class RequestPlanner:
    def __init__(self): self.base=PlannerV5()

    def plan(self,question,focus_vector):
        p=self.base.plan(question,focus_vector)
        return plan_question(question,p)


def scope_matches(record,request):
    scope=request['scope'];tag=request['metric']
    if not scope or record['kind']!='financial_row' or tag not in record['metric_tags']: return True
    label=norm(record['label'])
    if scope=='including_discontinued':
        if 'including discontinued' in label: return True
        row=norm(record.get('row_label',''))
        return tag=='statutory_npat' and 'attributable to owners' in row and not re.search(r'from continuing|from discontinued',row)
    return 'including discontinued' not in label and 'from discontinued' not in label


class RequestRetriever(HybridEvidenceRetriever):
    def section_context(self,candidates):
        """Keep bounded sibling prose together, without crossing a page or heading."""
        expanded=[];seen=set()
        for anchor in candidates:
            siblings=[anchor]
            if anchor['kind']=='passage':
                group=[r for r in self.records if r['kind']=='passage'
                    and r['source']==anchor['source'] and r['label']==anchor['label']]
                # A large section is not an invitation to flood the context window.
                if len(group)<=16 and sum(len(r['body']) for r in group)<=6500:
                    siblings=sorted(group,key=lambda r:r['unit_ids'])
            for r in siblings:
                if r['chunk_id'] not in seen:
                    expanded.append(r);seen.add(r['chunk_id'])
        return expanded

    def contrast_candidates(self,request,query_vector):
        """Find explicit discussion of both concepts, not cash-flow numeric tables."""
        eligible=[]
        for i,r in enumerate(self.records):
            if r['kind'] not in ('passage','definition'): continue
            if r['source']['company']!=request['company']: continue
            if request['report_year'] and r['source']['report_year']!=request['report_year']: continue
            body=norm(r['body'])
            if re.search(r'cash (?:profit|earnings|basis)',body) and re.search(r'cash flows?|cash accounting',body):
                eligible.append(i)
        eligible.sort(key=lambda i:(-float(self.vectors[i]@query_vector),self.records[i]['chunk_id']))
        return [self.records[i] for i in eligible[:2]]

    def search_plan(self,p,query_vector,method='hybrid'):
        if p['behavior']!='answer': return {'plan':p,'records':[],'candidates':[],'request_records':{}}
        catalog=read(CATALOG);branch_results=[];request_records={}
        for request in p['requests']:
            sub=deepcopy(p);tag=request['metric'];kind=request['intent']
            sub.update(companies=[request['company']],metrics=[tag] if tag else [],intent=kind,
                value_years=request['value_years'],report_year=request['report_year'])
            sub['search_question']=p.get('search_question',p['normalised_question']) if kind in ('explain','reconcile') else p['normalised_question']
            if tag: sub['search_question']+='\nFinancial concept: '+catalog[tag]['label']
            if request['definition_contrast']:
                sub['search_question']+='\nCash profit is not a measure based on cash accounting or cash flows. Explain the definition and distinction.'
            if request['scope']:
                sub['search_question']+='\nReporting scope: '+request['scope'].replace('_',' ')
            # Source-scope filtering occurs before ranking, not after a short top-k cut.
            if request['scope']:
                if not hasattr(self,'scope_engines'): self.scope_engines={}
                key=(tag,request['scope'])
                if key not in self.scope_engines:
                    allowed=[i for i,r in enumerate(self.records) if scope_matches(r,request)]
                    self.scope_engines[key]=HybridEvidenceRetriever([self.records[i] for i in allowed],self.units,self.vectors[allowed])
                result=self.scope_engines[key].search_plan(sub,query_vector,method)
            else:
                result=super().search_plan(sub,query_vector,method)
            candidates=result['records']
            if request['definition_contrast']:
                explicit=self.contrast_candidates(request,query_vector)
                candidates=explicit+[r for r in candidates if r not in explicit]
            elif kind=='explain':
                candidates=self.section_context(candidates)
            branch_results.append(candidates)
            request_records[request['id']]=[r['chunk_id'] for r in candidates]
        selected=[];seen=set()
        for depth in range(max((len(r) for r in branch_results),default=0)):
            for branch in branch_results:
                if depth<len(branch) and branch[depth]['chunk_id'] not in seen:
                    selected.append(branch[depth]);seen.add(branch[depth]['chunk_id'])
        return {'plan':p,'records':selected,'candidates':list(request_records.values()),
                'request_records':request_records}

    def context(self,result,tokenizer,budget=None):
        context=super().context(result,tokenizer,budget)
        present={r['chunk_id'] for r in context['records']}
        context['request_coverage']={key:{'candidate_in_context':any(i in present for i in ids),
            'included_ids':[i for i in ids if i in present],
            'meaning':'Candidate coverage only, not semantic answer sufficiency.'}
            for key,ids in result.get('request_records',{}).items()}
        return context
