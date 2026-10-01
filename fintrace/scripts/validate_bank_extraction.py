"""Validate source identity, structural invariants and explicit acceptance samples.

Checks read expected answers only after extraction. They do not patch outputs.
This is not whole-corpus accuracy, financial assurance or RAG evaluation.
"""
import argparse
import hashlib
import importlib.metadata
import json
import platform
import re
import sys
from pathlib import Path

from benchmark_pdf_extraction import score, compact
from extract_bank_reports import BASE, ROOT, expanded, read, save


def main():
    docs=read(ROOT/'config/banking_sources.json')['documents']
    scope=read(ROOT/'config/banking_extraction_scope.json')['pages']
    records={}
    errors=[]
    unresolved=[]
    correction_count=0
    for doc in docs:
        source=ROOT/'data/raw'/doc['file']
        if hashlib.sha256(source.read_bytes()).hexdigest()!=doc['sha256']:
            errors.append(f"Source hash mismatch: {doc['id']}")
        native=read(BASE/'native'/f"{doc['id']}.json")
        if native['source_sha256']!=doc['sha256']:
            errors.append(f"Native cache hash mismatch: {doc['id']}")
        for page in expanded(scope[doc['id']]):
            path=BASE/'evidence'/doc['id']/f'page_{page:03}.json'
            if not path.exists():
                errors.append(f'Missing evidence: {doc["id"]}:{page}')
                continue
            record=read(path)
            records[(doc['id'],page)]=record
            s=record['source']
            if any(s[k]!=v for k,v in [('document_id',doc['id']),('company',doc['company']),('source_sha256',doc['sha256']),('pdf_page',page)]):
                errors.append(f'Source identity mismatch: {path}')
            if record['quality']['extraction_status']!='success':
                errors.append(f'Extraction unsuccessful: {path}')
            if not s.get('printed_page',{}).get('value'):
                unresolved.append({'doc':doc['id'],'page':page,'issue':'printed_page_label_unresolved'})
            correction_count+=len(record.get('corrections',[]))
            if record.get('unresolved_numeric_artifacts'):
                errors.append(f'Unresolved numeric artifacts: {path}')
            for b in record['blocks']:
                if b['page_context_id']!=record['id']:
                    errors.append(f'Wrong context: {b["id"]}')
                if not b['provenance'] or any(p['page_no']!=page for p in b['provenance']):
                    errors.append(f'Missing/wrong page provenance: {b["id"]}')
                if b['type']=='table':
                    if not b['rows'] or len({len(r) for r in b['rows']})!=1:
                        errors.append(f'Nonrectangular/empty table: {b["id"]}')
                    for c in b['cells']:
                        r,col=c['start_row_offset_idx'],c['start_col_offset_idx']
                        if b['rows'][r][col]!=c['text']:
                            errors.append(f'Grid/cell disagreement: {b["id"]}')
    baseline=[]
    for ref in read(ROOT/'eval/extraction/reference.json')['pages']:
        r=records.get((ref['doc'],ref['page']))
        if r is None:
            errors.append(f'Acceptance sample excluded: {ref["doc"]}:{ref["page"]}')
            continue
        result={'text':r['markdown'],'tables':[b for b in r['blocks'] if b['type']=='table']}
        baseline.append({'doc':ref['doc'],'page':ref['page'],**score(result,ref)})
    additional=[]
    for c in read(ROOT/'eval/extraction/additional_checks.json')['cases']:
        r=records[(c['doc'],c['page'])]
        matches=[row for b in r['blocks'] if b['type']=='table' for row in b['rows']
                 if re.search(c['label'],re.sub(r'\s+',' ',row[0]),re.I)]
        actual=[matches[0][i] for i in c['columns']] if matches else []
        passed=([compact(v) for v in actual]==[compact(v) for v in c['values']]
                and all(compact(t) in compact(r['markdown']) for t in c['context']))
        additional.append({**c,'actual':actual,'passed':passed})
    failed_rows=[{'doc':r['doc'],'page':r['page'],**row} for r in baseline for row in r['rows'] if not row['row_values_correct']]
    failed_anchors=[{'doc':r['doc'],'page':r['page'],**a} for r in baseline for a in r['anchors'] if not a['present']]
    failed_extra=[c for c in additional if not c['passed']]
    if failed_rows or failed_anchors or failed_extra:
        errors.append('Acceptance reference failures; see details')
    summary=read(BASE/'summary.json')
    result={'status':'passed_automated_acceptance' if not errors else 'failed',
        'limitations':['References are AI-assisted and not independently reviewed.',
            'Local row/value and page-context checks are not complete semantic or all-cell verification.',
            'Charts are not transcribed. No retrieval or answer-generation evaluation has run.',
            'Existing eval/v1 is historical CBA/BHP and must not be used as a CBA/NAB answer bank.'],
        'documents':len(docs),'native_pages':sum(s['native_pages'] for s in summary.values()),
        'selected_pages':len(records),'structured_tables':sum(s['tables'] for s in summary.values()),
        'text_blocks':sum(s['text_blocks'] for s in summary.values()),
        'untranscribed_figures':sum(s['figures'] for s in summary.values()),
        'benchmark_rows':sum(len(r['rows']) for r in baseline),'benchmark_rows_failed':len(failed_rows),
        'context_anchors':sum(len(r['anchors']) for r in baseline),'context_anchors_failed':len(failed_anchors),
        'additional_checks':len(additional),'additional_checks_failed':len(failed_extra),
        'source_confirmed_bracket_corrections':correction_count,'errors':errors,'review_queue':unresolved,
        'failed_rows':failed_rows,'failed_anchors':failed_anchors,'additional_results':additional,
        'environment':{'python':platform.python_version(),**{p:importlib.metadata.version(p) for p in ['pypdf','pdfplumber','pymupdf','docling','docling-core','docling-ibm-models','docling-parse','torch']}}}
    save(ROOT/'reports/banking_extraction_acceptance.json',result)
    snapshots=[]
    for snapshot in sorted((ROOT/'models/huggingface/hub').glob('*/snapshots/*')):
        snapshots.append({'model':snapshot.parent.parent.name,'revision':snapshot.name,
                          'files':[{'path':str(p.relative_to(snapshot)).replace('\\','/'),
                                    'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),
                                    'bytes':p.stat().st_size} for p in sorted(snapshot.rglob('*')) if p.is_file()]})
    save(ROOT/'reports/extraction_environment.json',{'versions':result['environment'],
          'pipeline':'Docling standard PDF, TableFormer ACCURATE, OCR disabled, CPU, four threads',
          'models':snapshots,'configuration_sha256':{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
              for name in ['config/banking_sources.json','config/banking_extraction_scope.json',
                           'eval/extraction/reference.json','eval/extraction/additional_checks.json']}})
    print(json.dumps({k:v for k,v in result.items() if k not in ['additional_results','environment']},indent=2))
    return 1 if errors else 0


if __name__=='__main__':
    sys.exit(main())
