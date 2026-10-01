"""Measured retrieval comparison, kept outside runtime retrieval code."""
import argparse
from collections import Counter, defaultdict
import gc
import hashlib
import json
import math
from time import perf_counter
import numpy as np

from bank_retrieval import (ROOT, BASE, CONFIG, REPORTS, read, save, sha, canonical, build_corpora,
                            covered_units, Retriever, Encoder, Reranker, tokenizer_for, assemble_context, execution_profile)

EVAL = ROOT / 'eval/banking_retrieval_v1'


def check_seal():
    manifest = read(EVAL / 'manifest.json')
    if any(sha(EVAL / name) != digest for name, digest in manifest['sha256'].items()):
        raise ValueError('Sealed evaluation files changed')


def evidence_scores(question, records):
    groups = question['required_evidence_groups']
    if not groups:
        return {'hit': None, 'mrr': None, 'evidence_recall': None, 'complete': None}
    available = covered_units(records)
    relevant = {u for group in groups for alt in group['alternatives'] for u in alt}
    first = next((i for i, r in enumerate(records, 1) if covered_units([r]) & relevant), None)
    satisfied = [any(set(alt) <= available for alt in g['alternatives']) for g in groups]
    return {'hit': int(first is not None), 'mrr': 1/first if first else 0,
            'evidence_recall': sum(satisfied)/len(groups), 'complete': int(all(satisfied))}


def ndcg(question, records, universe, k=5):
    """Binary unit-overlap relevance; report separately from complete evidence."""
    relevant = {u for g in question['required_evidence_groups'] for alt in g['alternatives'] for u in alt}
    if not relevant:
        return None
    positives = sum(bool(covered_units([r]) & relevant) for r in universe)
    dcg = sum(1/math.log2(rank+1) for rank, r in enumerate(records[:k], 1) if covered_units([r]) & relevant)
    ideal = sum(1/math.log2(rank+1) for rank in range(1, min(k, positives)+1))
    return dcg/ideal if ideal else 0


def query_vectors(questions, model='qwen'):
    keys = [q['question'] for q in questions]
    profile = execution_profile()
    spec = read(ROOT / CONFIG)['models'][model]
    code_hash = sha(ROOT / 'scripts/bank_retrieval.py')
    identity = hashlib.sha256(canonical({'questions':keys, 'model':spec,
                'execution_profile':profile, 'encoder_code_sha256':code_hash}).encode()).hexdigest()
    path = BASE / f'queries_{model}_{identity[:16]}.npz'
    meta = path.with_suffix('.json')
    if path.exists() and meta.exists():
        info = read(meta)
        if (info['array_sha256'] != sha(path) or info['model'] != spec
                or info.get('execution_profile') != profile or info.get('encoder_code_sha256') != code_hash):
            raise ValueError('Query embedding cache changed')
        return np.load(path)['embeddings'], info['seconds_per_question']
    started = perf_counter()
    encoder = Encoder(model)
    loaded = perf_counter()
    matrix = encoder.encode(keys, query=True)
    seconds = (perf_counter() - loaded)/len(keys)
    np.savez_compressed(path, embeddings=matrix)
    save(meta, {'array_sha256':sha(path), 'query_list_sha256':identity,
                'model': spec, 'execution_profile':profile, 'encoder_code_sha256':code_hash,
                'seconds_per_question':seconds,
                'model_load_seconds':loaded-started, 'truncation':False})
    del encoder
    gc.collect()
    return matrix, seconds


def average(rows, key):
    values = [r[key] for r in rows if r[key] is not None]
    return sum(values)/len(values) if values else None


def summary(rows):
    positives = [r for r in rows if r['top5']['complete'] is not None]
    return {'questions':len(rows), 'answerable_questions':len(positives),
            'hit_at_5':average([r['top5'] for r in positives], 'hit'),
            'mrr_at_5':average([r['top5'] for r in positives], 'mrr'),
            'ndcg_at_5':average(positives,'ndcg_at_5'),
            'complete_at_5':average([r['top5'] for r in positives], 'complete'),
            'evidence_recall_at_5':average([r['top5'] for r in positives], 'evidence_recall'),
            'context_complete':average([r['context'] for r in positives], 'complete'),
            'context_evidence_recall':average([r['context'] for r in positives], 'evidence_recall'),
            'mean_search_seconds':average(rows,'search_seconds'),
            'mean_context_tokens':average(rows,'context_tokens'),
            'quarantined_hits':sum(r['quarantined_hits'] for r in rows),
            'wrong_explicit_company_hits':sum(r['wrong_explicit_company_hits'] for r in rows)}


def choose(summaries):
    complexity = {'bm25':0,'dense':1,'hybrid':2,'hybrid_rerank':3}
    return min(summaries, key=lambda k: (-summaries[k]['context_complete'],
                -summaries[k]['context_evidence_recall'], -summaries[k]['mrr_at_5'],
                complexity[k.split(':')[1].removeprefix('bge_')], summaries[k]['mean_search_seconds']))


