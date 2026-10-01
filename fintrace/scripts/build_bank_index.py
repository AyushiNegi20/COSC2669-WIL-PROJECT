"""Build exact local vector indexes, with no truncation and no answer-key input."""
import gc
import hashlib
import json
from time import perf_counter
import numpy as np
from bank_retrieval import (ROOT, BASE, CONFIG, REPORTS, read, save, sha, canonical, build_corpora,
                            tokenizer_for, Encoder, execution_profile)


def main():
    config = read(ROOT / CONFIG)
    profile = execution_profile()
    corpora, _, _, _ = build_corpora(config['mode'])
    BASE.mkdir(parents=True, exist_ok=True)
    report = {'mode': config['mode'], 'chunk_release': config['chunk_release'],
              'chunk_release_sha256': sha(ROOT / config['chunk_release']),
              'configuration_sha256': sha(ROOT / CONFIG), 'models': {}, 'indexes': {}}
    for name in ('bge', 'qwen'):
        tokenizer = tokenizer_for(name)
        tokenizer.model_max_length = 10**9  # Suppress warning only; explicit limits checked below.
        audit = {}
        for kind, records in corpora.items():
            lengths = [len(tokenizer.encode(r['search_text'], truncation=False)) for r in records]
            audit[kind] = {'count': len(records), 'maximum_tokens': max(lengths),
                           'overflow_ids': [r['chunk_id'] for r, n in zip(records, lengths)
                                            if n > config['models'][name]['limit']]}
        eligible = any(not a['overflow_ids'] for a in audit.values())
        report['models'][name] = {'specification': config['models'][name], 'audit': audit,
                                  'eligible_corpora': [kind for kind,a in audit.items() if not a['overflow_ids']],
                                  'reason': 'Only complete fitting corpora are indexed; no truncation or selective omission permitted'}
        if not eligible:
            print(f'{name}: excluded because complete corpus does not fit', flush=True)
            continue
        encoder = Encoder(name)
        for kind, records in corpora.items():
            if audit[kind]['overflow_ids']:
                print(f'{name}: excluding {kind} corpus due to token overflow', flush=True)
                continue
            content_hash = hashlib.sha256(canonical(records).encode()).hexdigest()
            out = BASE / f'{kind}_{name}.npz'
            meta_path = BASE / f'{kind}_{name}.json'
            reused = None
            old = None
            if out.exists() and meta_path.exists():
                old = read(meta_path)
                if (old['records_sha256'] == content_hash and old['model'] == config['models'][name]
                        and old['array_sha256'] == sha(out)
                        and old.get('execution_profile') == profile
                        and old['encoder_code_sha256'] == sha(ROOT / 'scripts/bank_retrieval.py')):
                    print(f'Reusing verified {kind} {name} index', flush=True)
                    report['indexes'][f'{kind}_{name}'] = old
                    continue
                # A pre-benchmark append-only corpus correction can reuse an
                # exactly verified prefix. Never reuse vectors for changed text.
                n = old['records']
                prefix_hash = hashlib.sha256(canonical(records[:n]).encode()).hexdigest()
                if (not (REPORTS/'development.json').exists()
                        and n < len(records) and prefix_hash == old['records_sha256']
                        and old['model'] == config['models'][name]
                        and old['array_sha256'] == sha(out)
                        and old.get('execution_profile') == profile
                        and old['encoder_code_sha256'] == sha(ROOT/'scripts/bank_retrieval.py')):
                    cached = np.load(out)
                    if list(cached['ids']) != [r['chunk_id'] for r in records[:n]]:
                        raise ValueError('Append-only prefix identity mismatch')
                    reused = cached['embeddings'].copy()
                    import shutil
                    shutil.copy2(out, BASE/f'{kind}_{name}.prefix.npz')
                    save(BASE/f'{kind}_{name}.prefix.json',old)
                    print(f'Reusing {n} verified prefix vectors; embedding {len(records)-n} appended notes',flush=True)
                else:
                    raise ValueError('Index cache differs. Preserve it and use a new output version.')
            started = perf_counter()
            pending = records[len(reused):] if reused is not None else records
            embeddings = encoder.encode([r['search_text'] for r in pending], batch_size=config['batch_size'])
            if reused is not None:
                embeddings = np.concatenate([reused,embeddings],axis=0)
            np.savez_compressed(out, embeddings=embeddings, ids=np.array([r['chunk_id'] for r in records]))
            meta = {'records_sha256': content_hash, 'model': config['models'][name],
                    'records': len(records), 'dimensions': embeddings.shape[1],
                    'embedding_seconds': perf_counter() - started, 'array_sha256': sha(out),
                    'encoder_code_sha256': sha(ROOT / 'scripts/bank_retrieval.py'),
                    'execution_profile': profile, 'truncation': False}
            if reused is not None:
                meta.update(reused_prefix_vectors=len(reused), prefix_array_sha256=old['array_sha256'],
                            prefix_embedding_seconds=old['embedding_seconds'])
            save(meta_path, meta)
            report['indexes'][f'{kind}_{name}'] = meta
        del encoder
        gc.collect()
    save(REPORTS / 'index.json', report)
    print(json.dumps(report, indent=2), flush=True)


if __name__ == '__main__':
    main()
