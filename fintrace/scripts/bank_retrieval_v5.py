"""Experimental semantic planning and hybrid evidence retrieval. No gold inputs."""
from collections import defaultdict
import difflib
import re
import numpy as np
from bank_retrieval import ROOT,read,BM25
from bank_retrieval_v4 import (EvidenceRetriever,build_view,embedding_cache,vectors_for,
                              metrics,norm,plan as old_plan)

CONFIG=ROOT/'config/banking_retrieval_v5.json'
CATALOG=ROOT/'config/financial_concepts_v5.json'
REPORTS=ROOT/'reports/banking_retrieval_v5'


def normalise_question(question):
    """Correct conservative spelling matches; retain every change for inspection."""
    vocabulary={'commonwealth','australia','interest','dividend','deposits','customer',
                'statutory','earnings','expenses','impairment','liquidity','margin','share',
                'earning','deposit','shares','customers','margins','expense'}
    changes=[]
    def replace(match):
        word=match.group()
        if len(word)<5 or word.lower() in vocabulary: return word
        matches=difflib.get_close_matches(word.lower(),sorted(vocabulary),n=1,cutoff=.86)
        if not matches: return word
        changes.append({'original':word,'normalised':matches[0]})
        return matches[0]
    text=re.sub(r'[A-Za-z]+',replace,question)
    text=re.sub(r'\bFY\s*(24|25)\b',lambda m:'FY20'+m[1],text,flags=re.I)
    return text,changes


def operation(text):
    s=norm(text)
    # Negated vintage constraints do not turn a lookup into reconciliation.
    routing=re.sub(r'\bnot (?:a )?(?:later )?restatement\b','',s)
    if re.search(r'\bdefin|meaning|glossary|stand for|what does .* mean',routing): return 'define'
    if re.search(r'reconcil|\bbridge\b|non cash adjustments|reclassif|restat|moved between|different.*comparative|comparative.*different|original.*comparative',routing): return 'reconcile'
    if re.search(r'\bwhy\b|\breasons?\b|what (?:made|drove|caused)|factors|drivers|explain|influenc|affect|squeez|pressure.*attribute',routing): return 'explain'
    if re.search(r'summary|summari|snapshot|roundup|\bbrief\b',routing): return 'summary'
    if re.search(r'compar|change|growth|grew|improv|worsen|\bmove|versus|\bvs\b',routing): return 'compare'
    return 'find'


def semantic_focus(question):
    """Remove report identifiers for concept matching only, never from retrieval."""
    text=normalise_question(question)[0]
    text=re.sub(r'\b(?:Commonwealth Bank(?: of Australia)?|National Australia Bank|CBA|NAB)(?:\'s)?\b',' ',text,flags=re.I)
    text=re.sub(r'\b(?:FY\s*)?20\d{2}\b',' ',text,flags=re.I)
    text=re.sub(r'\b(?:original(?:ly)?|published|report|reports|disclosures|financial year)\b',' ',text,flags=re.I)
    text=re.sub(r'Give the source and unit\.?|Include the unit and reporting basis\.?',' ',text,flags=re.I)
    return ' '.join(text.split())


def annual_explanation(question):
    """Never apply annual-comparison preferences to an explicit interim request."""
    s=norm(question)
    interim=re.search(r'half year|six months|half yearly|\bh\s*[12]\b|quarter|march|december',s)
    return not interim and bool(re.search(r'\bfy\s*\d|annual|year|prior',s))


