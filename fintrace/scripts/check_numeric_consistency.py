"""Read-only numeric cross-checks, not financial or all-cell verification.

Scan every stored table cell. Check scalar numbers against native page tokens
and source glyphs at the cell coordinates. Keep mixed text, unsupported syntax
and missing coordinates visible in the coverage counts and review queue.
Neither agreement nor shared source glyphs establishes row/column semantics.
"""
import argparse
from collections import Counter
from decimal import Decimal
import hashlib
import math
import re

import pdfplumber
from pdfplumber.utils import extract_text

from extract_bank_reports import ROOT, BASE, expanded, fingerprint, read, save
from pdf_visibility import hidden_bracket

VERSION = 'numeric-consistency-v1'
SPACE = r'[ \t\u00a0]*'
NUMBER = r'(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?'
# A sign may have one intervening space, not an entire table-column gap.
SCALAR = rf'(?:(?:[+\-\u2212][ \t\u00a0]?)?{NUMBER}{SPACE}%?|\({SPACE}{NUMBER}{SPACE}%?{SPACE}\){SPACE}%?)'
FULL_NUMBER = re.compile(rf'^{SCALAR}$')
# Do not match 100 inside 1,100, (100), 100%, malformed 100), or words.
TOKEN = re.compile(rf'(?<![\w.,()+%\-\u2212]){SCALAR}(?![\w.,()%\-\u2212])')
LIMITATIONS = [
    'Agreement is consistency, not independent ground truth or semantic correctness.',
    'Both extractors can share defects in the same PDF text layer.',
    'Page presence cannot establish the correct row, year, basis or unit.',
    'Coordinate matching cannot prove that the table grid assigned the right header.',
    'Mixed text, footnoted values and unsupported numeric syntax require review.',
    'Only table cells are scanned; narrative figures and chart contents are not checked.',
]


def number_key(text):
    """Strict scalar syntax; preserve sign and percentage, never merge digits."""
    value = text.strip()
    if not FULL_NUMBER.fullmatch(value):
        return None
    percentage = '%' in value
    if value.count('%') > 1:
        return None
    negative = value.startswith('(')
    value = re.sub(r'[ \t\u00a0,%()]', '', value).replace('\u2212', '-')
    number = Decimal(value)
    if negative:
        number = -number
    return (number, percentage)


def page_numbers(text):
    return {key for m in TOKEN.finditer(text) if (key := number_key(m.group())) is not None}


def classify(text):
    if number_key(text) is not None:
        return 'numeric_scalar'
    if re.search(r'\d', text):
        return 'uncheckable_numeric_text'
    if not text.strip():
        return 'empty'
    if text.strip() in ('-', '\u2013', '\u2014'):
        return 'placeholder_not_zero'
    return 'non_numeric_text'


def cell_bbox(cell, width, height):
    box = cell.get('bbox')
    if not box:
        return None
    try:
        left, right, top, bottom = (float(box[k]) for k in ('l', 'r', 't', 'b'))
        if box.get('coord_origin') == 'BOTTOMLEFT':
            top, bottom = height - top, height - bottom
        elif box.get('coord_origin') != 'TOPLEFT':
            return None
        if not all(math.isfinite(v) for v in (left, right, top, bottom)):
            return None
        if not (0 <= left < right <= width and 0 <= top < bottom <= height):
            return None
        return (left, top, right, bottom)
    except (KeyError, TypeError, ValueError):
        return None


def source_cell_text(cell, page, settings):
    box = cell_bbox(cell, page.width, page.height)
    if box is None:
        return {'status': 'uncheckable_coordinates', 'text': None,
                'correction_confirmed': False}
    left, top, right, bottom = box
    tolerance = settings['coordinate_tolerance_points']
    chars = [c for c in page.chars
             if left-tolerance <= (c['x0']+c['x1'])/2 <= right+tolerance
             and top-tolerance <= (c['top']+c['bottom'])/2 <= bottom+tolerance]
    correction = cell.get('extraction_correction', {})
    confirmed = False
    if (correction.get('method') == 'source_confirmed_background_colour_bracket'
            and correction.get('corrected_text') == cell['text']
            and correction.get('raw_text') == cell.get('raw_text')
            and cell.get('raw_text', '').strip() == cell['text'].strip() + ')'):
        brackets = [c for c in chars if c['text'] == ')']
        if len(brackets) == 1 and hidden_bracket(brackets[0], page.rects):
            chars = [c for c in chars if c is not brackets[0]]
            confirmed = True
    text = extract_text(chars, x_tolerance=settings['text_x_tolerance_points'],
                        y_tolerance=settings['text_y_tolerance_points']) if chars else ''
    return {'status': 'available' if chars else 'no_source_glyphs', 'text': text,
            'bbox_top_left': list(box), 'correction_confirmed': confirmed}


