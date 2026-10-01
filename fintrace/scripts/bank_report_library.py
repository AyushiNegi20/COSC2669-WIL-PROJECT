"""Shared full-report prose retrieval for the six frozen CBA/NAB PDFs.

No reference answers or expected metric values are runtime inputs. Numerical
tables remain on their existing validated path. This is supplementary prose.
"""
from copy import deepcopy
from functools import lru_cache
from hashlib import sha256
import json
import re

from cba_report_library import (ROOT, SCHEMA, Library, clean, column_overlap,
    period_for, attach_explanation_context, get_library as cba_library)

CACHE = ROOT/'data/processed/bank_full_reports/library_v3.json'
DIVISIONS = ('Business and Private Banking', 'Personal Banking',
             'Corporate and Institutional Banking', 'New Zealand Banking',
             'Corporate Functions and Other')


def cba_division(text, existing):
    """Recover explicit divisional scope when graphical headings lack text.

    Require a unique literal division introducing its own result or capital
    generation. Do not infer scope from incidental mentions or page numbers.
    """
    names=('Retail Banking Services','Business Banking','Institutional Banking and Markets',
           'Corporate Centre and Other','New Zealand')
    found=[name for name in names if re.search(re.escape(name)+
        r'\s+(?:cash net (?:profit|loss) after tax|generated\b[^.]{0,100}\borganic capital)',clean(text),re.I)]
    return found[0] if len(found)==1 else existing


def nab_period(block, raw):
    markers=[]
    for h in raw:
        if h[6] != 0 or h[1]>block[1]+5 or column_overlap(h,block)<.5:
            continue
        label=clean(h[4])
        match=re.fullmatch(r'(September|March) (20\d{2}) v(?:s|ersus)? (September|March) (20\d{2})',label,re.I)
        if match:
            m1,y1,m2,y2=match.groups()
            kind='Year comparison' if m1.lower()==m2.lower() and int(y1)==int(y2)+1 else 'Half year comparison'
            markers.append((h[1],kind+': '+label))
    return max(markers,key=lambda x:x[0])[1] if markers else period_for(block,raw)


def nab_blocks(page, spec):
    raw=page.get_text('blocks')
    title_candidates=[clean(b[4]) for b in raw if b[6]==0 and b[1]<100 and 3<len(clean(b[4]))<160]
    division=next((d for d in DIVISIONS if any(re.fullmatch(re.escape(d)+r'(?:\s*\(cont(?:inued)?\.?\))?',h,re.I)
                                               for h in title_candidates)), 'Group or general disclosure')
    glossary=any(h.lower().startswith('glossary') for h in title_candidates)
    blocks=[]
    merged = {}; consumed = set()
    for j, first in enumerate(raw[:-1]):
        second = raw[j+1]
        if first[6] != 0 or second[6] != 0 or j in consumed: continue
        a, b = clean(first[4]), clean(second[4])
        # Preserve a sentence split by the PDF layout engine, including a
        # continuation at the top of the next column. Never join full sentences
        # or infer a link between separate financial measures.
        same_column = column_overlap(first, second) > .6 and 0 <= second[1]-first[3] < 18
        next_column = first[0] < page.rect.width/2 < second[0] and second[1] < first[1] and re.search(r'\b(?:This|These|That|The)\s*$', a)
        if (len(re.findall(r'[A-Za-z]+', a)) >= 10 and not re.search(r'[.;:]$', a)
                and re.match(r'^[a-z]', b) and (same_column or next_column)):
            merged[j] = a+' '+b; consumed.add(j+1)
    for j,b in enumerate(raw):
        if b[6]!=0 or j in consumed:continue
        body=merged.get(j,clean(b[4])); alpha=re.findall(r'[A-Za-z]+',body)
        prose=len(alpha)>=10 and len(alpha)>len(re.findall(r'\d+',body))*2 and (
            bool(re.search(r'[.;:]\s*$',body)) or body.startswith('•') or glossary)
        short_bullet=body.startswith('•') and len(alpha)>=4 and len(alpha)>len(re.findall(r'\d+',body))*2
        if not (prose or short_bullet) or len(body)>4500:continue
        if b[1]>page.rect.height-35:continue
        block={'source_id':f"{spec['id']}:full:p{page.number+1:03}:b{j:03}",
               'quote':body,'period_context':nab_period(b,raw),'bbox':list(b[:4])}
        if j in merged:
            block['component_source_ids']=[f"{spec['id']}:full:p{page.number+1:03}:b{k:03}" for k in (j,j+1)]
        # Glossary definitions sometimes have a separate label block. Preserve
        # that literal label, never generate a definition or a numerical alias.
        if glossary:
            labels=[(k,h) for k,h in enumerate(raw) if h[6]==0 and 2<len(clean(h[4]))<110
                    and not clean(h[4]).lower().startswith('glossary') and h[3]<=b[1]+2
                    and b[1]-h[3]<14 and column_overlap(h,b)>.6]
            if labels:
                k,h=max(labels,key=lambda v:v[1][3])
                label=clean(h[4])
                block['quote']=label+'\n'+body
                block['label_source_id']=f"{spec['id']}:full:p{page.number+1:03}:b{k:03}"
        blocks.append(block)
    # Attach short enumerated exclusions as well as ordinary driver bullets.
    # The original joiner requires a literal lead phrase and same-column layout.
    attach_explanation_context(blocks)
    return blocks,division,title_candidates


