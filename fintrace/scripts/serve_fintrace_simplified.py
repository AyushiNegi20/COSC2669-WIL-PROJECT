"""Run the simpler candidate while preserving v12 for comparison."""
import argparse
from http.server import ThreadingHTTPServer
from urllib.parse import urlsplit
from answer_bank_simplified import Backend
from serve_fintrace_v12 import handler_for as previous_handler
from bank_retrieval import ROOT
from bank_integrity import verify


def handler_for(backend, root=ROOT):
    base = previous_handler(backend, root)
    class Handler(base):
        def do_GET(self):
            if not self.local_host(): return self.send_json(403, {'error': 'Local host only'})
            if urlsplit(self.path).path == '/':
                html = (root/'web/index.html').read_text(encoding='utf-8')
                html = html.replace('Explanations are source excerpts, not generated summaries.',
                    'Figures and calculations use source-backed templates, without generative AI. Definitions and explanations use local Qwen when its checks pass; otherwise the original evidence is shown.')
                html = html.replace('Be specific about “profit”: cash and statutory profit are different measures.',
                    'Ask about profit to see cash and statutory figures separately, with their reporting bases.')
                return self.content(html.encode('utf-8'), 'text/html; charset=utf-8')
            return super().do_GET()
    return Handler


def main():
    p = argparse.ArgumentParser(); p.add_argument('--port', type=int, default=8769); args = p.parse_args()
    if not verify()['unchanged']: raise RuntimeError('Frozen source foundation changed')
    server = ThreadingHTTPServer(('127.0.0.1', args.port), handler_for(Backend()))
    print(f'FinTrace simplified: http://127.0.0.1:{args.port}/', flush=True)
    print('Numeric source templates; local Qwen for explanations only.', flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()


if __name__ == '__main__': main()