def raw_correction_present(raw, native_text):
    # Only called after the source glyph and logged correction are confirmed.
    return bool(re.search(r'(?<![\w.,()+%\-])' + re.escape(raw.strip())
                          + r'(?![\w.,()%\-])', native_text))


def check_cell(cell, native_text, keys, page, settings):
    text = cell.get('text', '')
    category = classify(text)
    result = {'text': text, 'category': category, 'issues': []}
    if category != 'numeric_scalar':
        result.update(page_check='not_applicable', coordinate_check='not_applicable')
        if category == 'uncheckable_numeric_text':
            result['issues'].append('uncheckable_numeric_text')
        return result
    key = number_key(text)
    local = source_cell_text(cell, page, settings)
    if key in keys:
        page_status = 'matched'
    elif local['correction_confirmed'] and raw_correction_present(cell['raw_text'], native_text):
        page_status = 'matched_via_logged_correction'
    else:
        page_status = 'not_found'
        result['issues'].append('not_found_in_native_page')
    if local['status'] != 'available':
        spatial = local['status']
        result['issues'].append(spatial)
    elif number_key(local['text']) == key:
        spatial = 'matched'
    else:
        spatial = 'mismatch'
        result['issues'].append('coordinate_text_mismatch')
    result.update(page_check=page_status, coordinate_check=spatial, source_cell=local)
    return result


