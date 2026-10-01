"""Serve the contract-checked candidate; do not modify the frozen v11 demo."""
import argparse
from http.server import ThreadingHTTPServer
from answer_bank_v12 import Backend, EvidenceBackend
from serve_fintrace_v11 import handler_for as previous_handler
from bank_integrity import verify
from bank_retrieval import ROOT
from urllib.parse import urlsplit


def handler_for(backend, root=ROOT):
    base = previous_handler(backend, root)
    class Handler(base):
        def do_GET(self):
            if not self.local_host(): return self.send_json(403, {'error': 'Local host only'})
            if urlsplit(self.path).path == '/health':
                return self.send_json(200, {'status': 'ready', 'version': backend.version,
                    'scope': 'CBA/NAB FY2024/FY2025', 'ambiguity_policy': 'labelled supported alternatives'})
            return super().do_GET()
    return Handler


def main():
    p = argparse.ArgumentParser(); p.add_argument('--port', type=int, default=8768)
    p.add_argument('--evidence-only', action='store_true'); a = p.parse_args()
    if not verify()['unchanged']: raise RuntimeError('Frozen source foundation changed')
    backend = EvidenceBackend() if a.evidence_only else Backend()
    server = ThreadingHTTPServer(('127.0.0.1', a.port), handler_for(backend))
    print(f'FinTrace v12: http://127.0.0.1:{a.port}/', flush=True)
    print('Ambiguous profit returns labelled alternatives. Unsupported related figures are not substituted.', flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()


if __name__ == '__main__': main()
