"""First-response, real-backend wording regression with reproducible raw outputs.

Compares financial semantics to canonical requests, not to a blind gold key.
Narrative outputs require manual source review, never an automatic accuracy pass.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'eval/wording')]
from cases import families, controls, NARRATIVE
from bank_conversation import followup
from bank_ui_scope import resolve_scope
from bank_integrity import verify
from serve_fintrace_demo import build_backend


def cells(result):
    return [c['cell'] for part in result.get('answer', {}).get('parts', []) for c in part.get('claims', [])]


def signature(result):
    keys = ('company', 'metric', 'period_end', 'period_kind', 'unit', 'basis', 'scope', 'value', 'report_year')
    values = sorted({tuple(str(c.get(k, '')) for k in keys) for c in cells(result)})
    calculations = sorted(json.dumps({k: c.get(k) for k in
        ('operation', 'absolute_change', 'unit', 'relative_change_percent', 'percentage_points', 'operand_labels')}, sort_keys=True)
        for part in result.get('answer', {}).get('parts', []) for c in part.get('calculations', []))
    return {'cells': values, 'calculations': calculations}


def lookup_issues(result, bank, metrics, year=None):
    found = cells(result)
    issues = []
    if not set(metrics) <= {c['metric'] for c in found}: issues.append('Missing requested metric')
    for cell in found:
        if cell['company'] != bank or cell['metric'] not in metrics: issues.append('Wrong bank or metric')
        if year and cell['period_end'][:4] != str(year): issues.append('Wrong requested year')
        if not cell.get('source', {}).get('document_id') or not cell.get('source', {}).get('pdf_page'):
            issues.append('Missing source citation')
    if result.get('binding_validation', {}).get('passed') is False: issues.append('Binding validation failed')
    return sorted(set(issues))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--stage', choices=('numeric', 'narrative', 'all'), default='all')
    parser.add_argument('--families-only', action='store_true',
                        help='Run supported numerical wording families only; omit historical scope controls and narrative cases.')
    args = parser.parse_args()
    before = verify()
    if not before['unchanged']: raise ValueError(before['errors'])
    out = ROOT / 'reports/runs' / ('wording-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    out.mkdir(parents=True, exist_ok=False)
    backend = build_backend()
    rows = []

    def run(case):
        start = perf_counter()
        try:
            question, notes = followup(case['question'], case.get('previous_question'))
            scope = resolve_scope(question, case.get('scope'))
            response = backend.answer(scope['effective_question'])
            row = {'case': case, 'response': response, 'scope': scope, 'followup_notes': notes}
        except Exception as error:
            row = {'case': case, 'error': repr(error)}
        row['seconds'] = perf_counter() - start
        return row

    def save(row, issues, review=False):
        row['issues'] = issues
        row['assessment'] = 'fail' if issues else 'needs_manual_review' if review else 'pass'
        with (out / (row['case']['id'] + '.json')).open('x', encoding='utf-8') as stream:
            json.dump(row, stream, ensure_ascii=False, indent=2)
        rows.append({k: row[k] for k in ('case', 'seconds', 'issues', 'assessment')})
        print(row['case']['id'], row['assessment'], round(row['seconds'], 2), '; '.join(issues), flush=True)

    if args.stage != 'narrative':
        for family in families():
            baseline = run({'id': family['id'] + '_canonical', 'question': family['baseline']})
            reference = baseline.get('response', {})
            issues = lookup_issues(reference, family['bank'], [family['metric']], family.get('year'))
            if family.get('calculation') and not signature(reference)['calculations']: issues.append('Missing calculation')
            save(baseline, issues + ([baseline['error']] if 'error' in baseline else []))
            for i, question in enumerate(family['variants'], 1):
                row = run({'id': family['id'] + f'_variant{i}', 'question': question})
                result = row.get('response', {})
                problems = lookup_issues(result, family['bank'], [family['metric']], family.get('year'))
                if signature(result) != signature(reference): problems.append('Financial output differs from canonical wording')
                if issues: problems.append('Canonical request failed; equivalence alone is not a pass')
                save(row, problems + ([row['error']] if 'error' in row else []))
        for case in (() if args.families_only else controls()):
            row = run(case); result = row.get('response', {})
            if case['kind'] == 'guard':
                problems = [] if result.get('answer', {}).get('status') == 'unable_to_verify' and not cells(result) else ['Expected a safe refusal without substituted figures']
            else:
                problems = lookup_issues(result, case['bank'], case['metrics'], case['year'])
            save(row, problems + ([row['error']] if 'error' in row else []))
    if args.stage != 'numeric' and not args.families_only:
        for case in NARRATIVE:
            row = run(case); result = row.get('response', {})
            problems = lookup_issues(result, case['bank'], case['metrics'], case['year']) if case['kind'] == 'mixed' else []
            if not result.get('answer', {}).get('source_excerpts'): problems.append('No narrative evidence returned')
            if result.get('answer', {}).get('status') in ('clarify', 'unable_to_verify'): problems.append('Expected a sourced explanation, not a clarification/refusal')
            if case['kind'] == 'mixed' and result.get('generation', {}).get('status') == 'fallback' and result.get('answer', {}).get('status') != 'partial_answer':
                problems.append('Fallback explanation must be labelled partial')
            save(row, problems + ([row['error']] if 'error' in row else []), review=True)
    summary = {'method': 'Developer-authored metamorphic regression, not independent accuracy. Matching a canonical answer does not prove it correct.',
               'counts': dict(Counter(r['assessment'] for r in rows)), 'cases': rows,
               'integrity_before': before, 'integrity_after': verify()}
    (out / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(out, summary['counts'], flush=True)
    return 1 if summary['counts'].get('fail') or not summary['integrity_after']['unchanged'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
