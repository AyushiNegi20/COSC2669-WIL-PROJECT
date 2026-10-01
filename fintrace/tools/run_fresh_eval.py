"""Independent fresh-question evaluation for FinTrace CBA/NAB backend.

Authored separately from the system's own output. Ground truth (numeric values
and prose anchors) is verified against the six original issuer PDFs before any
scoring. Scores two stages:

  Retrieval  - library.search top-5 passage hit@5, MRR, assembled-context
               coverage, and scope purity (no wrong company/year).
  Generation - the deterministic evidence/answer layer: value, unit and source
               page correctness on answerable questions, correct clarification
               on ambiguous questions, and correct abstention on out-of-scope
               guards.

No external API calls. Read-only against the repo; writes results under
reports/fresh_qa_v1/.
"""
import json
import re
import statistics
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from bank_report_library import get_library, specs                      # noqa: E402
from bank_narrative_routing import narrative_decision, narrative_evidence  # noqa: E402
from answer_bank_release import EvidenceBackend                          # noqa: E402

QSET = ROOT / 'eval/fresh_qa_v1/questions.json'
OUT = ROOT / 'reports/fresh_qa_v1'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf-8')


def norm(text):
    return re.sub(r'\s+', ' ', text or '').strip().casefold()


def number(value):
    s = str(value).replace(',', '').replace('%', '').replace('$', '').strip()
    s = s.replace('(', '-').replace(')', '')
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


UNIT_KEY = {'million': 'million', 'billion': 'billion', 'percent': 'percent',
            '%': 'percent', 'cent': 'cents', 'bps': 'percent'}


def unit_key(unit):
    u = (unit or '').lower()
    for token, key in UNIT_KEY.items():
        if token in u:
            return key
    return u.strip()


# ---- Stage 0: verify ground truth against the original PDFs ------------------

def verify(questions):
    import pymupdf
    docs = {s['id']: s for s in specs()}
    pdfs = {k: pymupdf.open(ROOT / 'data/raw' / s['file']) for k, s in docs.items()}
    checks = []
    try:
        for q in questions['numeric']:
            e = q['expect']
            page_text = norm(pdfs[e['document']][e['pdf_page'] - 1].get_text())
            present = norm(str(e['value'])) in page_text
            checks.append({'id': q['id'], 'kind': 'numeric', 'value': e['value'],
                           'document': e['document'], 'pdf_page': e['pdf_page'], 'present': present})
            if not present:
                raise ValueError(f"Ground-truth value not on cited page: {q['id']} {e['value']} {e['document']} p{e['pdf_page']}")
        for q in questions['narrative']:
            for g in q['gold']:
                page_text = norm(pdfs[g['document']][g['pages'][0] - 1].get_text())
                present = norm(g['anchor']) in page_text
                checks.append({'id': q['id'], 'kind': 'anchor', 'anchor': g['anchor'],
                               'document': g['document'], 'pdf_page': g['pages'][0], 'present': present})
                if not present:
                    raise ValueError(f"Gold anchor not on cited page: {q['id']} '{g['anchor']}' {g['document']} p{g['pages'][0]}")
    finally:
        for p in pdfs.values():
            p.close()
    write(OUT / 'source_check.json', {'verified_against_original_pdfs': True, 'checks': checks})
    print(f"[verify] {len(checks)} ground-truth facts confirmed against original PDFs", flush=True)


# ---- Stage 1: retrieval ------------------------------------------------------

def matches(section, gold):
    src = section['source']
    return (src['document_id'] == gold['document'] and src['pdf_page'] in gold['pages']
            and any(norm(gold['anchor']) in norm(e['quote']) for e in section['excerpts']))


