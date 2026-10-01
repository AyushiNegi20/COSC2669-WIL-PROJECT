"""Source-retention and development regression checks, not a retrieval benchmark."""
from collections import Counter
import json
from pathlib import Path

from build_bank_chunks import (ROOT, OUTPUT, CONFIG, read, save, sha, size, build,
                               load_inputs, header_rows, row_contexts, columns, render_table)


def lines(path):
    return [json.loads(line) for line in Path(path).read_text(encoding='utf-8').splitlines()]


def validate(data, pages, config, guard):
    errors = []
    children, parents = data['children'], data['parents']
    records = children + parents
    blocks = {b['id']: (p, b) for p in pages for b in p['blocks']}
    by_id = {r['chunk_id']: r for r in records}
    parent_ids = {r['chunk_id'] for r in parents}
    covered_rows, covered_text = {}, {}
    if len(by_id) != len(records):
        errors.append('Duplicate chunk IDs')
    for rec in records:
        label = rec['chunk_id']
        def fail(message):
            errors.append(f'{label}: {message}')
        if rec['schema_version'] != config['schema_version'] or rec['chunking_version'] != config['version']:
            fail('Wrong contract version')
        if rec['utf8_bytes'] != size(rec['text']):
            fail('Incorrect size')
        limit = config['parent_max_utf8_bytes'] if rec['chunk_id'] in parent_ids else config['child_max_utf8_bytes']
        if size(rec['text']) > limit and rec['quality']['status'] != 'quarantined':
            fail('Unquarantined oversize record')
        if rec['quality']['calculation_ready'] or rec['quality']['status'] == 'validated':
            fail('Unreviewed build cannot grant financial approval')
        if not rec['anchors'] or not rec['evidence_ids']:
            fail('Missing provenance')
        for evidence_id in rec['evidence_ids']:
            if evidence_id not in blocks:
                fail('Dangling evidence ID')
            elif blocks[evidence_id][0]['source'] != rec['source']:
                fail('Source identity or document version mismatch')
        for anchor in rec['anchors']:
            if anchor['evidence_id'] not in blocks:
                fail('Unknown anchor')
                continue
            page, block = blocks[anchor['evidence_id']]
            if anchor['evidence_id'] not in rec['evidence_ids']:
                fail('Anchor omitted from evidence list')
            if anchor['type'] == 'text_span':
                start, end = anchor['start'], anchor['end']
                if not (0 <= start < end <= len(block['text'])):
                    fail('Invalid source span')
                elif block['text'][start:end] not in rec['text']:
                    fail('Source passage changed or lost')
                if rec['chunk_id'] not in parent_ids:
                    covered_text.setdefault(block['id'], []).append((start, end))
            elif anchor['type'] == 'table_rows':
                heads = anchor['header_rows']
                context = anchor['context_rows']
                rows = anchor['rows']
                if anchor['column_paths'] != columns(block, heads):
                    fail('Column/header binding differs from source spans')
                if rec['kind'] == 'table_parent':
                    expected_body = '\n'.join(f"Row {i}: " + ' | '.join(r) for i, r in enumerate(block['rows']))
                else:
                    expected_body = render_table(block, rows, heads, context, columns(block, heads))
                if expected_body not in rec['text']:
                    fail('Exact row/column serialization differs from source')
                for row in set(heads + context + rows):
                    if row < 0 or row >= len(block['rows']):
                        fail('Invalid source row')
                        continue
                    for value in block['rows'][row]:
                        if value and value not in rec['text']:
                            fail(f'Source cell missing or changed at row {row}: {value}')
                if rec['chunk_id'] not in parent_ids:
                    if heads != header_rows(block):
                        fail('Missing header rows')
                    expected_context, _ = row_contexts(block, heads)
                    if rows and any(expected_context[r] != context for r in rows):
                        fail('Mixed or missing row scope')
                    covered_rows.setdefault(block['id'], []).extend(rows)
                    relevant_guard = [g for g in guard if g['table_id'] == block['id']
                                      and g['row'] in set(rows + heads + context) and g['issues']]
                    if any(g['category'] == 'numeric_scalar' for g in relevant_guard) and rec['quality']['status'] != 'quarantined':
                        fail('Numeric review flag was not quarantined')
                    if block['id'] in config['quarantined_tables'] and rec['quality']['status'] != 'quarantined':
                        fail('Known malformed table escaped quarantine')
            else:
                fail('Unknown anchor type')
        if rec['chunk_id'] not in parent_ids:
            if rec['parent_id'] not in parent_ids:
                fail('Missing parent')
            elif by_id[rec['parent_id']]['source'] != rec['source']:
                fail('Cross-document/page parent')
        for related in rec['related_chunk_ids']:
            if related not in by_id:
                fail('Missing related context')
            elif by_id[related]['source'] != rec['source']:
                fail('Cross-document/page implicit relationship')
    for block_id, (page, block) in blocks.items():
        if block['type'] == 'table':
            heads = header_rows(block)
            _, sections = row_contexts(block, heads)
            expected = [r for r in range(len(block['rows'])) if r not in heads and r not in sections]
            if sorted(covered_rows.get(block_id, [])) != expected:
                errors.append(f'{block_id}: Missing or duplicated data row')
            table_parents = [r for r in parents if any(a['evidence_id'] == block_id for a in r['anchors'])]
            if len(table_parents) != 1 or table_parents[0]['anchors'][0]['rows'] != list(range(len(block['rows']))):
                errors.append(f'{block_id}: Parent did not preserve complete table')
        elif block.get('text'):
            spans = sorted(covered_text.get(block_id, []))
            cursor = 0
            for start, end in spans:
                if start != cursor:
                    errors.append(f'{block_id}: Missing or duplicated source text')
                cursor = end
            if cursor != len(block['text']):
                errors.append(f'{block_id}: Incomplete source text')
    return errors


