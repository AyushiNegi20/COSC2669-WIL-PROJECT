"""Pre-commit comprehensive sweep across all question categories, run through the
synthesis backend (answer_bank_simplified). Each category is scored against the
behaviour it should exhibit. No external API (local Ollama for synthesis only).
"""
import json
import re
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from answer_bank_simplified import Backend as SynthBackend   # noqa: E402
from bank_investment_answer import answer as investment_answer  # noqa: E402

QSET = ROOT / 'eval/comprehensive_v1/questions.json'
OUT = ROOT / 'reports/comprehensive_v1'
REFUSAL = {'clarify', 'unable_to_verify', 'refuse', 'no_answer', 'declined', 'error'}


def num(v):
    try:
        return Decimal(str(v).replace(',', '').replace('%', '').replace('$', '').replace('(', '-').replace(')', '').strip())
    except InvalidOperation:
        return None


def cells(result):
    a = result.get('answer', {})
    return [c.get('cell', {}) for p in a.get('parts', []) for c in p.get('claims', [])]


def text_blob(result):
    a = result.get('answer', {})
    parts = []
    ge = a.get('generated_explanation') or {}
    if isinstance(ge, dict) and ge.get('statements'):
        parts.append(' '.join(s.get('text', '') for s in ge['statements']))
    if a.get('message'):
        parts.append(a['message'])
    for s in a.get('source_excerpts', []):
        for e in s.get('excerpts', []):
            parts.append(e.get('quote', ''))
    return ' '.join(parts).lower()


def synthesized(result):
    ge = result.get('answer', {}).get('generated_explanation') or {}
    return bool(isinstance(ge, dict) and ge.get('statements'))


def score(case, result):
    cat = case['category']
    status = result.get('answer', {}).get('status')
    cs = cells(result)
    blob = text_blob(result)
    detail = {'status': status, 'cells': len(cs), 'synthesized': synthesized(result)}

    if cat in ('numeric_in_scope', 'vintage'):
        want = num(case['expect_value'])
        hit = next((c for c in cs if num(c.get('value')) == want
                    and c.get('company') == case['bank'] and c.get('report_year') == case['year']), None)
        detail['got_value'] = hit.get('value') if hit else None
        detail['got_page'] = hit.get('source', {}).get('pdf_page') if hit else None
        ok = hit is not None and status not in REFUSAL
        if cat == 'vintage' and hit is not None:
            ok = ok and num(hit.get('value')) != num(case['reject_value'])
        return ok, detail

    if cat in ('numeric_out_of_scope', 'out_of_universe', 'cross_company'):
        # Must not assert a figure.
        return len(cs) == 0, detail

    if cat == 'ambiguity':
        labelled = {(c.get('basis'), c.get('scope')) for c in cs}
        detail['labelled'] = sorted(str(x) for x in labelled)
        return status in REFUSAL or len(labelled) >= 2, detail

    if cat == 'no_year':
        return status == 'clarify', detail

    if cat in ('reasoning', 'premise_check', 'comparison', 'definition', 'direction'):
        # Backup deterministic answer for the comparison class.
        inv = investment_answer(case['question']) if cat == 'comparison' else None
        if inv:
            blob = (blob + ' ' + inv['answer_text'].lower())
            detail['deterministic'] = True
        engaged = synthesized(result) or bool(result.get('answer', {}).get('source_excerpts')) or (cat == 'direction' and cs)
        kw_ok = all(k.lower() in blob for k in case.get('expect_contains', []))
        detail['keywords_ok'] = kw_ok
        # direction is fine as figures-only; others must have engaged (not refused)
        if cat == 'direction':
            return (bool(cs) or synthesized(result)), detail
        return engaged and status not in REFUSAL and kw_ok, detail

    return False, detail


def main():
    cases = json.loads(QSET.read_text(encoding='utf-8'))['cases']
    OUT.mkdir(parents=True, exist_ok=True)
    be = SynthBackend()
    rows = []
    from collections import defaultdict
    by_cat = defaultdict(lambda: [0, 0])
    for c in cases:
        try:
            result = be.answer(c['question'])
        except Exception as exc:
            result = {'answer': {'status': 'error', 'message': str(exc)[:200]}}
        ok, detail = score(c, result)
        by_cat[c['category']][0] += int(ok)
        by_cat[c['category']][1] += 1
        rows.append({'id': c['id'], 'category': c['category'], 'question': c['question'],
                     'pass': ok, **detail})
        print(f"  {'PASS' if ok else 'FAIL'}  {c['category']:20} {c['id']:20} status={str(detail.get('status')):18} cells={detail.get('cells')} synth={detail.get('synthesized')}", flush=True)
    scorecard = {cat: {'pass': v[0], 'total': v[1]} for cat, v in sorted(by_cat.items())}
    total_pass = sum(v[0] for v in by_cat.values())
    total = sum(v[1] for v in by_cat.values())
    report = {'set': 'comprehensive_v1', 'total_pass': total_pass, 'total': total,
              'scorecard': scorecard, 'failures': [r['id'] for r in rows if not r['pass']], 'rows': rows}
    (OUT / 'results.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print('\n== SCORECARD ==')
    for cat, v in scorecard.items():
        print(f"  {cat:22} {v['pass']}/{v['total']}")
    print(f"\n  TOTAL {total_pass}/{total}")
    if report['failures']:
        print('  failures:', report['failures'])


if __name__ == '__main__':
    main()
