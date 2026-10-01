"""Offline, resumable bank PDF extraction. No evaluation answers are read.

Native page text is the audit layer. Docling provides structural candidates on
the explicitly selected pages. Neither conversion success nor a passed sample
is permission to describe every extracted table as independently verified.
"""
import argparse
import hashlib
import importlib.metadata
import json
import logging
import os
import re
import time
from pathlib import Path

import pypdf
import pdfplumber
from pdf_visibility import correct_tables

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'data/processed/banking_v1'
PIPELINE_VERSION = '1.0'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')
    temporary.replace(path)


def expanded(ranges):
    return sorted({p for start,end in ranges for p in range(start,end+1)})


def fingerprint(doc):
    path = ROOT/'data/raw'/doc['file']
    if not path.read_bytes().startswith(b'%PDF-'):
        raise ValueError(f"Not a PDF: {doc['id']}")
    if hashlib.sha256(path.read_bytes()).hexdigest() != doc['sha256']:
        raise ValueError(f"Source changed: {doc['id']}; review and explicitly update the manifest")
    return path


def native_extract(doc):
    path = fingerprint(doc)
    target = BASE/'native'/f"{doc['id']}.json"
    if target.exists():
        existing = read(target)
        if existing['source_sha256'] == doc['sha256'] and existing['pypdf_version'] == pypdf.__version__:
            return existing
    reader = pypdf.PdfReader(path)
    pages = []
    for number, page in enumerate(reader.pages, 1):
        text = page.extract_text(extraction_mode='layout') or ''
        pages.append({'pdf_page':number,'text':text,'width':float(page.mediabox.width),
                      'height':float(page.mediabox.height),
                      'flags':(['sparse_native_text'] if len(text.strip())<80 else [])
                              + (['replacement_character'] if '\ufffd' in text else [])})
    result = {'source_sha256':doc['sha256'],'pypdf_version':pypdf.__version__,'pages':pages}
    save(target,result)
    print(f"Native: {doc['id']} {len(pages)} pages", flush=True)
    return result


def converter():
    os.environ.setdefault('HF_HOME',str(ROOT/'models/huggingface'))
    os.environ.setdefault('HF_HUB_DISABLE_SYMLINKS_WARNING','1')
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions, TableFormerMode
    from docling.datamodel.accelerator_options import AcceleratorDevice, AcceleratorOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption
    options = PdfPipelineOptions()
    options.do_ocr = False
    options.do_table_structure = True
    options.table_structure_options.mode = TableFormerMode.ACCURATE
    options.accelerator_options = AcceleratorOptions(num_threads=4, device=AcceleratorDevice.CPU)
    options.document_timeout = 180
    return DocumentConverter(format_options={InputFormat.PDF:PdfFormatOption(pipeline_options=options)})


def structure(doc, pages, use_cache=True):
    path = fingerprint(doc)
    instance = None
    for number in pages:
        target = BASE/'structured'/doc['id']/f'page_{number:03}.json'
        if target.exists():
            old = read(target)
            if (old.get('source_sha256')==doc['sha256'] and old.get('pipeline_version')==PIPELINE_VERSION
                    and old.get('docling_version')==importlib.metadata.version('docling')
                    and old.get('status')=='success'):
                continue
        start = time.perf_counter()
        record = {'document_id':doc['id'],'pdf_page':number,'source_sha256':doc['sha256'],
                  'pipeline_version':PIPELINE_VERSION,'docling_version':importlib.metadata.version('docling'),
                  'settings':{'ocr':False,'table_mode':'ACCURATE','device':'cpu','threads':4}}
        try:
            cache = ROOT/'data/processed/extraction_benchmark/docling'/f"{doc['id']}_p{number:03}.json"
            cached = read(cache) if use_cache and cache.exists() else {}
            if ('document' in cached and cached.get('versions',{}).get('docling')==record['docling_version']
                    and cached.get('source_sha256')==doc['sha256']
                    and cached.get('document_id')==doc['id'] and cached.get('pdf_page')==number):
                # Reuse only conversion output, never scores or reference values.
                record.update({'document':cached['document'],'markdown':cached['text'],
                               'conversion_status':cached['conversion_status'],
                               'reused_conversion':True})
            else:
                instance = instance or converter()
                result = instance.convert(path,page_range=(number,number),raises_on_error=True)
                record.update({'document':result.document.model_dump(mode='json'),
                               'markdown':result.document.export_to_markdown(),
                               'conversion_status':str(result.status),'reused_conversion':False})
            if record['conversion_status'].split('.')[-1].lower() != 'success':
                raise ValueError(f"Incomplete conversion: {record['conversion_status']}")
            record['status']='success'
        except Exception as exc:
            record.update({'status':'failed','error':f'{type(exc).__name__}: {exc}'})
        record['seconds']=round(time.perf_counter()-start,3)
        save(target,record)
        print(f"Structured: {doc['id']}:{number} {record['status']} {record['seconds']}s",flush=True)


