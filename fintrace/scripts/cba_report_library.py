"""Supplementary CBA full-report evidence, separate from the frozen cell index.

Reads issuer PDFs only. No evaluation files, expected figures or answer keys.
Full-page text is searchable, but only prose blocks are offered for synthesis.
Investment arithmetic has an explicit, independently cross-extracted table path.
"""
from collections import Counter
from copy import deepcopy
from decimal import Decimal
from hashlib import sha256
import json
import math
from pathlib import Path
import re
from functools import lru_cache

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT/'data/processed/cba_full_reports/library_v6.json'
SCHEMA = 6
ROW_LABELS = ('Expensed investment spend', 'Capitalised investment spend',
              'Investment spend', 'Productivity and growth', 'Risk and compliance',
              'Infrastructure and branch refurbishment')
STOP = set('a an the is are was were be been what which who how did does do doing of to for from in on at by with and or as its it their this that these those please tell me about cba commonwealth bank australia fy fy2024 fy2025 2024 2025 report reports explain reported says say much more direction areas year discuss mean'.split())
STOP.update(('nab', 'national', 'can', 'could', 'us', 'describe', 'describes', 'described'))


def clean(text):
    return re.sub(r'\s+', ' ', text).strip()


def column_overlap(a, b):
    return max(0, min(a[2], b[2])-max(a[0], b[0])) / max(1, min(a[2]-a[0], b[2]-b[0]))


def period_for(block, raw_blocks):
    """Prefer explicit headings in the same column; never borrow a conflicting one.

    Some PDF headings are graphical, not text. An introductory paragraph's
    explicit 'prior year/half' supplies a bounded period cue in that column.
    """
    markers = []
    for h in raw_blocks:
        if h[6] != 0 or h[1] > block[1]+5:
            continue
        text = clean(h[4])
        heading = re.fullmatch(r'((?:Half Year|Year) Ended [A-Za-z]+ 20\d{2} versus [A-Za-z]+ 20\d{2})', text, re.I)
        label = heading[1] if heading else ''
        if not label and not text.startswith(('•', '-')) and re.search(r'\b(?:was|were|increased|decreased)\b',text,re.I):
            # A first sentence explicitly describing the period, not a later
            # reference to prior provision releases inside an annual paragraph.
            first = text.split('. ')[0]
            if re.search(r'\bon the prior half\b',first,re.I): label = 'Half year comparison (prior half)'
            elif re.search(r'\bon the prior year\b',first,re.I): label = 'Year comparison (prior year)'
        if label:
            markers.append((h[1], label, column_overlap(h,block)))
    local = [m for m in markers if m[2] >= .5]
    if local:
        return max(local,key=lambda m:m[0])[1]
    # A single explicit annual heading can govern both columns on an expense
    # page. It cannot cross into a competing half-year section.
    labels = {m[1] for m in markers}
    if len(labels) == 1 and markers:
        return markers[-1][1]
    return ''


def attach_explanation_context(blocks):
    """Attach contiguous same-column bullets to a 'driven by:' introduction."""
    for lead in blocks:
        if not re.search(r'(?:driven by|reflects?|reflecting|due to|as follows)\s*:$',lead['quote'],re.I):
            continue
        linked = [lead]
        candidates = sorted((b for b in blocks if b is not lead and b['bbox'][1]>=lead['bbox'][3]-2
                             and column_overlap(b['bbox'],lead['bbox'])>=.7),key=lambda b:b['bbox'][1])
        for b in candidates:
            if b['period_context'] != lead['period_context'] or b['bbox'][1]-linked[-1]['bbox'][3]>22:
                break
            if not b['quote'].startswith('•'):
                break
            linked.append(b)
        if len(linked)>1:
            text = ' '.join(b['quote'] for b in linked)
            if len(text)<=4500:
                lead['parent_quote'] = text
                lead['parent_source_ids'] = [b['source_id'] for b in linked]


def words(text):
    terms = re.findall(r'[a-z]+', text.lower())
    result = []
    for t in terms:
        if t in STOP: continue
        if t.startswith('invest'): t = 'invest'
        elif t.startswith('strateg'): t = 'strategy'
        elif t.startswith('priorit'): t = 'priority'
        elif t.startswith('technolog'): t = 'technology'
        elif t.startswith('modernis') or t.startswith('moderniz'): t = 'modern'
        elif t.startswith('digit'): t = 'digital'
        elif t in ('genai',): result.extend(['generative','ai']); continue
        elif t.endswith('s') and len(t)>4: t=t[:-1]
        result.append(t)
    return result


