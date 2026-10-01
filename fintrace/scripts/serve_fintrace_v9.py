"""Loopback-only JSON API for the FinTrace demo; no public deployment implied."""
import argparse
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
from threading import Lock
from urllib.parse import urlparse
from answer_bank_v9 import Backend,display


def handler_for(backend):
    lock=Lock()
    class Handler(BaseHTTPRequestHandler):
        def send_json(self,status,payload):
            data=json.dumps(payload,ensure_ascii=False).encode('utf-8')
            self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8')
            self.send_header('Content-Length',str(len(data)));self.send_header('Cache-Control','no-store')
            self.end_headers();self.wfile.write(data)

        def do_GET(self):
            if self.path=='/health': self.send_json(200,{'status':'ready','version':'v9-demo','scope':'CBA/NAB FY2024/FY2025'})
            else: self.send_json(404,{'error':'Use GET /health or POST /ask'})

        def do_POST(self):
            if self.path!='/ask': return self.send_json(404,{'error':'Unknown route'})
            origin=self.headers.get('Origin')
            if origin and urlparse(origin).hostname not in ('localhost','127.0.0.1','::1'):
                return self.send_json(403,{'error':'Cross-site requests are not permitted'})
            if self.headers.get_content_type()!='application/json':
                return self.send_json(415,{'error':'Use application/json'})
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<=16384: raise ValueError('Invalid request size')
                payload=json.loads(self.rfile.read(length))
                if not isinstance(payload,dict) or set(payload)!={'question'} or not isinstance(payload['question'],str):
                    raise ValueError('Expected a JSON object with one string question')
                if not payload['question'].strip() or len(payload['question'])>2000: raise ValueError('Question must contain 1-2000 characters')
                with lock: result=backend.answer(payload['question'])
                self.send_json(200,{**result,'display_text':display(result)})
            except (ValueError,UnicodeDecodeError) as error: self.send_json(400,{'error':str(error)})
            except Exception: self.send_json(503,{'error':'Backend unavailable; see local diagnostics and retry.'})

        def log_message(self,*args): pass  # Do not log user questions into access logs.
    return Handler


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8765);args=parser.parse_args()
    backend=Backend();server=ThreadingHTTPServer(('127.0.0.1',args.port),handler_for(backend))
    print(f'FinTrace demo API: http://127.0.0.1:{args.port}; Ctrl+C stops it.',flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()


if __name__=='__main__': main()


