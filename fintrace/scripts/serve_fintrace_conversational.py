"""Serve the conversational workspace without altering the frozen UI."""
from urllib.parse import urlsplit
from hashlib import sha256
import json
from bank_retrieval import ROOT
from serve_fintrace_scoped import handler_for as scoped_handler


def handler_for(backend, root=ROOT):
    base = scoped_handler(backend, root)
    files = [p for folder in ('scripts', 'web', 'config') for p in (root / folder).rglob('*')
             if p.is_file() and p.suffix in ('.py', '.json', '.html', '.mjs', '.css')]
    hashes = {str(p.relative_to(root)): sha256(p.read_bytes()).hexdigest() for p in files}
    startup_fingerprint = sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
    assets = {'/': ('conversation.html', 'text/html'),
              '/conversation.css': ('conversation.css', 'text/css'),
              '/conversation.mjs': ('conversation.mjs', 'text/javascript')}
    class Handler(base):
        def do_GET(self):
            if not self.local_host(): return self.send_json(403, {'error':'Local host only'})
            path = urlsplit(self.path).path
            if path == '/health':
                return self.send_json(200, {'status': 'ready', 'version': backend.version,
                    'scope': 'CBA/NAB FY2024/FY2025', 'ambiguity_policy': 'labelled supported alternatives',
                    'startup_fingerprint': startup_fingerprint})
            if path in assets:
                name, kind = assets[path]
                data = (root/'web'/name).read_bytes()
                self.send_response(200)
                self.send_header('Content-Type', kind + '; charset=utf-8')
                self.send_header('Content-Length', str(len(data)))
                self.send_header('Cache-Control', 'no-store')
                self.end_headers(); self.wfile.write(data)
                return
            return super().do_GET()
    return Handler
