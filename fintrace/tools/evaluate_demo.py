"""Run the current demo protocol once, preserving every response including errors."""
import argparse
from datetime import datetime,timezone
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import sys
from threading import Thread
from urllib.request import Request,build_opener,ProxyHandler
from time import perf_counter
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from serve_fintrace_demo import build_backend
from serve_fintrace_conversational import handler_for
from bank_integrity import verify

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--quick',action='store_true');args=parser.parse_args()
    check=verify()
    if not check['unchanged']:raise ValueError(check['errors'])
    cases=json.loads((ROOT/'eval/demo/protocol.json').read_text())['cases']
    if args.quick:cases=[c for c in cases if c['id'] in ('01_cba_profit','04_nim_change','08_cba_false_premise','18_unsupported_bank')]
    out=ROOT/'reports/runs'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out.mkdir(parents=True,exist_ok=False)
    server=ThreadingHTTPServer(('127.0.0.1',0),handler_for(build_backend()))
    Thread(target=server.serve_forever,daemon=True).start()
    base='http://127.0.0.1:'+str(server.server_port);opener=build_opener(ProxyHandler({}));results=[]
    try:
        for case in cases:
            payload={k:case[k] for k in ('question','scope','previous_question') if k in case}
            row={'case':case};start=perf_counter()
            try:
                request=Request(base+'/ask',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json','Origin':base})
                with opener.open(request,timeout=180) as response:
                    row.update(http_status=response.status,response=json.load(response))
            except Exception as error:row['error']=str(error)
            row['seconds']=perf_counter()-start
            with (out/(case['id']+'.json')).open('x',encoding='utf-8') as f:json.dump(row,f,indent=2,ensure_ascii=False)
            results.append(row)
            print(case['id'],row.get('http_status'),round(row['seconds'],2),flush=True)
            if 'error' in row:break
    finally:server.shutdown();server.server_close()
    summary={'cases':len(results),'http_errors':sum(r.get('http_status')!=200 for r in results),
        'integrity':verify(),'method':'Developer regression. Read each source and answer; HTTP success is not answer correctness.'}
    with (out/'summary.json').open('x',encoding='utf-8') as f:json.dump(summary,f,indent=2)
    print(out)
    return 1 if summary['http_errors'] or not summary['integrity']['unchanged'] else 0

if __name__=='__main__':raise SystemExit(main())