def query_plan(question,semantic_scores=None):
    config=read(CONFIG);catalog=read(CATALOG)
    text,corrections=normalise_question(question)
    p=old_plan(text)
    p.update(original_question=question,normalised_question=text,corrections=corrections,
             intent=operation(text),behavior='answer',reason=None,metric_candidates=[],
             metric_resolution='explicit',needs_human_review=True)
    s=norm(text)
    def stop(behavior,reason):
        p.update(behavior=behavior,reason=reason)
        return p
    if re.search(r'\b(?:anz|westpac|macquarie|bendigo|tesla|bhp)\b',s):
        return stop('abstain','Requested company is outside the CBA/NAB corpus.')
    if any(y not in (2024,2025) for y in p['value_years']):
        return stop('abstain','Requested reporting period is outside FY2024/FY2025.')
    if re.search(r'\b(?:next year|forecast|predict)\b|\bwill\b.*\b(?:earn|profit|pay|dividend)',s):
        return stop('abstain','The reports cannot establish a future realised financial outcome.')
    if re.search(r'\b(?:today|current|live|now)\b.*(?:share|stock) price|(?:share|stock) price.*\b(?:today|current|live|now)\b',s):
        return stop('abstain','Historical financial reports do not establish a live share price.')
    if re.search(r'\bmy\b.*\b(?:account|savings|loan|balance)\b|account balance of (?:a )?customer|customer.*(?:personal|individual).*account',s):
        return stop('abstain','Public reports do not establish individual account information.')
    if not p['companies']:
        return stop('clarify','Specify CBA or NAB; definitions and financial bases may differ.')
    tags=metrics(text)
    # Standard financial aliases, not question-specific source/value mappings.
    if re.search(r'\btotal income\b',s) and 'operating_income' not in tags:
        tags.append('operating_income')
    if p['intent']=='reconcile' and 'cash_profit' in tags and re.search(r'accounting (?:bottom line|profit)|statutory',s):
        tags=list(dict.fromkeys(tags+['statutory_npat']))
    broad=bool(re.search(r'how much money.*make|how much.*\bearn\b|more profitable|safety buffer|which bank.*better|how much cash.*have',s))
    unqualified_profit=bool(re.search(r'\bprofit\b',s)) and not re.search(r'cash|statutory|accounting|net profit|operating|reconcil|bridge|both',s)
    if not tags and p['intent'] not in ('define','reconcile') and (broad or unqualified_profit):
        return stop('clarify','Specify the financial measure and basis; do not infer one from generic wording.')
    if semantic_scores:
        ordered=sorted(semantic_scores.items(),key=lambda x:(-x[1],x[0]))
        p['metric_candidates']=[{'metric':k,'similarity':float(v)} for k,v in ordered[:3]]
        best,score=ordered[0];margin=score-ordered[1][1]
        p['semantic_margin']=float(margin)
        if not tags and score>=config['semantic_metric_min'] and margin>=config['semantic_metric_margin']:
            tags=[best];p['metric_resolution']='semantic_candidate_not_verified'
    p['metrics']=tags
    if not tags and p['intent'] in ('find','compare','summary','define'):
        return stop('clarify','The requested measure is not clear enough. Name a measure or explain its basis.')
    p['search_question']=text
    if tags:
        p['search_question']+='\nFinancial concepts: '+'; '.join(catalog[t]['label'] for t in tags)
    if p['intent']=='reconcile' and re.search(r'moved between|reclassif',s):
        p['reconciliation_type']='presentation_reclassification'
        p['search_question']+='\nReclassification of comparative presentation applied retrospectively.'
        named=re.findall(r'\b(?:FY\s*)?(20\d{2})\s+(?:report|disclosures)\b',text,re.I)
        if len(set(named))==1: p['report_year']=int(named[0])
    p['period_note']='Preserve each source period end; CBA and NAB fiscal years do not end on the same date.'
    return p


class SemanticPlanner:
    def __init__(self):
        self.catalog=read(CATALOG)
        self.keys=list(self.catalog)
        self.vectors=embedding_cache([v['label']+'. '+v['description'] for v in self.catalog.values()])
        self.topics=read(ROOT/'config/narrative_concepts_v5.json')
        self.topic_keys=list(self.topics)
        self.topic_vectors=embedding_cache([v['label']+'. '+v['description'] for v in self.topics.values()])

    def plan(self,question,vector):
        scores=self.vectors@vector
        p=query_plan(question,dict(zip(self.keys,map(float,scores))))
        if p['behavior']=='answer' and p['intent']=='explain':
            # Narrative drivers need a topic, not a forced numerical metric.
            if p['metric_resolution']=='semantic_candidate_not_verified':
                p['metrics']=[];p['metric_resolution']='narrative_topic_only'
                p['search_question']=p['normalised_question']
            topic_scores=self.topic_vectors@vector
            order=np.argsort(-topic_scores)
            p['narrative_candidates']=[{'topic':self.topic_keys[i],'similarity':float(topic_scores[i])} for i in order]
            if float(topic_scores[order[0]])>=.35 and float(topic_scores[order[0]]-topic_scores[order[1]])>=.02:
                p['narrative_topic']=self.topic_keys[order[0]]
                p['search_question']+='\nExplanation topic: '+self.topics[p['narrative_topic']]['label']
        return p


