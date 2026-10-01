"""Local demo configuration, separate from historical research candidates."""
import argparse
import json
from pathlib import Path
from answer_bank_conversational import Backend
from answer_bank_v12 import ContractSynthesisClient
from bank_generation_v11 import SynthesisClient
from bank_research_answer import ResearchClient
from bank_conversational_intent import IntentPlanner
from serve_fintrace_release import ExclusiveLocalServer
from serve_fintrace_conversational import handler_for

ROOT=Path(__file__).resolve().parents[1]

def build_backend():
    config=json.loads((ROOT/'config/demo_local8b.json').read_text(encoding='utf-8'))
    research=ResearchClient(config)
    research.ensure_available()
    backend=Backend()
    backend.intent_planner=IntentPlanner(SynthesisClient(config))
    backend.core.research_client=research
    backend.core.client=ContractSynthesisClient(config)
    return backend

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8770)
    args=parser.parse_args()
    from bank_integrity import verify
    if not verify()['unchanged']:raise RuntimeError('Retrieval checkpoint changed; inspect before demo')
    backend=build_backend()
    server=ExclusiveLocalServer(('127.0.0.1',args.port),handler_for(backend))
    print(f'FinTrace local demo: http://127.0.0.1:{args.port}/',flush=True)
    print('Qwen3 8B: source-selected narrative passages; checked definitions; Python arithmetic. No external API calls.',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()