def specs():
    return json.loads((ROOT/'config/banking_sources.json').read_text())['documents']


def build():
    import pymupdf
    original=cba_library().data
    records=deepcopy(original['records']); inventory=deepcopy(original['inventory'])
    documents={s['id']:s for s in specs()}
    for record in records:
        record['source']['document_role']=documents[record['source']['document_id']]['role']
        record['source']['report_section']=cba_division(record['text'],record['source'].get('report_section','Group or general disclosure'))
    for spec in documents.values():
        if spec['company']!='NAB':continue
        path=ROOT/'data/raw'/spec['file']
        if sha256(path.read_bytes()).hexdigest()!=spec['sha256']:
            raise ValueError('Issuer PDF checksum changed: '+spec['id'])
        with pymupdf.open(path) as document:
            for page in document:
                blocks,division,headings=nab_blocks(page,spec)
                text=page.get_text()
                source={'company':'NAB','document_id':spec['id'],'document_title':spec['title'],
                    'pdf_page':page.number+1,'report_year':spec['report_year'],
                    'report_period_end':spec['period_end'],'source_url':spec['url'],
                    'source_sha256':spec['sha256'],'document_role':spec['role'],'report_section':division}
                records.append({'source':source,'text':text,'blocks':blocks,'headings':headings})
                inventory.append({'document':spec['id'],'page':page.number+1,
                                  'characters':len(text),'prose_blocks':len(blocks),'headings':headings})
    data={'schema':SCHEMA,'library_kind':'cba_nab_full_reports_v3',
          'records':records,'inventory':inventory,'investment_tables':deepcopy(original['investment_tables']),
          'documents':{s['id']:s['sha256'] for s in documents.values()},
          'limitations':['Native-text prose from all six reports; no claim of complete image/table understanding.',
                        'Numerical validation coverage is separate from prose search coverage.',
                        'Cash/statutory, division and annual/half-year distinctions must remain visible.']}
    CACHE.parent.mkdir(parents=True,exist_ok=True)
    CACHE.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    CACHE.with_suffix('.sha256').write_text(sha256(CACHE.read_bytes()).hexdigest(),encoding='ascii')
    return data


class BankLibrary(Library):
    def __init__(self,data=None):
        if data is None:
            data=json.loads(CACHE.read_text(encoding='utf-8')) if CACHE.exists() else build()
            if sha256(CACHE.read_bytes()).hexdigest()!=CACHE.with_suffix('.sha256').read_text().strip():
                raise ValueError('Bank prose cache checksum failed')
            for s in specs():
                if data['documents'].get(s['id'])!=s['sha256'] or sha256((ROOT/'data/raw'/s['file']).read_bytes()).hexdigest()!=s['sha256']:
                    raise ValueError('Bank prose source changed: '+s['id'])
        super().__init__(data)

    def search(self,question,year,top_k=5,purpose=None,company='CBA'):
        if company not in ('CBA','NAB') or year not in (2024,2025):return []
        return super().search(question,year,top_k=top_k,purpose=purpose,company=company)


@lru_cache(maxsize=1)
def get_library():return BankLibrary()


if __name__=='__main__':
    data=build()
    print(json.dumps({'pages':len(data['records']),
        'blocks':sum(len(p['blocks']) for p in data['records']),
        'per_document':{s['id']:sum(p['source']['document_id']==s['id'] for p in data['records']) for s in specs()}}))
