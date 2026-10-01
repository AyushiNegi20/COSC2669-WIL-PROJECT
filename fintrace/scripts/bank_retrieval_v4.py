"""Typed local evidence retrieval. No evaluation keys, reference values or page maps.

Builds a separate evidence view from v3's verified frozen source corpus.
"""
from collections import defaultdict
import hashlib
import re
import numpy as np
from bank_retrieval import (ROOT, read, save, sha, canonical, source_units, build_corpora,
    full_fragment, Encoder, tokenizer_for, BM25, plan_query, fragments, execution_profile)

CONFIG4 = ROOT/'config/banking_retrieval_v4.json'
OUT4 = ROOT/'data/processed/banking_retrieval_v4'
REPORT4 = ROOT/'reports/banking_retrieval_v4'


def norm(text):
    return ' '.join(re.findall(r'[a-z]+|[0-9]+',text.lower()))


def metrics(text):
    s=norm(text)
    found=[]
    rules={
      'basic_cash_eps':r'earnings per share|\beps\b',
      'dividend_per_share':r'dividend.*per share|\bdps\b|annual dividend|full year dividend',
      'nim':r'net interest margin|\bnim\b',
      'gross_loans':r'gross loans|loans and acceptances|\bglas\b',
      'customer_deposits':r'customer deposits|customer funding',
      'total_assets':r'total assets|balance sheet assets',
      'cet1':r'\bcet\s?1\b|common equity tier (?:1|one)',
      'lcr':r'liquidity coverage|\blcr\b',
      'operating_income':r'(?:total|net) operating income|operating revenue',
      'operating_expenses':r'operating expenses|operating costs',
      'credit_impairment':r'(?:credit|loan) impairment|impairment (?:charge|expense)',
      'cash_profit':r'cash (?:profit|net profit)|cash earnings(?! per share)|net profit.*cash basis',
      'statutory_npat':r'statutory.*(?:profit|npat)|(?:profit|npat).*statutory|net profit attributable',
    }
    for key,pattern in rules.items():
        if re.search(pattern,s):
            found.append(key)
    return found


def intent(question):
    s=norm(question)
    if re.search(r'what (?:does|do|is meant)|\bdefin|meaning of|what is .*(?:nim|lcr|cash earnings)|stand for',s):
        return 'define'
    if re.search(r'reconcil|non cash adjustments|linking.*statutory|reclassification|restat|comparatives different|originally reported.*comparative',s):
        return 'reconcile'
    if re.search(r'\bwhy\b|what drove|what factors|drivers|explain|affect|attribute|pressure',s):
        return 'explain'
    if re.search(r'summari|summary|brief|snapshot|roundup',s):
        return 'summary'
    if re.search(r'compare|change|growth|grew|difference|versus|\bvs\b',s):
        return 'compare'
    return 'find'


def plan(question):
    base=plan_query(question)
    s=norm(question)
    if 'commonwealth' in s and 'CBA' not in base['companies']:
        base['companies'].insert(0,'CBA')
    kind=intent(question)
    tags=metrics(question)
    named_reports=re.findall(r'\b(?:FY\s*)?(20\d{2})\s+(?:annual report|profit announcement|results report|report)\b',question,re.I)
    if len(set(named_reports))==1 and not (len(base['value_years'])>1 and re.search('original',question,re.I)):
        base['report_year']=int(named_reports[0])
    definition=re.search(r'what does (.*?) mean|meaning of (.*?) (?:as |in |according)|define (.*?)(?:\?|$)',question,re.I)
    definition_term=next((x for x in definition.groups() if x),None) if definition else None
    behavior='answer'
    reason=None
    if re.search(r'\b(?:anz|westpac|bhp|tesla)\b',s):
        behavior,reason='abstain','Requested company is outside the CBA/NAB source corpus.'
    elif re.search(r'\bmy\b.*\b(?:account|balance|savings|loan)\b',s):
        behavior,reason='abstain','Public company reports do not establish personal account information.'
    elif any(y>2025 or y<2024 for y in base['value_years']):
        behavior,reason='abstain','Requested year is outside the supported FY2024/FY2025 scope.'
    elif re.search(r'predict|forecast.*profit|next year.*profit|will.*profit',s):
        behavior,reason='abstain','The corpus cannot establish future realised profit.'
    elif base['ambiguity'] and kind not in ('define','reconcile'):
        behavior,reason='clarify',base['ambiguity']
    elif not base['companies'] and kind!='define':
        behavior,reason='clarify','Specify CBA or NAB and the reporting period.'
    return {**base,'intent':kind,'metrics':tags,'definition_term':definition_term,'behavior':behavior,'reason':reason}


