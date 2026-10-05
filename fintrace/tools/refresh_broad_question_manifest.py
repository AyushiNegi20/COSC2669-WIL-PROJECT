"""Refresh only reviewed runtime files; reject unrelated integrity changes."""
from hashlib import sha256
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
REVIEWED={'scripts/bank_source_cells.py','scripts/bank_broad_questions.py',
          'scripts/answer_bank_conversational.py','scripts/bank_conversation.py',
          'scripts/answer_bank_v12.py','scripts/bank_contract_v12.py'}


def main():
    path=ROOT/'releases/current.json'
    manifest=json.loads(path.read_text(encoding='utf-8'))
    for name,expected in manifest['files_sha256'].items():
        actual=sha256((ROOT/name).read_bytes()).hexdigest()
        if actual!=expected and name not in REVIEWED:
            raise ValueError('Unreviewed integrity change: '+name)
    for name in sorted(REVIEWED):
        manifest['files_sha256'][name]=sha256((ROOT/name).read_bytes()).hexdigest()
    manifest['local_revision']='5 October 2026 broad financial question update: source-bound EPS alternatives, explicit income/loan/margin interpretations and retained scope/version safeguards. Developer regression rehearsal, not fresh independent quality approval.'
    path.write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8',newline='\n')
    pointer=ROOT/'config/setup_artifacts.json'
    setup=json.loads(pointer.read_text(encoding='utf-8'))
    setup['manifest_sha256']=sha256(path.read_bytes()).hexdigest()
    pointer.write_text(json.dumps(setup,indent=2)+'\n',encoding='utf-8',newline='\n')
    print('Updated reviewed code hashes; all evidence and model hashes unchanged.')


if __name__=='__main__':main()