def grid(table):
    data = table['data']
    rows = [['' for _ in range(data['num_cols'])] for _ in range(data['num_rows'])]
    for cell in data['table_cells']:
        rows[cell['start_row_offset_idx']][cell['start_col_offset_idx']] = cell['text']
    return rows


def blocks_markdown(blocks):
    parts=[]
    for block in blocks:
        if block['type']=='table':
            rows=block['rows']
            for i,row in enumerate(rows):
                parts.append('| '+' | '.join(c.replace('|','\\|').replace('\n','<br>') for c in row)+' |')
                if i==0:
                    parts.append('| '+' | '.join('---' for _ in row)+' |')
            parts.append('')
        elif block['type']=='picture':
            parts.append('[Figure retained in original PDF; chart content not transcribed.]')
        else:
            parts.append(('## ' if block['type']=='section_header' else '')+block.get('text',''))
            parts.append('')
    return '\n'.join(parts)


def ordered_items(document):
    pools = {f"#/{name}/{i}":item for name in ['texts','tables','pictures','groups']
             for i,item in enumerate(document.get(name,[]))}
    def walk(node):
        for pointer in node.get('children',[]):
            item = pools.get(pointer['cref'])
            if item is None:
                continue
            if pointer['cref'].startswith('#/groups/'):
                yield from walk(item)
            else:
                yield item
                yield from walk(item)
    return list(walk(document['body']))


def printed_label(document, native_page):
    candidates = set()
    for item in document.get('texts',[]):
        if item['label']=='page_footer':
            text = item['text'].strip()
            if re.fullmatch(r'\d{1,3}',text):
                candidates.add(text)
            else:
                start = re.match(r'^(\d{1,3})\s', text)
                end = re.search(r'\s(\d{1,3})$', text)
                if start:
                    candidates.add(start[1])
                if end:
                    candidates.add(end[1])
    if len(candidates)==1:
        return {'value':next(iter(candidates)),'method':'docling_footer_candidate','reviewed':False}
    # Do not manufacture a constant PDF-to-printed offset across a report.
    return {'value':None,'method':'not_resolved','reviewed':False}