def metric_label(tag):
    return {'statutory_npat':'statutory net profit attributable to owners',
      'cash_profit':'cash profit cash earnings','basic_cash_eps':'basic cash earnings per share',
      'dividend_per_share':'dividend per share','gross_loans':'gross loans and acceptances',
      'customer_deposits':'customer deposits','total_assets':'total assets',
      'cet1':'common equity tier 1 capital ratio CET1','lcr':'liquidity coverage ratio',
      'nim':'net interest margin','operating_income':'total net operating income',
      'operating_expenses':'operating expenses','credit_impairment':'credit loan impairment charge'}.get(tag,tag or '')


def build_view():
    corpora,parents,raw,units=build_corpora()
    _,pages=source_units()
    blocks={b['id']:b for p in pages.values() for b in p['blocks']}
    glossary_pages=set()
    previous={}
    for page in sorted(pages.values(),key=lambda p:(p['source']['document_id'],p['source']['pdf_page'])):
        doc=page['source']['document_id'];number=page['source']['pdf_page']
        explicit=any(re.search(r'glossary|definitions|defined terms',b.get('text',''),re.I) for b in page['blocks'][:8])
        pairs=sum(b['type']=='section_header' and len(b.get('text','').split())<9 for b in page['blocks'])
        continuation=previous.get(doc)==number-1 and pairs>=8
        if explicit or continuation:
            glossary_pages.add(page['id']);previous[doc]=number
    rows=[]
    seen=set()
    def add(key,kind,source,body,label,unit_ids,extra=None):
        if key in seen:
            return
        seen.add(key)
        evidence=list(dict.fromkeys(unit_ids))
        record={'chunk_id':key,'kind':kind,'source':source,'body':body,'label':label,
            'metric_tags':metrics(label),'unit_ids':evidence,
            'fragments':[full_fragment(u,units[u]) for u in evidence],
            'quality':{'status':'development_unreviewed','independent_review':'pending','calculation_ready':False},
            'text':source['document_title']+' | PDF page '+str(source['pdf_page'])+'\n'+body,
            'search_text':source['company']+' FY'+str(source['report_year'])+' '+kind+' '+label+'\n'+body}
        if extra:
            record.update(extra)
        rows.append(record)
    for child in corpora['structured']:
        if child['quality']['status']=='quarantined':
            continue
        for anchor in child['anchors']:
            block=blocks[anchor['evidence_id']]
            if anchor['type']=='table_rows':
                for ri in anchor['rows']:
                    row=block['rows'][ri]
                    deps=list(dict.fromkeys(anchor['header_rows']+anchor['context_rows']))
                    table_glossary=child['kind']=='definition'
                    if not table_glossary and not any(row[1:]):
                        continue
                    label=' / '.join([block['rows'][n][0] for n in anchor['context_rows']]+[row[0]])
                    ids=[f"{block['id']}:r{n}" for n in deps+[ri]]
                    # Short real notes remain attached, never separate competitors.
                    notes=[]
                    for note_id in child.get('related_chunk_ids',[]):
                        note=raw[note_id]
                        if note['quality']['status']=='quarantined':
                            continue
                        text=note['text'].split('\n')[-1]
                        if re.search(r'average|quarter|restat|comparative|\bexclud|\binclud|\bAPRA\b',text,re.I) and len(text)<600:
                            notes.extend(f['unit'] for f in fragments(note,units))
                    ids+=list(dict.fromkeys(notes))
                    body='\n'.join(units[u] for u in dict.fromkeys(ids))
                    add('v4:'+block['id']+f':r{ri}','definition' if table_glossary else 'financial_row',child['source'],body,label,ids,
                        {'table_id':block['id'],'row':ri,'row_label':row[0],
                         'dependency_units':[u for u in ids if u!=f"{block['id']}:r{ri}"]})
            else:
                if block['type'] in ('section_header','page_header','page_footer','caption'):
                    continue
                body=units[block['id']][anchor['start']:anchor['end']]
                if len(re.findall('[A-Za-z]+',body))<5:
                    continue
                ids=[u for u in child['evidence_ids'] if u in units]
                headings=[units[u] for u in ids if u!=block['id']]
                # Glossary pages identify themselves; no fixed page-number list.
                page=pages[block['id'].rsplit(':',1)[0]]
                is_definition=page['id'] in glossary_pages
                # Label is the nearest literal heading, not a generated fact.
                label=headings[-1] if headings else body[:160]
                text='\n'.join(units[u] for u in ids)
                add('v4:'+child['chunk_id'],'definition' if is_definition else 'passage',child['source'],text,label,ids)
    return rows,units