class HybridEvidenceRetriever(EvidenceRetriever):
    def __init__(self,records,units,vectors,reranker=None):
        super().__init__(records,units,vectors)
        self.config=read(CONFIG)
        self.catalog=read(CATALOG)
        self.reranker=reranker

    def search_plan(self,p,query_vector,method='hybrid'):
        if method not in ('bm25','hybrid','hybrid_rerank'): raise ValueError('Unknown method')
        if p['behavior']!='answer': return {'plan':p,'records':[],'candidates':[]}
        query=p['normalised_question'];canonical=p['search_question']
        base=self.lexical.score(canonical)
        dense=self.vectors@query_vector
        tags=p['metrics'] if p['intent'] not in ('explain','reconcile') else [None]
        tags=tags or [None]
        branches=[];candidate_ids=[]
        years=p['value_years'] if len(p['value_years'])>1 and re.search(r'original|comparative in',query,re.I) else [p['report_year']]
        for company in p['companies']:
            for year in years:
                for tag in tags:
                    label_query=self.catalog[tag]['label'] if tag else canonical
                    label=self.label_lexical.score(label_query)
                    allowed=[i for i,r in enumerate(self.records) if r['source']['company']==company
                        and (not year or r['source']['report_year']==year)
                        and (not p['annual_report_only'] or '_ar' in r['source']['document_id'])]
                    def rank(values):
                        return sorted(allowed,key=lambda i:(-float(values[i]),self.records[i]['chunk_id']))
                    lists=[[i for i in rank(base) if base[i]>0][:self.config['candidate_k']],
                           [i for i in rank(label) if label[i]>0][:self.config['candidate_k']]]
                    if method!='bm25': lists.append(rank(dense)[:self.config['candidate_k']])
                    fused=defaultdict(float)
                    for order in lists:
                        for position,i in enumerate(order,1): fused[i]+=1/(self.config['rrf_constant']+position)
                    scores={}
                    for i,value in fused.items():
                        r=self.records[i];lab=norm(r['label']);row=norm(r.get('row_label',''))
                        if p['intent']=='define':
                            value+=.08 if r['kind']=='definition' else -.06
                            if tag in r['metric_tags']: value+=.04
                            definition=p.get('definition_term')
                            if definition and norm(definition)==lab: value+=.05
                        elif p['intent']=='explain':
                            value+=.04 if r['kind']=='passage' else -.03
                            years_in_label=re.findall(r'\b20\d{2}\b',r['label'])
                            if len(years_in_label)>=2 and annual_explanation(query):
                                value+=.025 if len(set(years_in_label))>1 else -.02
                        elif tag:
                            value+=.08 if tag in r['metric_tags'] else -.04
                            value+=.04 if r['kind']=='financial_row' else -.04
                            if tag=='cash_profit' and re.search('before|discontinued|non cash',row): value-=.04
                            if tag=='statutory_npat' and 'continuing operations' in row: value-=.02
                            if tag=='basic_cash_eps':
                                value+=.03 if 'basic' in lab and 'cash' in lab else -.03
                                if 'diluted' in lab: value-=.04
                            if tag=='total_assets' and 'average' in lab: value-=.04
                            if tag=='operating_expenses':
                                if 'underlying' in lab or 'to total operating income' in row: value-=.04
                                if 'total operating expenses' in row: value+=.015
                            if tag=='nim' and 'cash' in lab: value+=.01
                            if 'continuing operations' in norm(query):
                                if 'from continuing operations' in lab or 'group continuing operations' in lab: value+=.015
                                if 'including discontinued' in lab: value-=.03
                        if '_ar' in r['source']['document_id'] and not p['annual_report_only'] and p['intent']!='reconcile': value-=.005
                        scores[i]=value
                    order=sorted(scores,key=lambda i:(-scores[i],self.records[i]['chunk_id']))
                    if method=='hybrid_rerank':
                        if self.reranker is None: raise ValueError('Reranker required')
                        pool=order[:20]
                        # Rerank a typed candidate shortlist; keep all source text intact.
                        order=sorted(pool,key=lambda i:(-self.reranker.score(canonical,self.records[i]['text']),-scores[i]))
                    branches.append(order)
                    candidate_ids.append([self.records[i]['chunk_id'] for i in order[:self.config['candidate_k']]])
        picked=[]
        for depth in range(self.config['per_branch']):
            for branch in branches:
                if depth<len(branch) and branch[depth] not in picked: picked.append(branch[depth])
        if p['intent']=='reconcile':
            # Existing, source-based bridge assembly is retained as a candidate source.
            # Its result is not treated as evidence of answerability.
            legacy=super().search('Reconcile financial disclosures. '+canonical,query_vector)
            lookup={r['chunk_id']:i for i,r in enumerate(self.records)}
            eligible=[lookup[r['chunk_id']] for r in legacy['records']
                      if r['source']['company'] in p['companies']
                      and (None in years or r['source']['report_year'] in years)
                      and (not p['annual_report_only'] or '_ar' in r['source']['document_id'])]
            picked=list(dict.fromkeys(eligible+picked))
            if p.get('reconciliation_type')=='presentation_reclassification':
                # A change and its amount can occupy separate adjacent paragraphs.
                # Expand bounded local context from ranked passages, never gold IDs.
                expanded=[]
                anchors=[i for i in picked if self.records[i]['kind']=='passage'][:3]
                for i in picked:
                    expanded.append(i)
                    if i not in anchors: continue
                    anchor=self.records[i]
                    positions=[int(u.rsplit(':b',1)[1]) for u in anchor['unit_ids'] if ':r' not in u]
                    for j,r in enumerate(self.records):
                        if r['kind']!='passage' or r['source']!=anchor['source'] or r['label']!=anchor['label'] or len(r['body'])>=1800:
                            continue
                        if any(0<abs(int(u.rsplit(':b',1)[1])-pos)<=2 for u in r['unit_ids'] if ':r' not in u for pos in positions):
                            expanded.append(j)
                picked=list(dict.fromkeys(expanded))
        result={'plan':p,'records':[self.records[i] for i in picked],'candidates':candidate_ids}
        if not picked:
            result['plan']={**p,'behavior':'abstain','reason':'No eligible candidate evidence found.'}
        return result
