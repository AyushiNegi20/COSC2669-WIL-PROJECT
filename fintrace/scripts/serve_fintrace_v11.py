"""Run the generative workbench without changing the frozen v10 demo."""
import argparse
from http.server import ThreadingHTTPServer
from answer_bank_v11 import Backend
from bank_integrity import verify
from bank_retrieval import ROOT
from serve_fintrace_web import handler_for as evidence_handler_for
from urllib.parse import urlsplit


def handler_for(backend, root=ROOT):
    """Reuse the tested UI while preserving its frozen v10 files byte-for-byte."""
    base = evidence_handler_for(backend, root)
    class Handler(base):
        def do_GET(self):
            if not self.local_host():
                return self.send_json(403, {'error': 'Local host only'})
            path = urlsplit(self.path).path
            if path == '/':
                html = (root/'web/index.html').read_text(encoding='utf-8')
                html = html.replace('Explanations are source excerpts, not generated summaries.',
                    'Supported answers use local Qwen-generated explanations with automated checks. If generation fails, original source evidence is shown instead. Automated checks are not independent verification.')
                html = html.replace('and report excerpts. Currency', 'and cited explanations. Currency')
                return self.content(html.encode('utf-8'), 'text/html; charset=utf-8')
            if path == '/app.css':
                css = (root/'web/app.css').read_bytes() + b'\n.result-message { white-space: pre-line; }\n'
                return self.content(css, 'text/css; charset=utf-8')
            return super().do_GET()
    return Handler


def main():
    p = argparse.ArgumentParser(); p.add_argument('--port', type=int, default=8767)
    args = p.parse_args()
    if not verify()['unchanged']:
        raise RuntimeError('Frozen evidence foundation changed; inspect the v10 checkpoint')
    server = ThreadingHTTPServer(('127.0.0.1', args.port), handler_for(Backend()))
    print(f'FinTrace with local Qwen: http://127.0.0.1:{args.port}/', flush=True)
    print('Generation is attempted for supported answers; failures retain source evidence. First request loads models.', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
