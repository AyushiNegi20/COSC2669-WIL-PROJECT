"""Preserve demo responses for broad financial questions, without an answer key.

This is a developer regression rehearsal, not a blind accuracy assessment.
Run sequentially on the configured local demo backend.
"""
import argparse
import json
from pathlib import Path
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from serve_fintrace_demo import build_backend


def questions():
    patterns = [
        'What was {bank} profit in FY2025?',
        'What was {bank} EPS in FY2025?',
        'What was {bank} income in FY2025?',
        'How much income did {bank} earn in FY2025?',
        'What were {bank} loans in FY2025?',
        'What were {bank} total loans in FY2025?',
        'What was {bank} margin in FY2025?',
        'How did {bank} NIM change from FY2024 to FY2025?',
        'What was {bank} net interest income in FY2025?',
        'What was {bank} diluted statutory EPS in FY2025?',
        'What were {bank} net loans in FY2025?',
        'What was {bank} net operating income in the FY2024 report?',
    ]
    return [pattern.format(bank=bank) for bank in ('CBA', 'NAB') for pattern in patterns]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    backend = build_backend()
    results = []
    for i, question in enumerate(questions(), 1):
        start = perf_counter()
        item = {'id': f'broad{i:02}', 'question': question}
        try:
            item['response'] = backend.answer(question)
        except Exception as error:
            item['error'] = repr(error)
        item['seconds'] = perf_counter() - start
        (args.output / f'{i:02}.json').write_text(json.dumps(item, indent=2), encoding='utf-8')
        results.append(item)
        response = item.get('response', {})
        answer = response.get('answer', {})
        cells = [c['cell'] for p in answer.get('parts', []) for c in p.get('claims', [])]
        print(json.dumps({'id': item['id'], 'question': question,
              'status': answer.get('status', item.get('error')), 'seconds': round(item['seconds'], 2),
              'cells': [{k: c.get(k) for k in ('metric', 'basis', 'scope', 'value', 'unit')} for c in cells],
              'message': answer.get('message', ''),
              'notes': answer.get('limitations', []),
              'paragraphs': response.get('presentation', {}).get('paragraphs', [])}), flush=True)
    (args.output / 'results.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
    return int(any('error' in r for r in results))


if __name__ == '__main__':
    raise SystemExit(main())