def eval_retrieval(questions, library, backend):
    rows = []
    for q in questions['narrative']:
        scopes = q.get('scopes', [[q.get('bank'), q.get('year')]])
        rankings = []
        for bank, year in scopes:
            sections = library.search(q['question'], year, top_k=5, company=bank, purpose=q.get('purpose'))
            rankings.append({'bank': bank, 'year': year, 'sections': sections})
        decision = narrative_decision(q['question'], topic_hint=q['topic'])
        assembled = narrative_evidence(q['question'], decision,
                                       lambda query: backend.core.answer(query), library.search)
        selected = assembled['answer'].get('source_excerpts', [])
        hits, ranks, coverage = [], [], []
        for gold in q['gold']:
            positions = [i + 1 for r in rankings for i, s in enumerate(r['sections']) if matches(s, gold)]
            hits.append(bool(positions))
            ranks.append(min(positions) if positions else None)
            coverage.append(any(matches(s, gold) for s in selected))
        scope_errors = [s['source'] for r in rankings for s in r['sections']
                        if (s['source']['company'], s['source']['report_year']) != (r['bank'], r['year'])]
        row = {'id': q['id'], 'question': q['question'], 'hit_at_5': hits, 'ranks': ranks,
               'context_coverage': coverage, 'scope_errors': len(scope_errors)}
        rows.append(row)
        print(f"  [retr] {q['id']:18} hit@5={hits} cover={coverage} ranks={ranks} scope_err={len(scope_errors)}", flush=True)
    flat_hits = [v for r in rows for v in r['hit_at_5']]
    flat_cov = [v for r in rows for v in r['context_coverage']]
    flat_ranks = [v for r in rows for v in r['ranks']]
    summary = {
        'questions': len(rows), 'gold_judgements': len(flat_hits),
        'passage_hit_at_5': round(sum(flat_hits) / len(flat_hits), 3),
        'mrr_at_5': round(sum(1 / r if r else 0 for r in flat_ranks) / len(flat_ranks), 3),
        'context_fact_coverage': round(sum(flat_cov) / len(flat_cov), 3),
        'wrong_company_or_year': sum(r['scope_errors'] for r in rows),
        'misses': [r['id'] for r in rows if not all(r['hit_at_5']) or not all(r['context_coverage'])],
    }
    return {'rows': rows, 'summary': summary}


# ---- Stage 2: generation (deterministic evidence/answer layer) ---------------

def answer_cells(result):
    ans = result.get('answer', {})
    return [claim.get('cell', {}) for part in ans.get('parts', []) for claim in part.get('claims', [])]


REFUSAL_STATUS = {'clarify', 'unable_to_verify', 'refuse', 'no_answer', 'declined'}


