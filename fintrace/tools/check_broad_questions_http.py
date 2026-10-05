"""Check the real demo HTTP handler, including scope filters, in one fresh process."""
import json
from pathlib import Path
import sys
from threading import Thread
from urllib.request import Request, urlopen

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from serve_fintrace_demo import build_backend
from serve_fintrace_conversational import handler_for
from serve_fintrace_release import ExclusiveLocalServer


def main():
    backend=build_backend()
    server=ExclusiveLocalServer(('127.0.0.1',0),handler_for(backend))
    thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    url='http://127.0.0.1:'+str(server.server_address[1])
    cases=[
        ('CBA profit FY2025',None,'cash_profit',4),
        ('What was EPS?',{'company':'CBA','year':'2025'},'basic_statutory_eps',4),
        ('What was EPS?',{'company':'NAB','year':'2025'},'diluted_statutory_eps',6),
        ('What was income?',{'company':'NAB','year':'2025'},'statutory_operating_income',3),
        ('What were loans?',{'company':'CBA','year':'2025'},'gross_loans',1),
        ('What was margin?',{'company':'NAB','year':'2025'},'nim',2),
        ('What was NAB diluted statutory EPS from continuing operations FY2025?',None,'diluted_statutory_eps',1),
        ('What was NAB net operating income in the FY2024 report?',None,'operating_income',1),
        ('Compare CBA EPS from FY2024 to FY2025',None,'basic_cash_eps',2),
    ]
    results=[]
    try:
        for path in ('/','/health','/conversation.mjs','/conversation.css'):
            with urlopen(url+path,timeout=30) as response:
                assert response.status==200
        for question,scope,metric,count in cases:
            payload={'question':question}
            if scope:payload['scope']=scope
            request=Request(url+'/ask',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
            with urlopen(request,timeout=180) as response:
                result=json.load(response)
            cells=[c['cell'] for p in result['answer'].get('parts',[]) for c in p.get('claims',[])]
            assert len(cells)==count,(question,len(cells),count)
            assert any(c['metric']==metric for c in cells),question
            assert all(c['source'].get('pdf_page') for c in cells),question
            if 'continuing operations' in question:
                assert all(c['scope']=='continuing' for c in cells)
            if 'FY2024 report' in question:
                assert all(c['report_year']==2024 for c in cells)
            if question in ('What was income?','What was margin?'):
                assert result['answer']['status']=='partial_answer'
            if question.startswith('Compare CBA EPS'):
                assert result['answer']['status']=='partial_answer'
                assert any(p.get('calculations') for p in result['answer']['parts'])
            results.append({'question':question,'response':result})
            print('PASS',question,flush=True)
        output=ROOT/'reports/broad-financial-questions-2026-10-05/http-final.json'
        output.write_text(json.dumps(results,indent=2),encoding='utf-8')
        print(str(len(cases))+' HTTP questions and 4 frontend/health asset checks passed.',flush=True)
    finally:
        server.shutdown();server.server_close();thread.join()


if __name__=='__main__':main()
