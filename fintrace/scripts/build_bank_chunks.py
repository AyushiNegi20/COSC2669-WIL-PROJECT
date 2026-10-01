"""Deterministic banking chunks from frozen cleaned evidence, never answer keys.

Only standard-library dependencies. Generated files live outside extraction.
Source text stays literal. Local row context is not semantic metric mapping.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'data/processed/banking_chunks_v1'
CONFIG = 'config/banking_chunking.json'


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def write_lines(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(''.join(canonical(r) + '\n' for r in records), encoding='utf-8')


def size(text):
    return len(text.encode('utf-8'))


def header_rows(table):
    """Only leading header rows. Docling sometimes tags a glossary entry as header."""
    if glossary(table):
        return [0] if table['rows'][0][0].lower() == 'term' else []
    marked = {c['start_row_offset_idx'] for c in table['cells'] if c.get('column_header')}
    result = []
    for i in range(len(table['rows'])):
        if i not in marked:
            break
        result.append(i)
    return result


def glossary(table):
    rows = table['rows']
    return bool(rows and all(len(r) == 2 for r in rows)
                and sum(len(r[1]) > 80 for r in rows) >= len(rows) / 2)


def columns(table, heads):
    """Expand explicit merged-cell spans, never forward-fill arbitrary blanks."""
    paths = [[] for _ in table['rows'][0]]
    for r in heads:
        for c, raw in enumerate(table['rows'][r]):
            if raw:
                paths[c].append(raw)
        for cell in table['cells']:
            if cell['start_row_offset_idx'] != r or cell['col_span'] <= 1:
                continue
            start, end = cell['start_col_offset_idx'], cell['end_col_offset_idx']
            # Cleaned grid is the authority, not potentially uncorrected cell text.
            raw = table['rows'][r][start]
            for c in range(start + 1, end):
                if not table['rows'][r][c] and raw:
                    paths[c].append(raw)
    return paths


def row_contexts(table, heads):
    """Keep a broad scope plus nearest subheading, without inventing a basis."""
    contexts, broad, local = {}, None, None
    left = {c['start_row_offset_idx']: c['bbox']['l'] for c in table['cells']
            if c['start_col_offset_idx'] == 0 and c.get('bbox')}
    indented_local = False
    section_rows = set()
    for i, row in enumerate(table['rows']):
        if i in heads:
            continue
        if row[0] and not any(row[1:]):
            section_rows.add(i)
            if re.search(r'^(Group Performance|Shareholder Returns|Capital |Funding and|Credit Quality|Group -|Cash flows from|Interest earning assets$|Interest bearing liabilities$|Assets$|Liabilities$|Equity$|Shareholders)', row[0], re.I):
                broad, local = i, None
            else:
                local = i
                next_left = left.get(i + 1)
                subcategory = row[0].endswith(':') or bool(re.match(
                    r'^(Earnings Per Share|Return on equity|Dividend payout ratio)', row[0], re.I))
                indented_local = (subcategory and next_left is not None and i in left
                                  and next_left > left[i] + 3)
        elif local is not None and indented_local and i in left and left[i] <= left[local] + 3:
            # An unindented total/new item must not inherit an indented subcategory.
            local = None
            indented_local = False
        contexts[i] = list(dict.fromkeys(v for v in (broad, local) if v is not None))
    return contexts, section_rows


def prefix(source, heading_texts):
    printed = source['printed_page']['value']
    return (f"{source['document_title']} | report year {source['report_year']} | "
            f"report period end {source['report_period_end']} | PDF page {source['pdf_page']}"
            + (f" | printed page {printed} (unreviewed label)" if printed else '')
            + ('\nNearby source headings: ' + ' / '.join(heading_texts) if heading_texts else ''))


def split_spans(text, budget):
    """Exact, contiguous source slices; prefer sentence/word boundaries."""
    if budget < 32:
        raise ValueError('No space for source text after context prefix')
    start = 0
    while start < len(text):
        end = start
        used = 0
        while end < len(text) and used + size(text[end]) <= budget:
            used += size(text[end])
            end += 1
        if end < len(text):
            fragment = text[start:end]
            cuts = [m.end() for m in re.finditer(r'[.!?]\s+|\n\s*\n', fragment)]
            if not cuts:
                cuts = [m.end() for m in re.finditer(r'\s+', fragment)]
            if cuts and cuts[-1] > len(fragment) // 2:
                end = start + cuts[-1]
        yield start, end
        start = end


def chunk(source, kind, text, anchors, evidence_ids, config, issues=()):
    record = {
        'schema_version': config['schema_version'], 'chunking_version': config['version'],
        'kind': kind, 'source': source, 'text': text, 'evidence_ids': list(dict.fromkeys(evidence_ids)),
        'anchors': anchors, 'parent_id': None, 'related_chunk_ids': [],
        'relationships': [], 'utf8_bytes': size(text),
        'quality': {'status': 'development_unreviewed', 'issues': sorted(set(issues)),
                    'independent_review': 'pending', 'calculation_ready': False,
                    'embedding_token_check': 'pending_model_selection'},
    }
    record['chunk_id'] = config['version'] + ':' + hashlib.sha256(canonical(record).encode()).hexdigest()[:24]
    return record


def render_table(table, selected, heads, context, paths):
    lines = []
    for i in heads:
        lines.append(f"Header row {i}: " + ' | '.join(table['rows'][i]))
    for i in context:
        lines.append(f"Source section row {i}: " + ' | '.join(table['rows'][i]))
    for i in selected:
        row = table['rows'][i]
        if glossary(table):
            lines.append(f"Row {i}: {row[0]} | {row[1]}")
        else:
            parts = [f"Row {i}: {row[0]}"]
            for c in range(1, len(row)):
                label = ' / '.join(paths[c]) or f'unnamed column {c}'
                # Explicit column position remains even when headers repeat.
                parts.append(f"column {c} [{label}] = {row[c]}")
            lines.append(' | '.join(parts))
    return '\n'.join(lines)


def table_chunks(page, table, headings, config, guard):
    source = page['source']
    base = prefix(source, [b['text'] for b in headings])
    heads = header_rows(table)
    paths = columns(table, heads)
    contexts, sections = row_contexts(table, heads)
    is_glossary = glossary(table)
    base_issues = list(page['quality'].get('flags', [])) + table.get('quality_flags', [])
    if table['id'] in config['quarantined_tables']:
        base_issues.append('quarantined_source_table')
    if not heads and not is_glossary:
        base_issues.append('missing_column_headers')
    rows = [i for i in range(len(table['rows'])) if i not in heads and i not in sections]
    groups, current = [], []
    for i in rows:
        candidate = current + [i]
        ctx = contexts.get(i, [])
        text = base + '\n' + render_table(table, candidate, heads, ctx, paths)
        if current and (is_glossary or contexts[current[0]] != ctx
                        or len(candidate) > config['max_rows_per_child']
                        or size(text) > config['child_max_utf8_bytes']):
            groups.append(current)
            current = []
        current.append(i)
    if current:
        groups.append(current)
    children = []
    for selected in groups:
        ctx = contexts[selected[0]]
        included_rows = sorted(set(heads + ctx + selected))
        cell_issues = [g for g in guard if g['table_id'] == table['id'] and g['row'] in included_rows and g['issues']]
        issues = list(base_issues)
        if any(g['category'] == 'numeric_scalar' for g in cell_issues):
            issues.append('numeric_consistency_requires_review')
        if any(g['category'] == 'uncheckable_numeric_text' for g in cell_issues):
            issues.append('mixed_numeric_text_not_automatically_checked')
        text = base + '\n' + render_table(table, selected, heads, ctx, paths)
        anchors = [{'evidence_id': table['id'], 'type': 'table_rows', 'rows': selected,
                    'header_rows': heads, 'context_rows': ctx, 'column_paths': paths}]
        rec = chunk(source, 'definition' if is_glossary else 'table_rows', text, anchors,
                    [b['id'] for b in headings] + [table['id']], config, issues)
        rec['numeric_review_cells'] = [{k: g[k] for k in ('row', 'column', 'category', 'issues')} for g in cell_issues]
        if size(text) > config['child_max_utf8_bytes']:
            rec['quality']['issues'].append('oversize_unsplit_row')
        if any(x in rec['quality']['issues'] for x in ('quarantined_source_table', 'missing_column_headers',
                'numeric_consistency_requires_review', 'oversize_unsplit_row')):
            rec['quality']['status'] = 'quarantined'
        children.append(rec)
    # Parent stays literal and compact, not repeated cell triplets.
    text = base + '\n' + '\n'.join(f"Row {i}: " + ' | '.join(r) for i, r in enumerate(table['rows']))
    parent = chunk(source, 'table_parent', text,
                   [{'evidence_id': table['id'], 'type': 'table_rows', 'rows': list(range(len(table['rows']))),
                     'header_rows': heads, 'context_rows': [], 'column_paths': paths}],
                   [b['id'] for b in headings] + [table['id']], config, base_issues)
    # A parent may not reintroduce a quarantined row via a different child.
    if any(c['quality']['status'] == 'quarantined' for c in children):
        parent['quality']['status'] = 'quarantined'
        parent['quality']['issues'].append('contains_quarantined_child')
    if size(text) > config['parent_max_utf8_bytes']:
        parent['quality']['status'] = 'quarantined'
        parent['quality']['issues'].append('oversize_parent')
    for child in children:
        child['parent_id'] = parent['chunk_id']
    return children, parent


def build(pages, config, guard):
    children, parents, exclusions = [], [], []
    for page in pages:
        headings, block_children, table_records = [], {}, []
        for i, block in enumerate(page['blocks']):
            if block['type'] == 'section_header':
                headings.append(block)
                headings = headings[-2:]
            if block['type'] == 'table':
                cs, parent = table_chunks(page, block, headings, config, guard)
                children.extend(cs)
                parents.append(parent)
                table_records.append((i, block, cs, parent))
                block_children[block['id']] = cs
            elif block.get('text'):
                base = prefix(page['source'], [h['text'] for h in headings if h['id'] != block['id']])
                ids = [h['id'] for h in headings if h['id'] != block['id']] + [block['id']]
                full = chunk(page['source'], 'passage_parent', base + '\n' + block['text'],
                             [{'evidence_id': block['id'], 'type': 'text_span', 'start': 0, 'end': len(block['text'])}],
                             ids, config, page['quality'].get('flags', []))
                if full['utf8_bytes'] > config['parent_max_utf8_bytes']:
                    full['quality']['status'] = 'quarantined'
                    full['quality']['issues'].append('oversize_parent')
                parents.append(full)
                cs = []
                for start, end in split_spans(block['text'], config['child_max_utf8_bytes'] - size(base + '\n')):
                    rec = chunk(page['source'], 'passage', base + '\n' + block['text'][start:end],
                                [{'evidence_id': block['id'], 'type': 'text_span', 'start': start, 'end': end}],
                                ids, config, page['quality'].get('flags', []))
                    rec['parent_id'] = full['chunk_id']
                    cs.append(rec)
                children.extend(cs)
                block_children[block['id']] = cs
            else:
                exclusions.append({'evidence_id': block['id'], 'reason': 'No extracted text; figures are not transcribed.'})
        # Candidate notes, not certified cell-specific footnote attachment. Stop at headings/tables.
        for i, block, cs, parent in table_records:
            nearby = []
            for other in page['blocks'][i + 1:]:
                if other['type'] in ('section_header', 'table'):
                    break
                if other.get('text'):
                    nearby.append(other)
            for rec in cs + [parent]:
                for note in nearby:
                    note_ids = [c['chunk_id'] for c in block_children.get(note['id'], [])]
                    rec['related_chunk_ids'].extend(note_ids)
                    rec['relationships'].append({'type': 'following_table_context_candidate',
                                                  'evidence_id': note['id'], 'chunk_ids': note_ids,
                                                  'method': 'same_page_until_next_heading_or_table',
                                                  'review_status': 'unreviewed'})
    return {'children': children, 'parents': parents, 'exclusions': exclusions}


def expand_context(hit_ids, children, parents, max_bytes=12000, allow_unreviewed=False):
    """Bounded context expansion. Default denies all unreviewed development evidence.

    Return omissions explicitly. Callers must not silently answer as if omitted
    notes or parents were inspected. Exact model-token budgeting is still needed.
    """
    by_id = {r['chunk_id']: r for r in children + parents}
    result, omitted, seen, used = [], [], set(), 0
    def add(record):
        nonlocal used
        key = record['chunk_id']
        if key in seen:
            return True
        if record['quality']['status'] == 'quarantined' or (not allow_unreviewed and record['quality']['status'] != 'validated'):
            omitted.append({'chunk_id': key, 'reason': 'quality_gate'})
            return False
        cost = size(record['text']) + (2 if result else 0)
        if used + cost > max_bytes:
            omitted.append({'chunk_id': key, 'reason': 'context_budget'})
            return False
        seen.add(key)
        result.append(record)
        used += cost
        return True
    for key in dict.fromkeys(hit_ids):
        rec = by_id[key]
        # Never evade a child's quarantine by returning its parent.
        if rec['quality']['status'] == 'quarantined':
            omitted.append({'chunk_id': key, 'reason': 'quality_gate'})
            continue
        parent = by_id.get(rec['parent_id'])
        if parent is None or not add(parent):
            add(rec)
        for related in rec['related_chunk_ids']:
            add(by_id[related])
    return {'records': result, 'utf8_bytes': used, 'omissions': omitted,
            'complete_context': not omitted, 'mode': 'development' if allow_unreviewed else 'validated_only'}


def load_inputs():
    from freeze_extraction import verify_entries
    config = read(ROOT / CONFIG)
    release = read(ROOT / config['extraction_release'])
    # Check current code and the exact extraction inputs, not retired experiment reports.
    from bank_integrity import verify
    errors = verify(data_prefixes=('data/processed/banking_v1/evidence/',
        'data/processed/banking_v1/numeric_consistency/cells.json'))['errors']
    paths = sorted(p for p in release['local_artifacts'] if '/evidence/' in p and p.endswith('.json'))
    paths.append('data/processed/banking_v1/numeric_consistency/cells.json')
    errors += verify_entries(ROOT, {p: release['local_artifacts'][p] for p in paths})
    if errors:
        raise ValueError(f'Frozen extraction inputs changed: {errors}')
    pages = [read(ROOT / p) for p in paths[:-1]]
    return config, pages, read(ROOT / paths[-1]), {p: sha(ROOT / p) for p in paths}


def run():
    config, pages, guard, inputs = load_inputs()
    data = build(pages, config, guard)
    frozen = ROOT / 'releases' / f"{config['version']}.json"
    if frozen.exists() and (OUTPUT/'children.jsonl').exists():
        from bank_integrity import verify
        result = verify(data_prefixes=('data/processed/banking_chunks_v1/',))
        if not result['unchanged']:
            raise ValueError('Frozen chunking files changed. Use a new version and output directory; do not overwrite v1.')
        print(json.dumps({'status': 'already_frozen_unchanged', 'release': str(frozen)}, indent=2))
        return data
    write_lines(OUTPUT / 'children.jsonl', data['children'])
    write_lines(OUTPUT / 'parents.jsonl', data['parents'])
    save(OUTPUT / 'exclusions.json', data['exclusions'])
    summary = {'version': config['version'], 'pages': len(pages),
               'tables': sum(b['type'] == 'table' for p in pages for b in p['blocks']),
               'children': len(data['children']), 'parents': len(data['parents']),
               'child_kinds': dict(Counter(r['kind'] for r in data['children'])),
               'child_quality': dict(Counter(r['quality']['status'] for r in data['children'])),
               'child_max_utf8_bytes': max(r['utf8_bytes'] for r in data['children']),
               'excluded_blocks': len(data['exclusions']), 'inputs_sha256': inputs,
               'configuration_sha256': sha(ROOT / CONFIG),
               'builder_sha256': sha(Path(__file__)),
               'retrieval_evaluation': 'not_performed', 'embedding_token_check': 'pending_model_selection',
               'independent_review': 'pending', 'calculation_ready': False}
    save(OUTPUT / 'build.json', summary)
    print(json.dumps({k: v for k, v in summary.items() if k != 'inputs_sha256'}, indent=2))
    return data


if __name__ == '__main__':
    argparse.ArgumentParser(description=__doc__).parse_args()
    run()