def annual_rows(text, layout_text):
    """Bind the first two annual columns, never half-year columns or % columns.

    Require two extractors to agree on each labelled row, headers, currency,
    category totals and expensed/capitalised reconciliation. Fail closed.
    """
    rows = {}
    for label in ROW_LABELS:
        pattern = r'^\s*'+re.escape(label)+r'\s*[¹²]?\s+([\d,]+)\s+([\d,]+)\s+'
        primary = re.findall(pattern, text, re.M|re.I)
        secondary = re.findall(pattern, layout_text, re.M|re.I)
        if not primary or len(set(primary)) != 1 or not secondary or set(primary) != set(secondary):
            raise ValueError('Uncertain investment row: '+label)
        rows[label] = [str(Decimal(v.replace(',',''))) for v in primary[0]]
    prefix = text[:re.search(r'Expensed investment spend', text, re.I).start()]
    if not re.search(r'Full Year Ended',prefix,re.I) or '$M' not in prefix:
        raise ValueError('Annual period or million-dollar unit not established')
    dates = re.findall(r'30\s+Jun\s+(\d{2})',prefix)
    if len(dates)<2: raise ValueError('Annual date columns unavailable')
    years = [2000+int(x) for x in dates[:2]]
    if years[0] != years[1]+1: raise ValueError('Unexpected annual columns')
    for i in (0,1):
        total = Decimal(rows['Investment spend'][i])
        if sum(Decimal(rows[k][i]) for k in ROW_LABELS[3:]) != total:
            raise ValueError('Investment categories do not reconcile')
        if sum(Decimal(rows[k][i]) for k in ROW_LABELS[:2]) != total:
            raise ValueError('Investment accounting components do not reconcile')
    return {'years':years,'rows':rows,'unit':'AUD million','scope':'continuing operations',
            'validation':'pypdf_and_pymupdf_row_agreement_plus_two_reconciliations'}


def build():
    import pymupdf
    from pypdf import PdfReader
    specs = json.loads((ROOT/'config/banking_sources.json').read_text())['documents']
    records, inventory, investment = [], [], []
    for spec in specs:
        if spec['company'] != 'CBA': continue
        path = ROOT/'data/raw'/spec['file']
        if sha256(path.read_bytes()).hexdigest() != spec['sha256']:
            raise ValueError('Issuer PDF checksum changed: '+spec['id'])
        native = PdfReader(path)
        with pymupdf.open(path) as document:
            for i,page in enumerate(document):
                source = {'company':'CBA','document_id':spec['id'],'document_title':spec['title'],
                    'pdf_page':i+1,'report_year':spec['report_year'],'report_period_end':spec['period_end'],
                    'source_url':spec['url'],'source_sha256':spec['sha256']}
                text = native.pages[i].extract_text() or ''
                division=re.search(r'^\s*(Retail Banking Services|Business Banking|Institutional Banking and Markets|New Zealand|Corporate Centre and Other)(?:\s*\(continued\))?\s*$',text,re.M)
                if division and 'Divisional Performance' in text[:500]:
                    source['report_section']=division[1]
                elif 'NZD' in text and re.search(r'ASB|New Zealand',text):
                    source['report_section']='New Zealand'
                else:source['report_section']='Group or general disclosure'
                blocks = []
                raw_blocks=page.get_text('blocks')
                for j,b in enumerate(raw_blocks):
                    if b[6] != 0: continue
                    body = clean(b[4])
                    # Column-local layout blocks preserve paragraph order. Tables
                    # and labels remain in page text but are not narrative facts.
                    alpha = re.findall(r'[A-Za-z]+',body)
                    prose = len(alpha)>=10 and len(alpha)>len(re.findall(r'\d+',body))*2 and (
                        bool(re.search(r'[.;:]\s*$',body)) or body.startswith('•'))
                    if not prose or len(body)>2200: continue
                    if 'Commonwealth Bank of Australia' in body and 'Profit Announcement' in body: continue
                    blocks.append({'source_id':f"{spec['id']}:full:p{i+1:03}:b{j:03}", 'quote':body,
                                   'period_context':period_for(b,raw_blocks), 'bbox':list(b[:4])})
                attach_explanation_context(blocks)
                headings = [clean(b[4]) for b in page.get_text('blocks') if b[6]==0 and 3<len(clean(b[4]))<130 and not re.fullmatch(r'[\d\s,.()%$–-]+',clean(b[4]))]
                record = {'source':source,'text':text,'blocks':blocks,'headings':headings[:12]}
                records.append(record)
                inventory.append({'document':spec['id'],'page':i+1,'characters':len(text),
                                  'prose_blocks':len(blocks),'headings':headings[:5]})
                if all(label.lower() in text.lower() for label in ROW_LABELS):
                    try:
                        table = annual_rows(text,page.get_text(sort=True))
                        if table['years'][0] != spec['report_year']: raise ValueError('Wrong report year')
                        investment.append({**table,'source':source,'page_text':text,'blocks':blocks})
                    except ValueError as error:
                        inventory[-1]['investment_rejection'] = str(error)
    result = {'schema':SCHEMA,'records':records,'investment_tables':investment,
              'documents':{d['id']:d['sha256'] for d in specs if d['company']=='CBA'},
              'inventory':inventory,
              'limitations':['All native-text pages scanned; not every page visually reviewed.',
                             'Full-report prose is machine-extracted, not a human-certified corpus.',
                             'Only investment tables passing row/header/reconciliation checks extend numerical binding.']}
    CACHE.parent.mkdir(parents=True,exist_ok=True)
    CACHE.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    CACHE.with_suffix('.sha256').write_text(sha256(CACHE.read_bytes()).hexdigest(),encoding='ascii')
    return result


