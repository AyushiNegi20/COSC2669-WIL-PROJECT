"""One maintained demo entry point for the bounded release candidate."""
import argparse
from http.server import ThreadingHTTPServer
import socket
from answer_bank_conversational import Backend
from serve_fintrace_conversational import handler_for
from bank_integrity import verify


class ExclusiveLocalServer(ThreadingHTTPServer):
    """Do not let a second Windows process silently share the demo port."""
    allow_reuse_address = False

    def server_bind(self):
        if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--port', type=int, default=8770)
    parser.add_argument('--provider', choices=('ollama', 'groq'), default='ollama')
    parser.add_argument('--confirm-free-plan', action='store_true')
    args = parser.parse_args()
    if not verify()['unchanged']: raise RuntimeError('Frozen source foundation changed')
    backend = Backend()
    if args.provider == 'groq':
        from bank_groq import configure_backend
        backend = configure_backend(backend, free_plan_confirmed=args.confirm_free_plan)
        print('Experimental Groq mode: selected public-report excerpts leave this laptop; session quota caps apply.', flush=True)
    server = ExclusiveLocalServer(('127.0.0.1', args.port), handler_for(backend))
    print(f'FinTrace release candidate: http://127.0.0.1:{args.port}/', flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()