def metric_regressions(data):
    """Answer references are used only here, after runtime outputs exist."""
    spec = read(ROOT / 'config/metric_scope_13.json')
    results = []
    for doc, refs in spec['documents'].items():
        for raw in refs:
            ref = dict(zip(spec['row_fields'], raw))
            block_id = f"{doc}:p{ref['pdf_page']:03}:{ref['block_suffix']}"
            matches = [c for c in data['children'] if any(a['evidence_id'] == block_id
                       and a['type'] == 'table_rows' and ref['row'] in a['rows'] for a in c['anchors'])]
            passed = len(matches) == 1 and ref['expected_text'] in matches[0]['text']
            if passed and ref['section_contains']:
                passed = ref['section_contains'].lower() in matches[0]['text'].lower()
            results.append({'document_id': doc, 'metric': ref['metric'], 'passed': passed,
                            'chunk_id': matches[0]['chunk_id'] if len(matches) == 1 else None,
                            'quality': matches[0]['quality']['status'] if len(matches) == 1 else None})
    return results


def regressions(data):
    checks = {}
    def row(block, number):
        return next(c for c in data['children'] if any(a['evidence_id'] == block
                    and a['type'] == 'table_rows' and number in a['rows'] for a in c['anchors']))
    c = row('cba25:p019:b002', 5)
    checks['cash_eps_continuing_scope'] = all(t in c['text'] for t in ['continuing operations', 'Earnings Per Share', '587.8']) and '588.4' not in c['text']
    c = row('cba25:p019:b002', 12)
    checks['cash_eps_total_scope'] = all(t in c['text'] for t in ['including discontinued operations', 'Earnings Per Share', '588.4']) and '587.8' not in c['text']
    c = row('cba25:p090:b003', 16)
    checks['assets_not_investment_securities'] = 'Investment securities' not in c['text']
    c = row('nab25:p013:b006', 4)
    related = {r['chunk_id']: r for r in data['children']}
    checks['nab_restatement_note_linked'] = any('Comparative information has been restated' in related[r]['text'] for r in c['related_chunk_ids'])
    c = row('cba25:p019:b002', 26)
    checks['lcr_quarterly_note_linked'] = any('Quarterly average' in related[r]['text'] for r in c['related_chunk_ids'])
    c = row('cba24:p147:b001', 0)
    checks['glossary_first_definition_not_lost_as_header'] = c['kind'] == 'definition' and 'Australian Accounting Standards' in c['text']
    c = row('nab_ar25:p153:b007', 3)
    checks['malformed_supporting_table_quarantined'] = c['quality']['status'] == 'quarantined'
    c = row('nab25:p013:b006', 5)
    checks['negative_sign_preserved'] = '(9,848)' in c['text']
    c = row('cba25:p053:b002', 8)
    checks['source_vintages_not_merged'] = row('cba24:p051:b000', 8)['source']['source_sha256'] != c['source']['source_sha256']
    from build_bank_chunks import expand_context
    bad = row('nab_ar25:p153:b007', 3)
    checks['quarantine_cannot_expand'] = not expand_context([bad['chunk_id']], data['children'], data['parents'], allow_unreviewed=True)['records']
    checks['default_context_denies_unreviewed'] = not expand_context([c['chunk_id']], data['children'], data['parents'])['records']
    expanded = expand_context([c['chunk_id'], c['chunk_id']], data['children'], data['parents'], max_bytes=4000, allow_unreviewed=True)
    checks['context_bounded_and_deduplicated'] = expanded['utf8_bytes'] <= 4000 and len(expanded['records']) == len({r['chunk_id'] for r in expanded['records']})
    return checks


