"""Run the Qwen-synthesis backend on mentor-style reasoning questions and record
what it actually returns: a synthesized answer, an excerpts-only fallback, or a
refusal. Compared against reference answers written from the original PDFs.

Uses answer_bank_simplified, which wires the local Ollama Qwen synthesis
(ContractSynthesisClient + add_generation). No external API.
"""
import json
import sys
from pathlib import Path
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from answer_bank_simplified import Backend as SynthBackend           # noqa: E402
from bank_investment_answer import answer as investment_answer        # noqa: E402

QSET = ROOT / 'eval/reasoning_qa_v1/questions.json'
OUT = ROOT / 'reports/reasoning_qa_v1'


def synthesized_prose(result):
    ans = result.get('answer', {})
    ge = ans.get('generated_explanation') or {}
    stmts = ge.get('statements') if isinstance(ge, dict) else None
    if stmts:
        return ' '.join(s.get('text', '') for s in stmts).strip()
    return None


def classify(result, prose, investment_hit):
    status = result.get('answer', {}).get('status')
    gen = result.get('generation', {}).get('status')
    if investment_hit:
        return 'answered_deterministic'
    if prose:
        return 'answered_synthesized'
    if status in ('clarify', 'unable_to_verify'):
        return 'refused'
    excerpts = result.get('answer', {}).get('source_excerpts')
    if excerpts:
        return 'excerpts_only'
    return 'other:' + str(status)


def main():
    questions = json.loads(QSET.read_text(encoding='utf-8'))['questions']
    OUT.mkdir(parents=True, exist_ok=True)
    be = SynthBackend()
    rows = []
    for q in questions:
        started = perf_counter()
        try:
            result = be.answer(q['question'])
        except Exception as exc:  # keep the run going
            result = {'answer': {'status': 'error', 'message': str(exc)[:200]}}
        prose = synthesized_prose(result)
        inv = investment_answer(q['question'])  # deterministic comparison answerer (new)
        outcome = classify(result, prose, inv is not None)
        rows.append({
            'id': q['id'], 'question': q['question'], 'kind': q['kind'],
            'reference_answer': q['reference_answer'],
            'rag_outcome': outcome,
            'rag_answer_status': result.get('answer', {}).get('status'),
            'rag_generation_status': result.get('generation', {}).get('status'),
            'rag_synthesized': prose,
            'deterministic_answer': inv['answer_text'] if inv else None,
            'seconds': round(perf_counter() - started, 1),
        })
        print(f"  {q['id']:18} {outcome:22} ans={result.get('answer',{}).get('status')!s:16} gen={result.get('generation',{}).get('status')}", flush=True)
    counts = {}
    for r in rows:
        counts[r['rag_outcome']] = counts.get(r['rag_outcome'], 0) + 1
    report = {'set': 'reasoning_qa_v1', 'n': len(rows), 'outcome_counts': counts, 'rows': rows}
    (OUT / 'results.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print('\n== OUTCOME COUNTS ==')
    print(json.dumps(counts, indent=2))


if __name__ == '__main__':
    main()