def eval_generation(questions, backend):
    numeric_rows = []
    for q in questions['numeric']:
        e = q['expect']
        result = backend.answer(q['question'])
        status = result['answer'].get('status')
        cells = answer_cells(result)
        want_val = number(e['value'])
        match = None
        for c in cells:
            if (c.get('company') == q['bank'] and c.get('report_year') == q['year']
                    and number(c.get('value')) == want_val):
                match = c
                break
        # Factually correct = the right figure was returned as a bound claim
        # (source_bound_answer or partial_answer), not a refusal/clarification.
        factual_ok = match is not None and status not in REFUSAL_STATUS
        unit_ok = bool(match) and unit_key(match.get('unit')) == unit_key(e['unit'])
        got_page = match.get('source', {}).get('pdf_page') if match else None
        page_ok = bool(match) and got_page in ([e['pdf_page']] + e.get('alt_pages', []))
        doc_ok = bool(match) and match.get('source', {}).get('document_id') == e['document']
        overall = factual_ok and unit_ok and page_ok and doc_ok
        row = {'id': q['id'], 'question': q['question'], 'status': status, 'factual_ok': factual_ok,
               'expected': e, 'got_value': match.get('value') if match else None,
               'got_unit': match.get('unit') if match else None, 'got_page': got_page,
               'got_document': match.get('source', {}).get('document_id') if match else None,
               'unit_ok': unit_ok, 'page_exact': bool(match) and got_page == e['pdf_page'],
               'page_ok': page_ok, 'doc_ok': doc_ok, 'overall_correct': overall, 'trap': q.get('trap')}
        numeric_rows.append(row)
        flag = 'OK ' if overall else ('~~ ' if factual_ok else 'XX ')
        print(f"  [gen ] {flag}{q['id']:20} status={status:20} val {e['value']}->{row['got_value']} p{e['pdf_page']}->{got_page}", flush=True)

    clarify_rows = []
    for q in questions['clarify_expected']:
        result = backend.answer(q['question'])
        status = result['answer'].get('status') if 'answer' in result else result.get('status')
        cells = answer_cells(result)
        labelled = {(c.get('basis'), c.get('scope')) for c in cells}
        # Correct = either clarifies, or presents >=2 labelled alternatives
        # (e.g. cash vs statutory) rather than silently picking one figure.
        alternatives = len(labelled) >= 2
        passed = status in REFUSAL_STATUS or alternatives
        clarify_rows.append({'id': q['id'], 'question': q['question'], 'status': status,
                             'num_cells': len(cells), 'labelled_alternatives': sorted(str(x) for x in labelled),
                             'passed': passed})
        print(f"  [clar] {'OK ' if passed else 'XX '}{q['id']:20} status={status:20} alternatives={sorted(str(x) for x in labelled)}", flush=True)

    guard_rows = []
    for q in questions['guards']:
        result = backend.answer(q['question'])
        status = result['answer'].get('status') if 'answer' in result else result.get('status')
        cells = answer_cells(result)
        passed = len(cells) == 0  # must not assert any numeric claim
        guard_rows.append({'id': q['id'], 'question': q['question'], 'status': status,
                           'num_cells': len(cells), 'passed': passed})
        print(f"  [grd ] {'OK ' if passed else 'XX '}{q['id']:20} status={status:22} cells={len(cells)}", flush=True)

    n = len(numeric_rows)
    summary = {
        'numeric_total': n,
        'factually_correct': sum(r['factual_ok'] for r in numeric_rows),
        'factually_correct_rate': round(sum(r['factual_ok'] for r in numeric_rows) / n, 3),
        'unit_correct': sum(r['unit_ok'] for r in numeric_rows),
        'page_exact': sum(r['page_exact'] for r in numeric_rows),
        'page_ok_incl_valid_alternatives': sum(r['page_ok'] for r in numeric_rows),
        'fully_correct': sum(r['overall_correct'] for r in numeric_rows),
        'fully_correct_rate': round(sum(r['overall_correct'] for r in numeric_rows) / n, 3),
        'not_factually_correct': [r['id'] for r in numeric_rows if not r['factual_ok']],
        'page_or_unit_deviations': [r['id'] for r in numeric_rows if r['factual_ok'] and not r['overall_correct']],
        'clarify_total': len(clarify_rows), 'clarify_passed': sum(r['passed'] for r in clarify_rows),
        'guard_total': len(guard_rows), 'guard_passed': sum(r['passed'] for r in guard_rows),
        'guard_failures': [r['id'] for r in guard_rows if not r['passed']],
    }
    return {'numeric': numeric_rows, 'clarify': clarify_rows, 'guards': guard_rows, 'summary': summary}


def main():
    questions = read(QSET)
    OUT.mkdir(parents=True, exist_ok=True)
    verify(questions)
    print('[load] building library and backend...', flush=True)
    library = get_library()
    backend = EvidenceBackend()
    print('== RETRIEVAL ==', flush=True)
    retrieval = eval_retrieval(questions, library, backend)
    print('== GENERATION ==', flush=True)
    generation = eval_generation(questions, backend)
    report = {'set': 'fresh_qa_v1', 'retrieval': retrieval['summary'], 'generation': generation['summary']}
    write(OUT / 'retrieval_detail.json', retrieval)
    write(OUT / 'generation_detail.json', generation)
    write(OUT / 'summary.json', report)
    print('\n== SUMMARY ==', flush=True)
    print(json.dumps(report, indent=2), flush=True)


if __name__ == '__main__':
    main()
