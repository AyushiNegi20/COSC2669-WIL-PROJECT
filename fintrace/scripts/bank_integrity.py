"""Verify the current code and local corpus without historical experiment files."""
from hashlib import sha256
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def verify(path=None, root=ROOT, data_prefixes=None):
    # path is accepted for the earlier chunk-verification caller. The current
    # manifest covers its source evidence and chunk artifacts explicitly.
    manifest=root/'releases/current.json'
    if not manifest.is_file():
        return {'unchanged':False,'errors':['Missing releases/current.json'],'quality_approved':False}
    data=json.loads(manifest.read_text(encoding='utf-8'))
    errors=[]
    for name,expected in data['files_sha256'].items():
        if name.startswith(('data/','models/')) and data_prefixes is not None and not any(name.startswith(p) for p in data_prefixes):
            continue
        target=(root/name).resolve()
        if not target.is_relative_to(root.resolve()):
            errors.append('Unsafe manifest path: '+name)
        elif not target.is_file():errors.append('Missing: '+name)
        elif sha256(target.read_bytes()).hexdigest()!=expected:errors.append('Changed: '+name)
    return {'release_id':'current','unchanged':not errors,'errors':errors,'quality_approved':False}

if __name__=='__main__':
    result=verify();print(json.dumps(result,indent=2));raise SystemExit(not result['unchanged'])