def run():
    config, pages, guard, inputs = load_inputs()
    data = {'children': lines(OUTPUT / 'children.jsonl'), 'parents': lines(OUTPUT / 'parents.jsonl'),
            'exclusions': read(OUTPUT / 'exclusions.json')}
    errors = validate(data, pages, config, guard)
    build_info = read(OUTPUT / 'build.json')
    if build_info['inputs_sha256'] != inputs or build_info['configuration_sha256'] != sha(ROOT / CONFIG):
        errors.append('Stale build inputs or configuration')
    # A maintenance-only builder change is acceptable only when the complete
    # deterministic rebuild below still exactly equals the stored chunks.
    from jsonschema import Draft202012Validator
    schema = read(ROOT / 'schemas/banking_chunk.schema.json')
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    for rec in data['children'] + data['parents']:
        errors.extend(f"{rec['chunk_id']}: schema: {error.message}" for error in validator.iter_errors(rec))
    checks = regressions(data)
    metrics = metric_regressions(data)
    # Whole-output comparison detects changes to bindings/text/flags omitted by focused checks.
    rebuilt = build(pages, config, guard)
    checks['deterministic_rebuild_exact'] = rebuilt == data
    errors += [f'Regression failed: {k}' for k, passed in checks.items() if not passed]
    errors += [f"Metric retention failed: {r['document_id']}:{r['metric']}" for r in metrics if not r['passed']]
    report = {'version': config['version'], 'status': 'passed_development_checks' if not errors else 'failed',
              'pages': len(pages), 'tables': sum(b['type'] == 'table' for p in pages for b in p['blocks']),
              'source_text_blocks': sum(bool(b.get('text')) for p in pages for b in p['blocks']),
              'children': len(data['children']), 'parents': len(data['parents']),
              'child_quality': dict(Counter(c['quality']['status'] for c in data['children'])),
              'child_max_utf8_bytes': max(c['utf8_bytes'] for c in data['children']),
              'parent_max_utf8_bytes': max(c['utf8_bytes'] for c in data['parents']),
              'table_rows': sum(len(b['rows']) for p in pages for b in p['blocks'] if b['type'] == 'table'),
              'regressions': checks, 'metric_anchors_retained': sum(r['passed'] for r in metrics),
              'metric_anchor_quality': dict(Counter(r['quality'] for r in metrics)),
              'metric_checks': metrics, 'errors': errors, 'inputs_sha256': inputs,
              'outputs_sha256': {str(p.relative_to(ROOT)).replace('\\', '/'): sha(p)
                                 for p in sorted(OUTPUT.iterdir()) if p.is_file()},
              'independent_evaluation': 'not_performed', 'retrieval_benchmark': 'not_performed',
              'embedding_token_check': 'pending_model_selection',
              'limitations': ['This checks preservation of existing extraction, not correctness of every original PDF cell.',
                             'All current source pages and metric anchors are development-exposed.',
                             'Candidate note links are not human-confirmed footnote bindings.',
                             'Quarantined chunks must not be used in normal answering. Other chunks remain development-only.',
                             'No exact tokenizer limit, Hit@5, nDCG or answer accuracy is certified here.']}
    save(ROOT / 'reports/banking_chunking_acceptance.json', report)
    print(json.dumps({k: v for k, v in report.items() if k not in ('inputs_sha256', 'outputs_sha256', 'metric_checks')}, indent=2))
    return report


if __name__ == '__main__':
    raise SystemExit(1 if run()['errors'] else 0)
