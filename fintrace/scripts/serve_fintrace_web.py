"""Same-origin local workbench over the unchanged v9 API."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
from http.server import ThreadingHTTPServer
from urllib.parse import urlsplit
from bank_retrieval import ROOT
from serve_fintrace_v9 import handler_for as api_handler_for

STATIC={
    '/':('index.html','text/html; charset=utf-8'),
    '/app.css':('app.css','text/css; charset=utf-8'),
    '/app.mjs':('app.mjs','text/javascript; charset=utf-8'),
    '/ui-model.mjs':('ui-model.mjs','text/javascript; charset=utf-8'),
    '/favicon.svg':('favicon.svg','image/svg+xml'),
}
CSP="default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"


def document_catalog(root):
    manifest=json.loads((root/'config/banking_sources.json').read_text(encoding='utf-8'))
    raw=(root/'data/raw').resolve();catalog=[];files={}
    for doc in manifest['documents']:
        path=(raw/doc['file']).resolve()
        if not path.is_relative_to(raw): raise ValueError('Document path escaped the raw source directory')
        available=path.is_file() and sha256(path.read_bytes()).hexdigest()==doc['sha256']
        catalog.append({k:doc[k] for k in ('id','company','report_year','period_end','title','role')})
        catalog[-1].update(available=available,path=f"/reports/{doc['id']}.pdf" if available else None)
        if available: files[f"/reports/{doc['id']}.pdf"]=(path,doc['sha256'])
    return catalog,files


def handler_for(backend,root=ROOT):
    base=api_handler_for(backend)
    catalog,pdfs=document_catalog(root)
    class Handler(base):
        def setup(self):
            super().setup()
            self.connection.settimeout(30)

        def end_headers(self):
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Referrer-Policy','no-referrer')
            self.send_header('Content-Security-Policy',CSP)
            super().end_headers()

        def local_host(self):
            try: host=urlsplit('http://'+self.headers.get('Host','')).hostname
            except ValueError: return False
            return host in ('127.0.0.1','localhost','::1')

        def content(self,data,kind):
            self.send_response(200)
            self.send_header('Content-Type',kind)
            self.send_header('Content-Length',str(len(data)))
            self.send_header('Cache-Control','no-store')
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if not self.local_host(): return self.send_json(403,{'error':'Local host only'})
            path=urlsplit(self.path).path
            if path in STATIC:
                file,kind=STATIC[path]
                return self.content((root/'web'/file).read_bytes(),kind)
            if path=='/documents': return self.send_json(200,{'documents':catalog})
            if path in pdfs:
                file,expected=pdfs[path]
                try: data=file.read_bytes()
                except OSError: return self.send_json(404,{'error':'Source file is unavailable'})
                if sha256(data).hexdigest()!=expected:
                    return self.send_json(409,{'error':'Source file changed; refusing to show a different version'})
                return self.content(data,'application/pdf')
            if self.path=='/health':
                return self.send_json(200,{'status':'ready','version':getattr(backend,'version','v9-demo'),'scope':'CBA/NAB FY2024/FY2025'})
            return self.send_json(404,{'error':'Not found'})

        def do_POST(self):
            if not self.local_host(): return self.send_json(403,{'error':'Local host only'})
            origin=self.headers.get('Origin')
            if origin and origin!='http://'+self.headers.get('Host',''):
                return self.send_json(403,{'error':'Same-origin requests only'})
            return super().do_POST()
    return Handler


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8766);args=parser.parse_args()
    from bank_integrity import verify
    if not verify()['unchanged']: raise RuntimeError('The tested backend checkpoint has changed')
    from answer_bank_v10 import Backend
    server=ThreadingHTTPServer(('127.0.0.1',args.port),handler_for(Backend()))
    print(f'FinTrace workbench: http://127.0.0.1:{args.port} | Ctrl+C to stop',flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()


if __name__=='__main__': main()