class EvidenceRetriever:
    def __init__(self,records,units,vectors=None):
        eligible=[i for i,r in enumerate(records) if r['quality']['status']!='quarantined']
        if vectors is not None:
            if len(vectors)!=len(records):
                raise ValueError('Vector rows must match evidence records')
            vectors=vectors[eligible]
        records=[records[i] for i in eligible]
        self.records,self.units,self.vectors=records,units,vectors
        self.config=read(CONFIG4)
        self.lexical=BM25([r['search_text'] for r in records])
        self.label_lexical=BM25([r['label'] for r in records])

    def search(self,question,query_vector=None):
        p=plan(question)
        if p['behavior']!='answer':
            return {'plan':p,'records':[],'candidates':[]}
        base=self.lexical.score(question)
        dense=self.vectors@query_vector if self.vectors is not None and query_vector is not None else np.zeros(len(self.records))
        requests=[]
        tags=p['metrics'] if p['intent'] in ('find','compare','summary','reconcile') and p['metrics'] else [None]
        cash_bridge=p['intent']=='reconcile' and 'cash_profit' in p['metrics'] and 'statutory_npat' in p['metrics']
        if cash_bridge:
            tags=['cash_profit']
        for company in p['companies'] or [None]:
            for tag in tags:
                # Multiple report vintages only when explicitly requested.
                years=p['value_years'] if len(p['value_years'])>1 and re.search('original|comparative in',question,re.I) else [p['report_year']]
                for year in years:
                    requests.append((company,tag,year))
        branch_results=[]
        for company,tag,year in requests:
            label_scores=self.label_lexical.score(p['definition_term'] or (metric_label(tag) if tag else question))
            allowed=[i for i,r in enumerate(self.records) if (not company or r['source']['company']==company)
                     and (not year or r['source']['report_year']==year)
                     and (not p['annual_report_only'] or '_ar' in r['source']['document_id'])]
            scores={}
            for i in allowed:
                r=self.records[i]
                score=float(base[i])+float(dense[i])*10
                if p['intent']=='define':
                    score+=float(label_scores[i])*2
                    score+=30 if r['kind']=='definition' else -20
                    if p['definition_term'] and set(norm(p['definition_term']).split())<=set(norm(r['label']).split()):
                        score+=40
                elif p['intent']=='explain':
                    score+=12 if r['kind']=='passage' else -20
                elif tag:
                    score+=float(label_scores[i])*2
                    score+=30 if tag in r['metric_tags'] else -30
                    score+=15 if r['kind']=='financial_row' else -15
                    label=norm(r['label'])
                    if tag=='cash_profit':
                        if re.search('before|discontinued operations|non cash',norm(r.get('row_label',''))): score-=25
                    if tag=='statutory_npat':
                        if 'continuing operations' in norm(r.get('row_label','')): score-=15
                    if tag=='total_assets' and 'average' in label: score-=25
                    if tag=='basic_cash_eps':
                        score+=15 if 'cash' in label and 'basic' in label else -15
                        if 'diluted' in label: score-=20
                    if tag=='operating_expenses' and 'underlying' in label: score-=15
                    if tag=='nim':
                        score+=8 if 'cash' in label else 0
                    if 'continuing operations' in norm(question):
                        score+=8 if 'from continuing operations' in label or 'group continuing operations' in label else 0
                        score-=15 if 'including discontinued' in label else 0
                elif p['intent']=='reconcile':
                    score+=8 if r['kind'] in ('financial_row','passage') else -20
                if '_ar' in r['source']['document_id'] and not p['annual_report_only'] and p['intent']!='reconcile':
                    score-=3
                scores[i]=score
            order=sorted(allowed,key=lambda i:(-scores[i],self.records[i]['chunk_id']))[:self.config['candidate_k']]
            branch_results.append(order)
        picked=[]
        for depth in range(self.config['per_branch']):
            for branch in branch_results:
                if depth<len(branch) and branch[depth] not in picked:
                    picked.append(branch[depth])
        if cash_bridge:
            tables=defaultdict(list)
            for i,r in enumerate(self.records):
                if r['kind']=='financial_row' and (not p['companies'] or r['source']['company'] in p['companies']) and (not p['report_year'] or r['source']['report_year']==p['report_year']):
                    tables[r['table_id']].append(i)
            bridges=[]
            for table,indices in tables.items():
                cash=[i for i in indices if 'cash_profit' in self.records[i]['metric_tags'] and not re.search('before|discontinued',norm(self.records[i]['row_label']))]
                statutory=[i for i in indices if 'statutory_npat' in self.records[i]['metric_tags']]
                adjustments=[i for i in indices if re.search('non.cash|hedging|amortisation|acquisitions',self.records[i]['row_label'],re.I)]
                if cash and statutory and adjustments:
                    lo=min(self.records[i]['row'] for i in cash)
                    hi=max(self.records[i]['row'] for i in statutory)
                    chosen=[i for i in indices if lo<=self.records[i]['row']<=hi]
                    bridges.append((sum(float(base[i]) for i in chosen),chosen))
            if bridges:
                picked=max(bridges,key=lambda x:x[0])[1]
        if picked and p['intent']=='reconcile' and re.search(r'reclassif|restat',question,re.I):
            # A presentation change often spans adjacent paragraphs in one section.
            # Expand only through eligible records; do not fetch raw unknown-quality text.
            top=self.records[picked[0]]
            if top['kind']=='passage':
                body_ids=[u for u in top['unit_ids'] if ':r' not in u]
                last=max(int(u.rsplit(':b',1)[1]) for u in body_ids)
                neighbors=[i for i,r in enumerate(self.records) if r['kind']=='passage'
                    and r['source']==top['source'] and r['label']==top['label']
                    and any(abs(int(u.rsplit(':b',1)[1])-last)==1 for u in r['unit_ids'] if ':r' not in u)
                    and len(r['body'])<1800]
                picked=list(dict.fromkeys([picked[0]]+neighbors+picked[1:]))
        return {'plan':p,'records':[self.records[i] for i in picked],
                'candidates':[[self.records[i]['chunk_id'] for i in branch] for branch in branch_results]}

    def context(self,result,tokenizer,budget=None):
        budget=budget or self.config['context_tokens']
        included=[];omitted=[];seen=set()
        # Compact source-unit bundles deduplicate headers within each document.
        for record in result['records']:
            fresh=[u for u in record['unit_ids'] if u not in seen]
            if not fresh:
                continue
            trial=included+[record]
            text=self.render(trial)
            if len(tokenizer.encode(text,truncation=False))>budget:
                omitted.append(record['chunk_id']);continue
            included.append(record);seen.update(fresh)
        text=self.render(included)
        return {'records':included,'text':text,'tokens':len(tokenizer.encode(text,truncation=False)),
                'omissions':omitted,'quality':'development_unreviewed','calculation_ready':False}

    def render(self,records):
        groups=defaultdict(list)
        for r in records:
            groups[(r['source']['document_id'],r['source']['pdf_page'])].append(r)
        parts=[]
        for _,items in groups.items():
            source=items[0]['source']
            parts.append(source['document_title']+' | PDF page '+str(source['pdf_page']))
            ids=list(dict.fromkeys(u for r in items for u in r['unit_ids']))
            # Preserve table/paragraph source order, not retrieval score order.
            def ordering(u):
                block,sep,row=u.partition(':r')
                return block,int(row) if sep else -1
            parts.extend('['+u+'] '+self.units[u] for u in sorted(ids,key=ordering))
        return '\n'.join(parts)


