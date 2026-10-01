"""Evaluate the actual demo configuration; never import answer keys into runtime.

Accept {questions:[{id,q}]} or a list of {id,question}. Extra fields are ignored.
Every response, calculation and source is preserved without hidden retries.
"""
import argparse
from datetime import datetime,timezone
from hashlib import sha256
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
    parser=argparse.ArgumentParser()
    parser.add_argument('--questions',required=True,type=Path)
    args=parser.parse_args()
    raw=json.loads(args.questions.read_text(encoding='utf-8-sig'))
    cases=raw.get('questions',raw.get('cases',[])) if isinstance(raw,dict) else raw
    if not isinstance(cases,list) or not cases:raise ValueError('Expected a non-empty question list')
    before=verify()
    if not before['unchanged']:raise RuntimeError(before['errors'])
    def git_output(*arguments):
        run=subprocess.run(['git','-c','safe.directory='+ROOT.as_posix(),*arguments],
                           cwd=ROOT,capture_output=True,text=True,check=False)
        return run.stdout.strip() if run.returncode==0 else 'unavailable'
    candidate={'commit':git_output('rev-parse','HEAD'),'working_tree':git_output('status','--short'),
               'manifest_sha256':sha256((ROOT/'releases/current.json').read_bytes()).hexdigest()}
    out=ROOT/'reports/runs'/('release-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    out.mkdir(parents=True,exist_ok=False)
    print('Output:',out,flush=True)
    backend=build_backend();results=[]
    for i,case in enumerate(cases,1):
        start=perf_counter()
        item={'id':str(case.get('id',i)), 'question':case.get('q',case.get('question'))}
        try:
            scope=resolve_scope(item['question'],case.get('scope'))
            item['scope']=scope
            item['response']=backend.answer(scope['effective_question'])
        except Exception as error:item['error']=repr(error)
        item['seconds']=perf_counter()-start
        (out/f'{i:03}.json').write_text(json.dumps(item,indent=2,ensure_ascii=False),encoding='utf-8')
        results.append(item)
        print(item['id'],item.get('response',{}).get('answer',{}).get('status',item.get('error')),
              round(item['seconds'],2),flush=True)
    after=verify()
    config=json.loads((ROOT/'config/demo_local8b.json').read_text(encoding='utf-8'))
    summary={'entrypoint':'serve_fintrace_demo.build_backend','configuration':config,'candidate':candidate,
             'before':before,'after':after,'questions':len(results),
             'errors':sum('error' in r for r in results),
             'assessment':'Unscored first responses. Review correctness, completeness, citations and refusals independently.',
             'results':results}
    (out/'results.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False),encoding='utf-8')
    if not after['unchanged']:raise RuntimeError(after['errors'])
    return int(summary['errors']>0)


if __name__=='__main__':raise SystemExit(main())
