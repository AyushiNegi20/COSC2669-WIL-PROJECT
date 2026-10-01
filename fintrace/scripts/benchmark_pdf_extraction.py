"""Compare extractors against a source-transcribed development reference.

References are read only by the scorer, never by the extraction adapters.
All engine outputs are retained, including failures. Run one engine per process
to make elapsed times understandable; downloads are not steady-state timings.
"""
import argparse
import hashlib
import importlib.metadata
import json
import logging
import os
import re
import time
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data/processed/extraction_benchmark'


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def compact(value):
    return re.sub(r'\s+', '', unicodedata.normalize('NFKC', value or '')).casefold()


def label_key(value):
    value = re.sub(r'[\u00b9\u00b2\u00b3\u2070-\u2079]', '', value or '')
    value = re.sub(r'\([^)]*\)', '', value)
    return re.sub(r'[^a-z0-9]', '', value.lower())


def numeric(value):
    s = compact(value)
    return bool(re.fullmatch(r'\(?[+\-\u2212]?\d[\d,]*(?:\.\d+)?\)?%?', s))


def row_matches(row, label):
    cells = [str(c or '').strip() for c in row]
    first = next((i for i, c in enumerate(cells) if numeric(c)), None)
    if first is None:
        return None
    key = label_key(' '.join(cells[:first]))
    expected = label_key(label)
    # Do not mistake Cash earnings before tax for Cash earnings, or
    # Underlying operating performance for Operating performance.
    if key != expected and key != expected + 'fullyfranked':
        return None
    return [compact(c) for c in cells[first:] if c.strip()]


def score(result, reference):
    details = []
    for label, expected in reference['rows']:
        matches = [values for t in result['tables'] for row in t['rows']
                   if (values := row_matches(row, label)) is not None]
        actual = matches[0] if matches else []
        bound = actual[:len(expected)] == [compact(x) for x in expected]
        details.append({'label': label, 'expected': expected, 'actual': actual[:len(expected)],
                        'row_values_correct': bound,
                        'values_present_in_page': all(compact(x) in compact(result['text']) for x in expected)})
    anchors = [{'text': a, 'present': compact(a) in compact(result['text'])}
               for a in reference['anchors']]
    return {'rows': details, 'anchors': anchors}


def extract_light(engine, path, number, handles):
    import pypdf
    import pdfplumber
    import pymupdf
    if engine == 'pypdf_layout':
        reader = handles.setdefault(str(path), pypdf.PdfReader(path))
        return {'text': reader.pages[number - 1].extract_text(extraction_mode='layout') or '', 'tables': []}
    if engine.startswith('pdfplumber'):
        if str(path) not in handles:
            handles[str(path)] = pdfplumber.open(path)
        page = handles[str(path)].pages[number - 1]
        settings = {} if engine.endswith('lines') else {
            'vertical_strategy': 'text', 'horizontal_strategy': 'text'}
        tables = [{'bbox': list(t.bbox), 'rows': t.extract()} for t in page.find_tables(settings)]
        return {'text': page.extract_text(layout=True) or '', 'tables': tables}
    if str(path) not in handles:
        handles[str(path)] = pymupdf.open(path)
    page = handles[str(path)][number - 1]
    strategy = 'lines' if engine.endswith('lines') else 'text'
    tables = [{'bbox': list(t.bbox), 'rows': t.extract()} for t in page.find_tables(strategy=strategy).tables]
    return {'text': page.get_text('text', sort=True), 'tables': tables}


def make_docling():
    os.environ.setdefault('HF_HOME', str(ROOT / 'models/huggingface'))
    os.environ.setdefault('HF_HUB_DISABLE_SYMLINKS_WARNING', '1')
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions, TableFormerMode
    from docling.datamodel.accelerator_options import AcceleratorDevice, AcceleratorOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption
    options = PdfPipelineOptions()
    options.do_ocr = False
    options.do_table_structure = True
    options.table_structure_options.mode = TableFormerMode.ACCURATE
    options.accelerator_options = AcceleratorOptions(num_threads=4, device=AcceleratorDevice.CPU)
    return DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)})