def assemble(doc, pages):
    native = native_extract(doc)
    native_pages = {p['pdf_page']:p for p in native['pages']}
    records = []
    counts = {'selected_pages':len(pages),'converted_pages':0,'failed_pages':0,'tables':0,'text_blocks':0,'figures':0}
    plumber=pdfplumber.open(fingerprint(doc))
    for number in pages:
        page_id=f"{doc['id']}:p{number:03}"
        source = {'document_id':doc['id'],'company':doc['company'],'report_year':doc['report_year'],
                  'report_period_end':doc['period_end'],'document_title':doc['title'],'source_url':doc['url'],
                  'source_sha256':doc['sha256'],'pdf_page':number}
        path = BASE/'structured'/doc['id']/f'page_{number:03}.json'
        converted = read(path) if path.exists() else {'status':'missing'}
        record = {'id':page_id,'source':source,'native_text':native_pages[number]['text'],
                  'raw_extraction_path':f"structured/{doc['id']}/page_{number:03}.json",
                  'blocks':[],'quality':{'extraction_status':converted['status'],
                    'independent_review':'pending','semantic_metric_mapping':'not_performed',
                    'eligible_for_automatic_numeric_facts':False,'flags':native_pages[number]['flags'].copy()}}
        if converted['status']!='success':
            counts['failed_pages']+=1
            record['quality']['flags'].append('structured_extraction_failed')
            record['quality']['error']=converted.get('error','missing conversion')
        else:
            counts['converted_pages']+=1
            document,corrections,unresolved=correct_tables(converted['document'],plumber.pages[number-1])
            record['corrections']=corrections
            record['unresolved_numeric_artifacts']=unresolved
            if unresolved:
                record['quality']['flags'].append('unresolved_numeric_artifacts')
            source['printed_page']=printed_label(document,native_pages[number])
            record['raw_markdown']=converted['markdown']
            items=ordered_items(document)
            for index,item in enumerate(items):
                kind=item.get('label','unknown')
                if kind in ('page_header','page_footer') or item.get('content_layer')=='furniture':
                    continue
                block={'id':f'{page_id}:b{index:03}','type':kind,
                       'provenance':item.get('prov',[]),'origin_ref':item.get('self_ref'),
                       'page_context_id':page_id}
                if kind=='table':
                    counts['tables']+=1
                    block.update({'rows':grid(item),'cells':item['data']['table_cells'],
                                  'caption_refs':item.get('captions',[]),
                                  'footnote_refs':item.get('footnotes',[]),
                                  'quality_flags':['table_semantics_need_review'],
                                  'context_policy':'Keep page headings and footnotes with this table. Do not index rows without their column and section context.'})
                elif kind=='picture':
                    counts['figures']+=1
                    block.update({'quality_flags':['figure_not_transcribed'],'caption_refs':item.get('captions',[])})
                else:
                    counts['text_blocks']+=1
                    block['text']=item.get('text','')
                record['blocks'].append(block)
            if any(b['type']=='picture' for b in record['blocks']):
                record['quality']['flags'].append('figure_content_not_extracted')
            record['neighbour_pdf_pages']=[p for p in [number-1,number+1] if 1<=p<=len(native_pages)]
            record['markdown']=blocks_markdown(record['blocks'])
        records.append(record)
    plumber.close()
    directory=BASE/'evidence'/doc['id']
    directory.mkdir(parents=True,exist_ok=True)
    for record in records:
        save(directory/f"page_{record['source']['pdf_page']:03}.json",record)
    markdown='\n\n'.join(f"# {doc['title']} | PDF page {r['source']['pdf_page']}\n\n"
                          +r.get('markdown',r['native_text']) for r in records)
    (directory/'review.md').write_text(markdown,encoding='utf-8')
    counts['native_pages']=len(native_pages)
    counts['native_sparse_pages']=[p['pdf_page'] for p in native['pages'] if 'sparse_native_text' in p['flags']]
    counts['source_sha256']=doc['sha256']
    counts['source_confirmed_bracket_corrections']=sum(len(r.get('corrections',[])) for r in records)
    counts['unresolved_numeric_artifacts']=sum(len(r.get('unresolved_numeric_artifacts',[])) for r in records)
    return counts


def main():
    global BASE
    parser=argparse.ArgumentParser()
    parser.add_argument('--stage',choices=['native','structured','assemble','all'],default='all')
    parser.add_argument('--doc',nargs='+')
    parser.add_argument('--offline',action='store_true')
    parser.add_argument('--no-benchmark-cache',action='store_true')
    parser.add_argument('--scope',type=Path,default=ROOT/'config/banking_extraction_scope.json',
                        help='Separate page-selection file for an independently prepared holdout.')
    parser.add_argument('--output-base',type=Path,
                        help='Separate generated-output directory. Required for a non-default scope.')
    args=parser.parse_args()
    default_scope=(ROOT/'config/banking_extraction_scope.json').resolve()
    if args.scope.resolve()!=default_scope and not args.output_base:
        parser.error('A separate scope requires --output-base to protect the development corpus')
    if args.output_base:
        proposed=args.output_base.resolve()
        if args.scope.resolve()!=default_scope and proposed==BASE.resolve():
            parser.error('Holdout output must not replace the development corpus')
        BASE=proposed
    if args.offline:
        os.environ['HF_HUB_OFFLINE']='1'
    BASE.mkdir(parents=True,exist_ok=True)
    logging.basicConfig(filename=BASE/'extraction.log',level=logging.WARNING)
    docs=read(ROOT/'config/banking_sources.json')['documents']
    scope=read(args.scope)['pages']
    if args.doc:
        unknown=set(args.doc)-{d['id'] for d in docs}
        if unknown:
            parser.error(f'Unknown document IDs: {unknown}')
    summary={}
    for doc in docs:
        if args.doc and doc['id'] not in args.doc:
            continue
        pages=expanded(scope[doc['id']])
        count=len(pypdf.PdfReader(fingerprint(doc)).pages)
        if not pages or min(pages)<1 or max(pages)>count:
            raise ValueError(f"Invalid page selection for {doc['id']}")
        if args.stage in ['native','all']:
            native_extract(doc)
        if args.stage in ['structured','all']:
            structure(doc,pages,not args.no_benchmark_cache)
        if args.stage in ['assemble','all']:
            summary[doc['id']]=assemble(doc,pages)
    if summary:
        target=BASE/'summary.json'
        old=read(target) if target.exists() else {}
        old.update(summary)
        save(target,old)
        print(json.dumps(summary,indent=2),flush=True)


if __name__=='__main__':
    main()
