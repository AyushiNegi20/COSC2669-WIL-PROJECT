"""Optional scope controls over the release app; preserve frozen UI artifacts."""
import json
from threading import Lock
from urllib.parse import urlsplit
from bank_retrieval import ROOT
from bank_ui_scope import resolve_scope
from bank_conversation import followup
from answer_bank_v9 import display
from serve_fintrace_simplified import handler_for as previous_handler


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('Frozen frontend integration anchor changed: ' + old[:70])
    return text.replace(old, new, 1)


def scoped_app(text):
    """Small checked overlay, not another fork of the full frozen frontend."""
    text = 'import {readScope, restoreScope, disableScope, renderScope} from "/scope-controls.mjs";\n' + text
    changes = [
        ('$("question").disabled = state.busy;', '$("question").disabled = state.busy; disableScope(state.busy);'),
        ('if (answer.message) fragment.append', 'renderScope(result, fragment);\n  if (answer.message) fragment.append'),
        ('button.title = entry.question;', 'if (entry.result.ui_scope) button.append(el("small", "history-scope", entry.result.ui_scope.summary));\n    button.title = entry.question;'),
        ('$("question").value = entry.question; updateForm(); renderResult(entry);', '$("question").value = entry.question; restoreScope(entry.scope); updateForm(); renderResult(entry);'),
        ('$("input-error").hidden = true;\n  state.busy = true;', '$("input-error").hidden = true;\n  const scope = readScope();\n  state.busy = true;'),
        ('body: JSON.stringify({ question })', 'body: JSON.stringify({ question, scope })'),
        ('const entry = { id: ++historySequence, question, result };', 'const effectiveScope = result.ui_scope?.effective || scope;\n    restoreScope(effectiveScope);\n    const entry = { id: ++historySequence, question, result, scope: effectiveScope };'),
        ('$("question").value = ""; updateForm(); clearEvidence();', '$("question").value = ""; restoreScope(); updateForm(); clearEvidence();'),
    ]
    for old, new in changes:
        text = replace_once(text, old, new)
    return text


def handler_for(backend, root=ROOT):
    base = previous_handler(backend, root)
    lock = Lock()
    # Validate all anchors at startup rather than breaking a user's first request.
    app = scoped_app((root/'web/app.mjs').read_text(encoding='utf-8')).encode('utf-8')
    controls = (root/'web/scope-controls.html').read_text(encoding='utf-8')
    class Handler(base):
        def content(self, data, kind):
            if kind.startswith('text/html'):
                html = data.decode('utf-8')
                html = replace_once(html, '<label for="question">', controls + '\n      <label for="question">')
                html = replace_once(html, '</head>', '<link rel="stylesheet" href="/scope.css">\n</head>')
                data = html.encode('utf-8')
            return super().content(data, kind)

        def do_GET(self):
            if not self.local_host():
                return self.send_json(403, {'error': 'Local host only'})
            path = urlsplit(self.path).path
            if path == '/app.mjs':
                return self.content(app, 'text/javascript; charset=utf-8')
            if path in ('/scope-controls.mjs', '/scope.css'):
                kind = 'text/css' if path.endswith('.css') else 'text/javascript'
                return self.content((root/'web'/path[1:]).read_bytes(), kind + '; charset=utf-8')
            return super().do_GET()

        def do_POST(self):
            if not self.local_host():
                return self.send_json(403, {'error': 'Local host only'})
            origin = self.headers.get('Origin')
            if origin and origin != 'http://' + self.headers.get('Host', ''):
                return self.send_json(403, {'error': 'Same-origin requests only'})
            if self.path != '/ask':
                return self.send_json(404, {'error': 'Unknown route'})
            if self.headers.get_content_type() != 'application/json':
                return self.send_json(415, {'error': 'Use application/json'})
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 16384:
                    raise ValueError('Invalid request size')
                payload = json.loads(self.rfile.read(length))
                if not isinstance(payload, dict) or 'question' not in payload or set(payload) - {'question', 'scope', 'previous_question'}:
                    raise ValueError('Expected question and optional scope')
                query, followup_notes = followup(payload['question'], payload.get('previous_question'))
                scope = resolve_scope(query, payload.get('scope'))
                scope['notes'] = followup_notes + scope['notes']
                with lock:
                    result = backend.answer(scope['effective_question'])
                result = {**result, 'question': payload['question'].strip(),
                          'effective_question': scope['effective_question'], 'ui_scope': scope}
                if result.get('presentation'):
                    prose = result['presentation']
                    rendered = '\n\n'.join(p['text'] + ''.join(
                        f" [{s['document_title']}, PDF page {s['pdf_page']}]" for s in p['citations'])
                        for p in prose['paragraphs'])
                    rendered += '\n\n' + '\n'.join(dict.fromkeys(prose.get('important_notes',[])+prose['qualifications']))
                else:
                    rendered = display(result)
                scope_text = 'Question scope: ' + scope['summary']
                if scope['notes']:
                    scope_text += '\n' + '\n'.join(scope['notes'])
                self.send_json(200, {**result, 'display_text': scope_text + '\n\n' + rendered})
            except (ValueError, UnicodeDecodeError) as error:
                self.send_json(400, {'error': str(error)})
            except Exception:
                self.send_json(503, {'error': 'Backend unavailable; see local diagnostics and retry.'})
    return Handler