def extract_docling(converter, path, number):
    result = converter.convert(path, page_range=(number, number), raises_on_error=True)
    doc = result.document
    tables = []
    for table in doc.tables:
        rows = [['' for _ in range(table.data.num_cols)] for _ in range(table.data.num_rows)]
        for cell in table.data.table_cells:
            rows[cell.start_row_offset_idx][cell.start_col_offset_idx] = cell.text
        tables.append({'rows': rows, 'provenance': [p.model_dump(mode='json') for p in table.prov]})
    return {'text': doc.export_to_markdown(), 'tables': tables,
            'document': doc.model_dump(mode='json'), 'conversion_status': str(result.status)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--engine', choices=['pypdf_layout','pdfplumber_lines','pdfplumber_text',
                        'pymupdf_lines','pymupdf_text','docling'])
    parser.add_argument('--limit', type=int)
    parser.add_argument('--summarise', action='store_true')
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=OUT / 'warnings.log', level=logging.WARNING)
    references = read_json(ROOT / 'eval/extraction/reference.json')['pages']
    docs = {d['id']: d for d in read_json(ROOT / 'config/banking_sources.json')['documents']}
    if args.summarise:
        summaries = []
        for engine_dir in sorted(OUT.iterdir()):
            if not engine_dir.is_dir():
                continue
            outputs = [read_json(p) for p in engine_dir.glob('*.json')]
            refs = {(r['doc'],r['page']): r for r in references}
            scores = [score(o, refs[(o['document_id'],o['pdf_page'])]) for o in outputs if 'score' in o]
            rows = [r for s in scores for r in s['rows']]
            anchors = [a for s in scores for a in s['anchors']]
            summaries.append({'engine': engine_dir.name, 'pages': len(outputs),
                'errors': sum('error' in o for o in outputs), 'reference_rows': len(rows),
                'bound_rows_correct': None if engine_dir.name=='pypdf_layout' else sum(r['row_values_correct'] for r in rows),
                'value_presence_rows': sum(r['values_present_in_page'] for r in rows),
                'anchors_correct': sum(a['present'] for a in anchors), 'anchors_total': len(anchors),
                'seconds': round(sum(o['seconds'] for o in outputs), 2)})
        write_json(ROOT / 'reports/extraction_benchmark.json', {'reference_sha256':hashlib.sha256((ROOT / 'eval/extraction/reference.json').read_bytes()).hexdigest(),
            'limitations':'Development sample, not held-out. Row score checks local binding, not full table semantics. pypdf has no table adapter; its row score is not applicable. Timings include cold conversion/model setup where applicable.', 'results':summaries})
        print(json.dumps(summaries, indent=2))
        return
    if not args.engine:
        parser.error('--engine or --summarise is required')
    converter = None
    handles = {}
    for ref in references[:args.limit]:
        doc = docs[ref['doc']]
        path = ROOT / 'data/raw' / doc['file']
        if hashlib.sha256(path.read_bytes()).hexdigest() != doc['sha256']:
            raise ValueError(f'Hash mismatch: {path}')
        target = OUT / args.engine / f"{doc['id']}_p{ref['page']:03}.json"
        started = time.perf_counter()
        output = {'engine': args.engine, 'document_id': doc['id'], 'pdf_page': ref['page'],
                  'source_sha256':doc['sha256']}
        try:
            if args.engine == 'docling':
                converter = converter or make_docling()
                output.update(extract_docling(converter, path, ref['page']))
            else:
                output.update(extract_light(args.engine, path, ref['page'], handles))
            output['score'] = score(output, ref)
        except Exception as exc:
            output['error'] = f'{type(exc).__name__}: {exc}'
        output['seconds'] = round(time.perf_counter() - started, 4)
        output['versions'] = {p: importlib.metadata.version(p) for p in ['pypdf','pdfplumber','pymupdf']}
        if args.engine == 'docling':
            output['versions']['docling'] = importlib.metadata.version('docling')
        write_json(target, output)
        print(f"{args.engine} {doc['id']}:{ref['page']} {output['seconds']}s "
              + (output.get('error') or f"{sum(r['row_values_correct'] for r in output['score']['rows'])}/{len(ref['rows'])} rows"), flush=True)
    for handle in handles.values():
        if hasattr(handle, 'close'):
            handle.close()


if __name__ == '__main__':
    main()