class Library:
    def __init__(self, data=None):
        if data is None:
            data = json.loads(CACHE.read_text(encoding='utf-8')) if CACHE.exists() else build()
            if not CACHE.with_suffix('.sha256').exists() or sha256(CACHE.read_bytes()).hexdigest()!=CACHE.with_suffix('.sha256').read_text().strip():
                raise ValueError('Full-report cache checksum failed; rebuild from the PDFs')
            specs=json.loads((ROOT/'config/banking_sources.json').read_text())['documents']
            for d in specs:
                if d['company']=='CBA' and (data['documents'].get(d['id']) != d['sha256'] or
                    sha256((ROOT/'data/raw'/d['file']).read_bytes()).hexdigest()!=d['sha256']):
                    raise ValueError('Full-report cache/source mismatch')
        if data['schema'] != SCHEMA: raise ValueError('Rebuild the CBA report library')
        self.data=data
        self.vocabulary=set(re.findall(r'[a-z]+',' '.join(p['text'] for p in data['records']).lower()))
        self.blocks=[{**b,'source':p['source']} for p in data['records'] for b in p['blocks']]
        self.counts=[Counter(words(b.get('parent_quote',b['quote']))) for b in self.blocks]
        self.df=Counter(t for count in self.counts for t in count)
        self.avg=sum(sum(c.values()) for c in self.counts)/max(1,len(self.counts))

    def unmatched_subject(self,question):
        # Named entities cannot silently disappear during broad topic retrieval.
        # This is a lexical safety gate, not a proof that a report lacks a fact.
        named=re.findall(r'\b[A-Z][a-z]{2,}\b',question)
        first=re.match(r'\s*([A-Za-z]+)',question)
        ignore=set('What Which Where When Why How Does Did Has Can Give Explain Describe Compare Choose Please In For The Is Are Show Assume Ignore Say Answer Return Tell Report FY Commonwealth Bank Australia National New Zealand'.lower().split())
        if first:ignore.add(first[1].lower())
        named += re.findall(r'\b(?:on|in|for)\s+(?:an?\s+|the\s+)?([a-z][\w-]+)\s+(?:branch|project|platform|venture|acquisition)\b',question,re.I)
        return sorted({w for w in named if w.lower() not in ignore and w.lower() not in self.vocabulary})

    def search(self, question, year, top_k=5, purpose=None, company='CBA'):
        from bank_evidence_relevance import relevance
        from bank_query_routing import explanation_subject
        subject = explanation_subject(question)
        statutory = bool(re.search(r'\bstatutory\b|income.statement', question, re.I))
        statutory_pages = {(p['source']['document_id'], p['source']['pdf_page']) for p in self.data['records']
            if re.search(r'Financial performance\s+Group\s+20\d{2}\s+20\d{2}', p['text'], re.I)} if statutory and company == 'NAB' else None
        terms=set(words(question)); ranked=[]
        query_words = words(question)
        query_pairs = set(zip(query_words, query_words[1:]))
        # Expand common user phrasing, without changing numerical metric identity.
        if 'ai' in terms: terms.update(('generative','artificial','intelligence'))
        if 'scam' in terms: terms.add('fraud')
        if re.search(r'\bit\s+(?:service\w*\s+)?(?:cost\w*|expense\w*|spend\w*)\b',question,re.I):
            terms.update(('information','technology','service','expense'))
        if terms.intersection(('staff','personnel','payroll','wage','salary','salarie')):
            terms.update(('staff','personnel','salary','wage'))
        # Narrative vocabulary only. These expansions never bind a number or
        # make a subset such as housing equivalent to total loans.
        if terms.intersection(('lending','loan','mortgage','mortgages')):
            terms.update(('lending','loan'))
        if terms.intersection(('grew','grow','growth','expanded','expand','rise','rose','increased')):
            terms.update(('growth','increase','increased'))
        if 'invest' in terms: terms.update(('spend','productivity','infrastructure'))
        if re.search(r'\bput(?:ting|s)?\s+(?:more\s+)?money\b|\bspend(?:ing)? priorities\b',question,re.I):
            terms.update(('invest','spend'))
        if terms.intersection(('performance','overview','summary','result','highlight')):
            terms.update(('profit','income','expense','increase','decrease'))
        if not terms: return []
        for block,count in zip(self.blocks,self.counts):
            if block['source']['report_year']!=year or block['source']['company']!=company: continue
            if not relevance(question,block.get('parent_quote',block['quote']))[0]: continue
            if subject:
                body = block.get('parent_quote', block['quote'])
                if not re.search(r'^\s*(?:Group\s+)?' + subject + r'.{0,100}\b(?:increas\w*|decreas\w*|grew|fell|rose|was|were|reflect\w*|driven|due)\b', body, re.I):
                    continue
                if statutory_pages is not None and (block['source']['document_id'], block['source']['pdf_page']) not in statutory_pages:
                    continue
            section=block['source'].get('report_section','Group or general disclosure')
            if section!='Group or general disclosure' and not re.search(re.escape(section)+r'|\bASB\b' if section=='New Zealand' else re.escape(section),question,re.I):
                continue
            if block.get('period_context','').lower().startswith('half year') and not re.search(r'half.year|six months',question,re.I):continue
            if block.get('period_context','').lower().startswith('year') and re.search(r'half.year|six months',question,re.I):continue
            overlap=terms.intersection(count)
            if not overlap: continue
            if purpose == 'definition':
                body_words = words(block['quote'])
                # Prefer actual meaning/basis disclosures about the requested
                # phrase, not every short KPI footnote containing 'cash'. No
                # financial answer, page or metric alias is hardcoded here.
                phrase_match = bool(query_pairs.intersection(zip(body_words, body_words[1:])))
                if len(terms) == 1:
                    phrase_match = bool(overlap)
                definition_language = re.search(r'\b(?:means?|defined|represents?|refers? to|calculated|based on|basis is|(?:is|are) (?:not )?a measure|excluded from)\b', block['quote'], re.I)
                if not phrase_match or not definition_language:
                    continue
            score=0
            length=sum(count.values())
            for t in overlap:
                idf=math.log(1+(len(self.blocks)-self.df[t]+.5)/(self.df[t]+.5))
                freq=count[t]; score+=idf*freq*2.2/(freq+1.2*(.25+.75*length/max(1,self.avg)))
            body_words = words(block.get('parent_quote', block['quote']))
            if purpose == 'definition':
                # A definition of the requested term should outrank a definition
                # of another term that merely uses it in a formula.
                leading = set(zip(body_words[:7], body_words[1:8]))
                score += 8 * len(query_pairs.intersection(leading))
            # Phrase continuity distinguishes a requested measure from a passage
            # mentioning scattered words. This is not a financial synonym map.
            for width in (2,3):
                query_grams = set(zip(*(query_words[i:] for i in range(width))))
                body_grams = set(zip(*(body_words[i:] for i in range(width))))
                score += width * 2 * len(query_grams.intersection(body_grams))
            if block.get('parent_quote') and re.search(r'\bwhy\b|\breasons?\b|\bdrivers?\b|\bexplain\b',question,re.I):
                score += 8
            if block['source'].get('document_role') == 'primary': score += .75
            # Claim checking should retrieve the passage containing a quoted
            # amount, without treating that amount as true or calculation-ready.
            amounts=set(re.findall(r'\b\d[\d,]*(?:\.\d+)?\b',question)) - {'2024','2025'}
            if amounts and any(v.replace(',','') in b.replace(',','') for v in amounts for b in [block['quote']]):
                score+=5
            ranked.append((score,block))
        ranked.sort(key=lambda v:(-v[0],v[1]['source_id']))
        result=[]; seen=set()
        for score,b in ranked:
            body = b.get('parent_quote',b['quote'])
            if body in seen: continue
            seen.add(body)
            result.append({'source':deepcopy(b['source']),'heading':'Full-report prose search. '+b['source'].get('report_section','')+'. '+b.get('period_context',''),
                           'excerpts':[{'source_id':b['source_id'],'quote':body,
                                        'period_context':b.get('period_context',''),
                                        **({'component_source_ids':b.get('parent_source_ids',b.get('component_source_ids'))}
                                           if b.get('parent_source_ids') or b.get('component_source_ids') else {})}],
                           'retrieval_score':score,'retrieval_method':'full_report_bm25_definition' if purpose == 'definition' else 'full_report_bm25'})
            if len(result)==top_k: break
        return result


@lru_cache(maxsize=1)
def get_library():
    return Library()


if __name__=='__main__':
    data=build()
    print(json.dumps({'pages':len(data['records']),'blocks':sum(len(p['blocks']) for p in data['records']),
                      'investment_tables':[(t['source']['document_id'],t['source']['pdf_page']) for t in data['investment_tables']],
                      'empty_pages':[(p['document'],p['page']) for p in data['inventory'] if not p['characters']]}))
