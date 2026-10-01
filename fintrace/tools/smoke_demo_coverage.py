"""Local HTTP regression, preserving every response. Not an independent eval."""
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from threading import Thread
from urllib.request import Request, urlopen

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from bank_integrity import verify
from serve_fintrace_demo import build_backend, ExclusiveLocalServer, handler_for


def main():
    before=verify()
    if not before['unchanged']:raise RuntimeError(before['errors'])
    backend=build_backend()
    server=ExclusiveLocalServer(('127.0.0.1',0),handler_for(backend))
    thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    base=f'http://127.0.0.1:{server.server_port}'
    out=ROOT/'reports/runs'/('coverage-http-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    out.mkdir(parents=True,exist_ok=False)
    print('Output:',out,flush=True)
    questions=(
        'What were NAB FY2025 basic and diluted statutory earnings per share?',
        'Why did NAB credit impairment charge rise in FY2025?',
        'How did NAB net interest margin change from FY2024 to FY2025 in basis points?',
        'What was CBA profit in FY2025?',
        'Which sector did CBA invest more in FY2025?',
        'Why did NAB statutory operating expenses increase in FY2025?',
        'Using Note 2, reconcile NAB FY2025 cash earnings to statutory profit attributable to owners.',
        'What was NAB FY2025 underlying profit?',
        'What was NAB actual FY2026 profit?',
    )
    results=[]
    try:
        for path in ('/','/health','/conversation.mjs','/reports/nab_ar25.pdf'):
            with urlopen(base+path,timeout=30) as response:
                prefix=response.read(100)
                assert response.status==200
                if path.endswith('.pdf'):assert prefix.startswith(b'%PDF-')
        for i,question in enumerate(questions,1):
            request=Request(base+'/ask',data=json.dumps({'question':question}).encode(),
                            headers={'Content-Type':'application/json','Origin':base})
            with urlopen(request,timeout=180) as response:result=json.load(response)
            (out/f'{i:02}.json').write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
            results.append(result)
            print(i,result['answer']['status'],round(result['seconds'],2),flush=True)
        eps=[c['cell']['value'] for p in results[0]['answer']['parts'] for c in p['claims']]
        assert eps==['221.0','219.9'],eps
        explanation=results[1]['answer']['source_excerpts']
        assert explanation and all(s['source']['document_id']=='nab25' for s in explanation)
        changes=[c for p in results[2]['answer']['parts'] for c in p.get('calculations',[])]
        assert changes and all(c['basis_points']=='3.00' for c in changes)
        assert {c['cell']['basis'] for p in results[3]['answer']['parts'] for c in p['claims']}=={'cash','statutory'}
        assert results[4]['answer']['status']=='source_bound_answer'
        assert results[5]['answer']['source_excerpts']
        assert results[6]['coverage']['kind']=='checked_segment_reconciliation'
        assert results[7]['coverage']['kind']=='checked_underlying_profit'
        assert results[8]['answer']['status']=='unable_to_verify'
        after=verify()
        assert after['unchanged'],after
        (out/'summary.json').write_text(json.dumps({'before':before,'after':after,'http_cases':len(questions),
            'checks':'passed; exposed regression, not independent accuracy',
            'note':'All first responses are preserved. Assertions use source-checked development expectations.'},indent=2),encoding='utf-8')
        print('HTTP/source-link/regression checks passed.',flush=True)
    finally:
        server.shutdown();server.server_close();thread.join(timeout=5)


if __name__=='__main__':main()