def audit():
    settings = read(ROOT/'config/numeric_consistency.json')
    if settings['version'] != VERSION:
        raise ValueError('Unsupported numeric consistency configuration version')
    for key in ('coordinate_tolerance_points', 'text_x_tolerance_points', 'text_y_tolerance_points'):
        if not isinstance(settings[key], (int, float)) or not 0 <= settings[key] <= 3:
            raise ValueError(f'Invalid tolerance: {key}')
    documents = read(ROOT/'config/banking_sources.json')['documents']
    scope = read(ROOT/'config/banking_extraction_scope.json')['pages']
    counters, page_checks, coordinate_checks = Counter(), Counter(), Counter()
    results, queue, errors, inputs = [], [], [], {}
    for doc in documents:
        pdf_path = fingerprint(doc)
        native_path = BASE/'native'/f"{doc['id']}.json"
        native = read(native_path)
        if native['source_sha256'] != doc['sha256']:
            raise ValueError(f'Native source identity mismatch: {doc["id"]}')
        inputs[str(native_path.relative_to(ROOT)).replace('\\', '/')] = hashlib.sha256(native_path.read_bytes()).hexdigest()
        native_pages = {p['pdf_page']: p for p in native['pages']}
        with pdfplumber.open(pdf_path) as pdf:
            for number in expanded(scope[doc['id']]):
                path = BASE/'evidence'/doc['id']/f'page_{number:03}.json'
                if not path.exists():
                    errors.append(f'Missing evidence: {doc["id"]}:{number}')
                    continue
                inputs[str(path.relative_to(ROOT)).replace('\\', '/')] = hashlib.sha256(path.read_bytes()).hexdigest()
                record = read(path)
                source = record['source']
                if (source['source_sha256'] != doc['sha256'] or source['document_id'] != doc['id']
                        or source['pdf_page'] != number or record['quality']['extraction_status'] != 'success'):
                    errors.append(f'Invalid evidence identity/status: {doc["id"]}:{number}')
                    continue
                counters['pages'] += 1
                page = pdf.pages[number-1]
                native_text = native_pages[number]['text']
                keys = page_numbers(native_text)
                for block in record['blocks']:
                    if block['type'] != 'table':
                        continue
                    counters['tables'] += 1
                    for index, cell in enumerate(block['cells']):
                        outcome = check_cell(cell, native_text, keys, page, settings)
                        outcome.update(document_id=doc['id'], pdf_page=number, table_id=block['id'],
                                       cell_index=index, row=cell['start_row_offset_idx'],
                                       column=cell['start_col_offset_idx'], bbox=cell.get('bbox'))
                        results.append(outcome)
                        counters['table_cells_scanned'] += 1
                        counters[outcome['category']] += 1
                        if outcome['category'] == 'numeric_scalar':
                            page_checks[outcome['page_check']] += 1
                            coordinate_checks[outcome['coordinate_check']] += 1
                            if not outcome['issues']:
                                counters['numeric_cells_consistent_on_both_checks'] += 1
                        if outcome['issues']:
                            counters['review_queue_cells'] += 1
                            queue.append({**outcome, 'review_status': 'pending',
                                          'reviewer': None, 'resolution': None})
                page.close()
                print(f"Numeric consistency: {doc['id']}:{number}", flush=True)
    status = 'invalid_inputs' if errors else ('completed_with_review_flags' if queue else 'completed_no_flags')
    report = {'version': VERSION, 'status': status, 'settings': settings,
              'counts': dict(counters), 'page_checks': dict(page_checks),
              'coordinate_checks': dict(coordinate_checks), 'errors': errors,
              'limitations': LIMITATIONS, 'input_sha256': inputs,
              'independent_review': 'pending', 'automatic_numeric_fact_approval': False,
              'details_path': 'data/processed/banking_v1/numeric_consistency/cells.json',
              'review_queue_path': 'data/processed/banking_v1/numeric_consistency/review_queue.json',
              'review_markdown_path': 'data/processed/banking_v1/numeric_consistency/REVIEW.md'}
    report['checker_sha256'] = {name: hashlib.sha256((ROOT/name).read_bytes().replace(b'\r\n', b'\n')).hexdigest()
                               for name in ['scripts/check_numeric_consistency.py', 'scripts/pdf_visibility.py',
                                            'scripts/extract_bank_reports.py',
                                            'config/numeric_consistency.json']}
    save(ROOT/report['details_path'], results)
    save(ROOT/report['review_queue_path'], queue)
    lines = ['# Numeric consistency review', '',
             'All decisions are pending. These are review flags, not confirmed extraction errors.', '',
             'Rows and columns below are zero-based extraction-grid positions. PDF pages are one-based.', '',
             '## Standalone numeric cells needing review', '',
             '| Document | PDF page | Table ID | Row | Column | Extracted | Source crop | Issues |',
             '| --- | ---: | --- | ---: | ---: | --- | --- | --- |']
    def escaped(value):
        return str(value).replace('|', '\\|').replace('\n', '<br>')
    for item in queue:
        if item['category'] == 'numeric_scalar':
            values = [item['document_id'], item['pdf_page'], item['table_id'], item['row'],
                      item['column'], item['text'], item.get('source_cell', {}).get('text'),
                      ', '.join(item['issues'])]
            lines.append('| ' + ' | '.join(escaped(v) for v in values) + ' |')
    lines += ['', '## Text with digits outside the scalar matcher', '',
              'These include dates, labels and footnotes. They are not automatically numeric errors.', '',
              '| Document | PDF page | Cells needing semantic review |', '| --- | ---: | ---: |']
    mixed = Counter((item['document_id'], item['pdf_page']) for item in queue
                    if item['category'] == 'uncheckable_numeric_text')
    lines += [f'| {doc} | {page} | {count} |' for (doc, page), count in sorted(mixed.items())]
    lines += ['', 'Full cell details are in review_queue.json. Record review decisions in a separate file.',
              'Do not edit this frozen output or describe it as independent ground truth.', '']
    (ROOT/report['review_markdown_path']).write_text('\n'.join(lines), encoding='utf-8')
    save(ROOT/'reports/numeric_consistency.json', report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fail-on-review', action='store_true',
                        help='Exit 2 on pending review flags; invalid inputs always exit 1.')
    args = parser.parse_args()
    report = audit()
    import json
    print(json.dumps({k: report[k] for k in ('status', 'counts', 'page_checks', 'coordinate_checks', 'errors')}, indent=2))
    return 1 if report['errors'] else (2 if args.fail_on_review and report['counts'].get('review_queue_cells') else 0)


if __name__ == '__main__':
    raise SystemExit(main())