def embedding_cache(texts,query=False):
    OUT4.mkdir(parents=True,exist_ok=True)
    spec=read(ROOT/'config/banking_retrieval.json')['models']['qwen']
    profile=execution_profile()
    signature={'texts':texts,'query':query,'model':spec,'execution_profile':profile,
               'encoder_sha256':sha(ROOT/'scripts/bank_retrieval.py')}
    identity=hashlib.sha256(canonical(signature).encode()).hexdigest()
    path=OUT4/f"{'queries' if query else 'index'}_{identity[:16]}.npz"
    if path.exists():
        meta=read(path.with_suffix('.json'))
        if meta['input_sha256']!=identity or meta['array_sha256']!=sha(path):
            raise ValueError('Embedding cache failed integrity check')
        with np.load(path,allow_pickle=False) as cached:
            vectors=cached['embeddings']
        if vectors.ndim!=2 or len(vectors)!=len(texts) or not np.isfinite(vectors).all():
            raise ValueError('Invalid cached embedding matrix')
        return vectors
    encoder=Encoder('qwen')
    vectors=encoder.encode(texts,query=query)
    np.savez_compressed(path,embeddings=vectors)
    save(path.with_suffix('.json'),{'input_sha256':identity,'model':spec,'execution_profile':profile,
        'encoder_sha256':signature['encoder_sha256'],'query':query,
        'array_sha256':sha(path),'records':len(texts)})
    return vectors


def vectors_for(records):
    return embedding_cache([r['search_text'] for r in records])
