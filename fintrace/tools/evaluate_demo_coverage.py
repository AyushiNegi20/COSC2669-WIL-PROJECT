"""Preserve first responses for exposed coverage regressions on the demo backend.

No gold keys are imported. Review source correctness separately. Calculations
and presentation are retained, so scoring cannot silently omit computed fields.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
from time import perf_counter
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from bank_integrity import verify
from serve_fintrace_demo import build_backend
from bank_ui_scope import resolve_scope


def main():
    p=argparse.ArgumentParser();p.add_argument('--previous-run',type=Path);args=p.parse_args()
    cases=[]
    if args.previous_run:
        cases=[{'id':x['id'],'question':x['question'],'scope':{'company':'NAB','year':'2025'}}
               for x in json.loads(args.previous_run.read_text(encoding='utf-8'))['results']]
    cases += [{'id':'extra-'+str(i+1),'question':q} for i,q in enumerate((
        'How did CBA net interest margin change from FY2024 to FY2025? Give basis points too.',
        'How did NAB deposits from customers change between 2024 and 2025?',
        'Why did CBA staff expenses increase in FY2025?',
        'What does NAB say about amortising software in FY2025?',
        'What was NAB statutory net interest income in FY2024?',
        'What was CBA cash profit in FY2025?',
        'What was NAB parent company statutory net interest income in FY2025?',
        'Which sector did CBA invest more in FY2025?',
    ))]
    before=verify()
    if not before['unchanged']:raise RuntimeError(before['errors'])
    out=ROOT/'reports/runs'/('coverage-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    out.mkdir(parents=True,exist_ok=False)
    print('Output:',out,flush=True)
    backend=build_backend();summary=[]
    for case in cases:
        start=perf_counter()
        try:
            resolved=resolve_scope(case['question'],case.get('scope'))
            response=backend.answer(resolved['effective_question'])
            record={'case':case,'resolved_scope':resolved,'response':response}
            answer=response['answer']
            row={**case,'route':response.get('route'),'status':answer['status'],
                 'generation':response.get('generation',{}).get('status'),
                 'claims':[c['text'] for part in answer.get('parts',[]) for c in part.get('claims',[])],
                 'calculations':[c for part in answer.get('parts',[]) for c in part.get('calculations',[])],
                 'display_text':response.get('presentation',{}),'message':answer.get('message','')}
        except Exception as error:
            record={'case':case,'error':repr(error)};row={**case,'error':repr(error)}
        row['seconds']=perf_counter()-start;summary.append(row)
        (out/(case['id']+'.json')).write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
        print(case['id'],row.get('status',row.get('error')),row.get('route'),round(row['seconds'],2),flush=True)
    after=verify()
    (out/'summary.json').write_text(json.dumps({'classification':'exposed development regression; manual source review required',
        'before':before,'after':after,'results':summary},ensure_ascii=False,indent=2),encoding='utf-8')
    if not after['unchanged']:raise RuntimeError(after['errors'])


if __name__=='__main__':main()