def run(phase):
    check_seal()
    output = REPORTS / f'{phase}.json'
    if output.exists():
        raise FileExistsError('This phase has already been scored. Preserve it; use a new experiment version for changes.')
    if phase == 'reserved' and not (REPORTS / 'selection.json').exists():
        raise ValueError('Select configuration on development before reading reserved questions')
    config = read(ROOT / CONFIG)
    questions = read(EVAL / f'{phase}.json')
    corpora, parents, raw, units = build_corpora(config['mode'])
    vectors = {}
    index_report = read(REPORTS / 'index.json')
    if index_report['configuration_sha256'] != sha(ROOT / CONFIG):
        raise ValueError('Index configuration changed')
    for index_name in index_report['indexes']:
        kind,model=index_name.rsplit('_',1)
        records=corpora[kind]
        index = np.load(BASE / f'{index_name}.npz')
        meta = read(BASE / f'{index_name}.json')
        if (meta.get('execution_profile') != execution_profile()
                or meta['encoder_code_sha256'] != sha(ROOT/'scripts/bank_retrieval.py')
                or meta['model'] != config['models'][model]):
            raise ValueError('Index encoder profile changed')
        if list(index['ids']) != [r['chunk_id'] for r in records]:
            raise ValueError('Vector IDs do not match live corpus')
        if meta['array_sha256'] != sha(BASE / f'{index_name}.npz') or meta['records_sha256'] != hashlib.sha256(canonical(records).encode()).hexdigest():
            raise ValueError('Stale vector index')
        vectors[(kind,model)] = index['embeddings']
    tokenizer = tokenizer_for('qwen')
    arms = [(kind, method) for kind in corpora for method in ('bm25','dense','hybrid','hybrid_rerank')]
    arms += [(kind,'bge_'+method) for kind in corpora if (kind,'bge') in vectors
             for method in ('dense','hybrid','hybrid_rerank')]
    if phase == 'reserved':
        selection = read(REPORTS / 'selection.json')
        if selection['configuration_sha256'] != sha(ROOT / CONFIG) or selection['retrieval_code_sha256'] != sha(ROOT / 'scripts/bank_retrieval.py'):
            raise ValueError('Runtime changed after development selection')
        arms = [tuple(selection['selected'].split(':')), ('recursive','bm25'), ('structured','bm25')]
        arms = list(dict.fromkeys(arms))
    needed_models = {'bge' if method.startswith('bge_') else 'qwen' for _,method in arms if method!='bm25'}
    query_embeddings, query_seconds = {}, {}
    for model in sorted(needed_models):
        query_embeddings[model],query_seconds[model]=query_vectors(questions,model)
    reranker = Reranker() if any(m.endswith('hybrid_rerank') for _,m in arms) else None
    all_rows, summaries = {}, {}
    for kind, method in arms:
        model = 'bge' if method.startswith('bge_') else 'qwen'
        engine = Retriever(corpora[kind], vectors.get((kind,model)), reranker)
        rows = []
        name = f'{kind}:{method}'
        print(f'Evaluating {phase} {name}', flush=True)
        for i,q in enumerate(questions):
            qvec = query_embeddings[model][i] if method!='bm25' else None
            out = engine.search(q['question'], method.removeprefix('bge_'), qvec, config['candidate_k'], config['final_k'])
            context = assemble_context(out['hits'], parents, raw, units, tokenizer, config['context_tokens'])
            rows.append({'question_id':q['id'], 'capability':q['capability'], 'expected_behavior':q['expected_behavior'],
                         'top5':evidence_scores(q,out['hits']), 'context':evidence_scores(q,context['records']),
                         'ndcg_at_5':ndcg(q,out['hits'],corpora[kind]),
                         'hit_ids':[r['chunk_id'] for r in out['hits']],
                         'context_ids':[r['chunk_id'] for r in context['records']],
                         'context_omissions':context['omissions'], 'context_tokens':context['tokens'],
                         'search_seconds':out['search_seconds'],
                         'quarantined_hits':sum(r['quality']['status']=='quarantined' for r in out['hits']),
                         'wrong_explicit_company_hits':sum(bool(out['plan']['companies']) and r['source']['company'] not in out['plan']['companies'] for r in out['hits']),
                         'query_plan':out['plan']})
            if i % 10 == 0:
                print(f'  {i+1}/{len(questions)}',flush=True)
        all_rows[name] = rows
        summaries[name] = summary(rows)
        print(json.dumps({name:summaries[name]},indent=2),flush=True)
    report = {'phase':phase, 'status':'measured_AI_candidate_evaluation_not_independent_validation',
              'mode':config['mode'], 'summaries':summaries, 'results':all_rows,
              'question_file_sha256':sha(EVAL/f'{phase}.json'), 'evaluation_manifest_sha256':sha(EVAL/'manifest.json'),
              'configuration_sha256':sha(ROOT/CONFIG), 'retrieval_code_sha256':sha(ROOT/'scripts/bank_retrieval.py'),
              'query_embedding_seconds_per_question_batch_average':query_seconds,
              'latency_note':'Search excludes model loading, query encoding and context assembly. Rerank cache is shared across arms. Not a production end-to-end latency benchmark.',
              'ndcg_note':'Binary source-unit overlap judgements; header-only overlap can be relevant. Complete-evidence coverage is the stricter primary criterion.',
              'unanswerable_note':'Non-answerable cases are excluded from ranking averages. Retrieval similarity does not establish answerability.',
              'by_capability':{arm:{cap:summary([r for r in rows if r['capability']==cap]) for cap in sorted({r['capability'] for r in rows})} for arm,rows in all_rows.items()}}
    save(output,report)
    if phase == 'development':
        winner = choose(summaries)
        save(REPORTS/'selection.json', {'selected':winner,
             'selection_policy':config['selection_policy'], 'development_report_sha256':sha(output),
             'configuration_sha256':sha(ROOT/CONFIG), 'retrieval_code_sha256':sha(ROOT/'scripts/bank_retrieval.py'),
             'reserved_file_sha256':sha(EVAL/'reserved.json'), 'independent_review':'pending',
             'selection_scope':'This candidate question set and evidence universe only; not best possible retrieval.'})
        print('Selected on development: '+winner,flush=True)
    return report


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--phase',choices=['development','reserved'],required=True)
    run(parser.parse_args().phase)
