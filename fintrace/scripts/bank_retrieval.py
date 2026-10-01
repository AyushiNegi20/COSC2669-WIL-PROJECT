"""Local evidence retrieval. This module never reads evaluation questions or answers."""
from collections import Counter, defaultdict
import hashlib
import json
import math
import re
from time import perf_counter
import numpy as np

from build_bank_chunks import ROOT, read, save, canonical, sha

CONFIG = 'config/banking_retrieval.json'
VERSION = read(ROOT / CONFIG)['version']
BASE = ROOT / 'data/processed' / VERSION.replace('-', '_')
REPORTS = ROOT / 'reports' / VERSION.replace('-', '_')
ALIASES = {'nim': 'net interest margin', 'npat': 'net profit after tax',
           'eps': 'earnings per share', 'dps': 'dividend per share',
           'cet1': 'common equity tier 1', 'lcr': 'liquidity coverage ratio'}
STOPWORDS = set('a an the is are was were be been what which who how did does do of to for from in on at by with and or as its it their this that these those include state please according reported originally'.split())
PLURALS = {'dividends':'dividend','deposits':'deposit','assets':'asset',
           'expenses':'expense','borrowings':'borrowing','profits':'profit'}


def tokens(text, normalise=None):
    found = re.findall(r"[a-z]+[0-9]*|[0-9]+(?:[.,][0-9]+)*", text.lower())
    expanded = found + [word for token in found if token in ALIASES for word in ALIASES[token].split()]
    if normalise is None:
        normalise = read(ROOT / CONFIG).get('lexical_normalisation', True)
    if not normalise:
        return expanded
    return [PLURALS.get(word, word) for word in expanded if word not in STOPWORDS]


def clean_search_question(question):
    """Remove response-format instructions, not financial scope or claim values."""
    text = re.sub(r'\bInclude the unit and reporting basis\.?', '', question, flags=re.I)
    text = re.sub(r'\b(?:Keep each bank.s year.end and basis clear|State the change and basis|Attribute the explanation to management)\.?', '', text, flags=re.I)
    text = re.sub(r'\bDo not invent an explanation for the difference\.?', '', text, flags=re.I)
    text = re.sub(r',?\s*as originally reported', '', text, flags=re.I)
    return ' '.join(text.split())


def search_question(question):
    return clean_search_question(question) if read(ROOT/CONFIG).get('query_cleanup', True) else question


def search_representation(record, units):
    """Literal source spans for ranking; full evidence remains unchanged."""
    pieces, seen = [], set()
    for fragment in record['fragments']:
        key = (fragment['unit'], fragment['start'], fragment['end'])
        if key not in seen:
            pieces.append(units[key[0]][key[1]:key[2]])
            seen.add(key)
    return record['source']['document_title'] + '\n' + '\n'.join(pieces)


def plan_query(question):
    """Parse explicit entities, not guessed metric/basis fields or answer labels."""
    companies = []
    if re.search(r'\b(cba|commonwealth bank)\b', question, re.I):
        companies.append('CBA')
    if re.search(r'\b(nab|national australia bank)\b', question, re.I):
        companies.append('NAB')
    years = sorted(set(int(v) for v in re.findall(r'\b(?:FY\s*)?(20\d{2})\b', question, re.I)))
    original = bool(re.search(r'originally (?:reported|published)|original (?:FY\d{4} )?report', question, re.I))
    # Named report filters only; a value-year alone must not exclude comparatives.
    specific_report = bool(re.search(r'\b(?:FY\s*)?20\d{2}\s+(?:profit announcement|results report|annual report|report)\b', question, re.I))
    report_year = years[0] if len(years) == 1 and (original or specific_report) else None
    annual_only = bool(re.search(r'\bannual report\b', question, re.I))
    ambiguity = None
    if re.search(r'\bprofit\b', question, re.I) and not re.search(
            r'cash|statutory|net profit|operating profit|reconcil|difference|both', question, re.I):
        ambiguity = 'Profit is ambiguous: specify a reporting basis or show labelled alternatives.'
    return {'companies': companies, 'value_years': years, 'report_year': report_year,
            'annual_report_only': annual_only, 'ambiguity': ambiguity,
            'branches': companies or [None]}


def load_lines(path):
    return [json.loads(x) for x in path.read_text(encoding='utf-8').splitlines()]


def source_units():
    units, pages = {}, {}
    for path in sorted((ROOT / 'data/processed/banking_v1/evidence').glob('*/page_*.json')):
        page = read(path)
        pages[page['id']] = page
        for b in page['blocks']:
            if b['type'] == 'table':
                for i, row in enumerate(b['rows']):
                    units[f"{b['id']}:r{i}"] = ' | '.join(row)
            elif b.get('text'):
                units[b['id']] = b['text']
    return units, pages


def full_fragment(unit, text):
    return {'unit': unit, 'start': 0, 'end': len(text), 'length': len(text)}


def fragments(record, units):
    result = []
    anchored = set()
    for a in record['anchors']:
        anchored.add(a['evidence_id'])
        if a['type'] == 'text_span':
            result.append({'unit': a['evidence_id'], 'start': a['start'], 'end': a['end'],
                           'length': len(units[a['evidence_id']])})
        else:
            for r in sorted(set(a['rows'] + a['header_rows'] + a['context_rows'])):
                unit = f"{a['evidence_id']}:r{r}"
                result.append(full_fragment(unit, units[unit]))
    for evidence_id in record['evidence_ids']:
        if evidence_id not in anchored and evidence_id in units:
            result.append(full_fragment(evidence_id, units[evidence_id]))
    return result


def eligible_record(record, mode):
    if record['quality']['status'] == 'quarantined':
        return False
    if mode == 'validated_only' and record['quality']['status'] != 'validated':
        return False
    # Do not index isolated page headings/chart labels as independent evidence.
    if record['kind'] == 'passage':
        body = record['text'].split('\n')[-1]
        return len(re.findall(r'[A-Za-z]+', body)) >= 4
    return True


def build_corpora(mode='development_unreviewed'):
    from bank_integrity import verify
    config = read(ROOT / CONFIG)
    result = verify(ROOT / config['chunk_release'])
    if not result['unchanged']:
        raise ValueError(result['errors'])
    units, pages = source_units()
    raw = load_lines(ROOT / 'data/processed/banking_chunks_v1/children.jsonl')
    original_parents = load_lines(ROOT / 'data/processed/banking_chunks_v1/parents.jsonl')
    parents = {c['chunk_id']: {**c, 'fragments': fragments(c, units)} for c in original_parents}
    structured = [{**c, 'fragments': fragments(c, units)} for c in raw if eligible_record(c, mode)]
    # Equal evidence universe for the baseline: reconstruct literal source units
    # available in eligible children, not extra rows from quarantined parents.
    allowed = {f['unit'] for c in structured for f in c['fragments']}
    baseline = []
    for page_id, page in pages.items():
        text, spans = '', []
        for b in page['blocks']:
            keys = [f"{b['id']}:r{r}" for r in range(len(b['rows']))] if b['type'] == 'table' else [b['id']]
            for key in keys:
                if key not in allowed:
                    continue
                start = len(text)
                text += units[key]
                spans.append((key, start, len(text)))
                text += '\n'
        start = 0
        while start < len(text):
            end = min(start + 1200, len(text))
            if end < len(text):
                for boundary in ('\n\n', '\n', '. ', ' '):
                    pos = text.rfind(boundary, start + 600, end)
                    if pos >= 0:
                        end = pos + len(boundary)
                        break
            frag = []
            for key, left, right in spans:
                a, z = max(left, start), min(right, end)
                if a < z:
                    frag.append({'unit': key, 'start': a - left, 'end': z - left, 'length': right - left})
            prefix = f"{page['source']['document_title']} | PDF page {page['source']['pdf_page']}\n"
            item = {'chunk_id': f'recursive:{page_id}:{start}:{end}', 'kind': 'recursive_baseline',
                    'source': page['source'], 'text': prefix + text[start:end], 'fragments': frag,
                    'quality': {'status': 'development_unreviewed'}, 'parent_id': None,
                    'related_chunk_ids': [], 'anchors': []}
            baseline.append(item)
            if end == len(text):
                break
            start = max(start + 1, end - 150)
    # Short notes such as "Quarterly average" are meaningful despite the
    # short-label filter. Keep linked notes as searchable evidence in BOTH arms.
    linked = {key for c in structured for key in c['related_chunk_ids']}
    existing = {c['chunk_id'] for c in structured}
    for c in raw:
        if c['chunk_id'] in linked and c['chunk_id'] not in existing and c['quality']['status'] != 'quarantined':
            if mode == 'validated_only' and c['quality']['status'] != 'validated':
                continue
            note = {**c, 'fragments': fragments(c, units)}
            structured.append(note)
            baseline.append({**note, 'chunk_id':'recursive-note:'+c['chunk_id'],
                             'kind':'recursive_baseline','parent_id':None,'related_chunk_ids':[]})
    for record in structured + baseline:
        record['search_text'] = (record['text'] if config.get('search_view') == 'full_evidence'
                                 else search_representation(record, units))
    return {'structured': structured, 'recursive': baseline}, parents, {c['chunk_id']: c for c in raw}, units


class BM25:
    def __init__(self, texts, k1=1.5, b=0.75):
        self.docs = [Counter(tokens(t)) for t in texts]
        self.lengths = [sum(d.values()) for d in self.docs]
        self.average = sum(self.lengths) / max(len(self.lengths), 1)
        self.df = Counter(t for d in self.docs for t in d)
        self.k1, self.b = k1, b

    def score(self, query):
        output = np.zeros(len(self.docs), dtype=np.float32)
        for term in set(tokens(query)):
            df = self.df[term]
            if not df:
                continue
            idf = math.log(1 + (len(self.docs) - df + .5) / (df + .5))
            for i, doc in enumerate(self.docs):
                tf = doc[term]
                if tf:
                    norm = self.k1 * (1 - self.b + self.b * self.lengths[i] / max(self.average, 1))
                    output[i] += idf * tf * (self.k1 + 1) / (tf + norm)
        return output


def ranked(scores, indexes, limit):
    return sorted(indexes, key=lambda i: (-float(scores[i]), i))[:limit]


def rrf(lists, constant=60):
    scores = defaultdict(float)
    for items in lists:
        for rank, key in enumerate(items, 1):
            scores[key] += 1 / (constant + rank)
    return sorted(scores, key=lambda i: (-scores[i], i))


def covered_units(records):
    pieces = defaultdict(list)
    lengths = {}
    for rec in records:
        for f in rec['fragments']:
            pieces[f['unit']].append((f['start'], f['end']))
            lengths[f['unit']] = f['length']
    complete = set()
    for key, spans in pieces.items():
        end = 0
        for a, b in sorted(spans):
            if a > end:
                break
            end = max(end, b)
        if end >= lengths[key]:
            complete.add(key)
    return complete


def tokenizer_for(name):
    from transformers import AutoTokenizer
    config = read(ROOT / CONFIG)
    spec = config['models'][name]
    path = ROOT / 'models/retrieval' / ('models--' + spec['id'].replace('/', '--')) / 'snapshots' / spec['revision']
    return AutoTokenizer.from_pretrained(str(path), local_files_only=True, trust_remote_code=False)


def execution_profile():
    import torch
    device = read(ROOT / CONFIG).get('device', 'cpu')
    if device == 'cuda' and not torch.cuda.is_available():
        raise RuntimeError('This experiment requires CUDA. Use the retrieval environment; do not silently change devices.')
    return {'device': device, 'dtype': 'float32', 'torch': torch.__version__,
            'hardware': torch.cuda.get_device_name(0) if device == 'cuda' else 'CPU'}


class Encoder:
    def __init__(self, name):
        import torch
        from transformers import AutoModel
        self.name = name
        self.profile = execution_profile()
        self.spec = read(ROOT / CONFIG)['models'][name]
        self.tokenizer = tokenizer_for(name)
        self.tokenizer.padding_side = 'right'
        torch.set_num_threads(read(ROOT / CONFIG)['threads'])
        path = ROOT / 'models/retrieval' / ('models--' + self.spec['id'].replace('/', '--')) / 'snapshots' / self.spec['revision']
        self.model = AutoModel.from_pretrained(str(path), local_files_only=True, trust_remote_code=False, dtype=torch.float32)
        self.model.to(self.profile['device'])
        self.model.eval()

    def encode(self, texts, query=False, batch_size=8):
        import torch
        formatted = [self.spec['query_prefix'] + search_question(t) if query else t for t in texts]
        lengths = [len(self.tokenizer.encode(t, truncation=False)) for t in formatted]
        if max(lengths, default=0) > self.spec['limit']:
            raise ValueError(f'{self.name} token overflow; no truncation allowed')
        order = sorted(range(len(texts)), key=lambda i: lengths[i])
        results = [None] * len(texts)
        for offset in range(0, len(order), batch_size):
            indexes = order[offset:offset + batch_size]
            batch = self.tokenizer([formatted[i] for i in indexes], padding=True, truncation=False, return_tensors='pt')
            batch = batch.to(self.profile['device'])
            with torch.inference_mode():
                out = self.model(**batch).last_hidden_state
                if self.spec['pooling'] == 'cls':
                    pooled = out[:, 0]
                else:
                    positions = batch['attention_mask'].sum(1) - 1
                    pooled = out[torch.arange(len(indexes), device=self.profile['device']), positions]
                pooled = torch.nn.functional.normalize(pooled, p=2, dim=1).cpu().numpy()
            for i, vector in zip(indexes, pooled):
                results[i] = vector
            if offset % 128 == 0:
                print(f'{self.name}: embedded {min(offset + batch_size, len(texts))}/{len(texts)}', flush=True)
        return np.asarray(results, dtype=np.float32)


class Reranker:
    def __init__(self):
        import torch
        from transformers import AutoModelForSequenceClassification
        self.spec = read(ROOT / CONFIG)['models']['reranker']
        self.profile = execution_profile()
        self.tokenizer = tokenizer_for('reranker')
        path = ROOT / 'models/retrieval' / ('models--' + self.spec['id'].replace('/', '--')) / 'snapshots' / self.spec['revision']
        self.model = AutoModelForSequenceClassification.from_pretrained(str(path), local_files_only=True,
                         trust_remote_code=False, dtype=torch.float32).eval()
        self.model.to(self.profile['device'])
        self.cache = {}

    def score(self, query, text):
        import torch
        key = hashlib.sha256((query + '\0' + text).encode()).hexdigest()
        if key in self.cache:
            return self.cache[key]
        # Explicit window scoring, not silent truncation. All source tokens are
        # scored in overlapping windows; original evidence remains unchanged.
        qids = self.tokenizer.encode(query, add_special_tokens=False)
        ids = self.tokenizer.encode(text, add_special_tokens=False)
        capacity = self.spec['limit'] - len(qids) - self.tokenizer.num_special_tokens_to_add(pair=True)
        if capacity < 32:
            raise ValueError('Query too long for reranker')
        scores = []
        for start in range(0, len(ids), max(1, capacity - 64)):
            window = ids[start:start + capacity]
            # This pinned reranker is BERT. Construct its documented pair layout
            # explicitly; Transformers 5 no longer exposes the older helper.
            sequence = [self.tokenizer.cls_token_id] + qids + [self.tokenizer.sep_token_id] + window + [self.tokenizer.sep_token_id]
            types = [0] * (len(qids) + 2) + [1] * (len(window) + 1)
            batch = {'input_ids': torch.tensor([sequence]), 'attention_mask': torch.ones((1, len(sequence)), dtype=torch.long),
                     'token_type_ids': torch.tensor([types])}
            batch = {key: value.to(self.profile['device']) for key, value in batch.items()}
            with torch.inference_mode():
                scores.append(float(self.model(**batch).logits.squeeze()))
            if start + capacity >= len(ids):
                break
        self.cache[key] = max(scores)
        return self.cache[key]


class Retriever:
    def __init__(self, records, vectors=None, reranker=None):
        self.records, self.vectors, self.reranker = records, vectors, reranker
        self.config = read(ROOT / CONFIG)
        self.lexical = BM25([r.get('search_text', r['text']) for r in records],
                            self.config['bm25']['k1'], self.config['bm25']['b'])

    def search(self, question, method='bm25', query_vector=None, candidate_k=20, final_k=5):
        start = perf_counter()
        plan = plan_query(question)
        ranking_question = search_question(question)
        sparse = self.lexical.score(ranking_question)
        dense = self.vectors @ query_vector if query_vector is not None else None
        branches, allowed_all = [], []
        for company in plan['branches']:
            allowed = [i for i, r in enumerate(self.records) if r['quality']['status'] != 'quarantined'
                       and (company is None or r['source']['company'] == company)
                       and (plan['report_year'] is None or r['source']['report_year'] == plan['report_year'])
                       and (not plan['annual_report_only'] or '_ar' in r['source']['document_id'])]
            allowed_all.extend(allowed)
            lexical = ranked(sparse, [i for i in allowed if sparse[i] > 0], candidate_k)
            if method == 'bm25':
                order = lexical
            else:
                if dense is None:
                    raise ValueError('Dense/hybrid retrieval requires embeddings')
                semantic = ranked(dense, allowed, candidate_k)
                order = semantic if method == 'dense' else rrf([lexical, semantic], self.config['rrf_constant'])[:candidate_k]
            if method == 'hybrid_rerank':
                order = sorted(order, key=lambda i: (-self.reranker.score(ranking_question, self.records[i].get('search_text', self.records[i]['text'])), i))
            branches.append(order)
        # Round robin gives explicit company comparisons evidence from each side.
        selected = []
        for depth in range(candidate_k):
            for branch in branches:
                if depth < len(branch) and branch[depth] not in selected:
                    selected.append(branch[depth])
        return {'hits': [self.records[i] for i in selected[:final_k]],
                'candidates': [self.records[i] for i in selected], 'plan': plan,
                'search_seconds': perf_counter() - start,
                'evidence_sufficiency': 'not_established_by_retrieval_scores',
                'mode': 'development_unreviewed'}


def assemble_context(hits, parents, raw_children, units, tokenizer, budget=2048):
    """Children first, candidate notes second, parents only if budget permits.

    A universal tokenizer is used across experiment arms. Quarantine always wins.
    """
    records, omissions, seen = [], [], set()
    def add(record):
        if record['chunk_id'] in seen:
            return
        if record['quality']['status'] == 'quarantined':
            omissions.append({'id': record['chunk_id'], 'reason': 'quarantine'})
            return
        candidate = '\n\n'.join(r['text'] for r in records + [record])
        if len(tokenizer.encode(candidate, truncation=False)) > budget:
            omissions.append({'id': record['chunk_id'], 'reason': 'token_budget'})
            return
        records.append(record)
        seen.add(record['chunk_id'])
    for hit in hits:
        add(hit)
    for hit in hits:
        for key in hit.get('related_chunk_ids', []):
            note = raw_children[key]
            add({**note, 'fragments': fragments(note, units)})
    for hit in hits:
        parent = parents.get(hit.get('parent_id'))
        if parent and not covered_units([parent]).issubset(covered_units(records)):
            if parent['quality']['status'] == 'quarantined':
                omissions.append({'id':parent['chunk_id'],'reason':'quarantine'})
                continue
            parent_units = covered_units([parent])
            contained = [r for r in records if covered_units([r]) and covered_units([r]) <= parent_units]
            # Replace contained children instead of paying for duplicate source
            # text. Keep other banks, passages and notes in their original order.
            trial = []
            inserted = False
            for r in records:
                if r in contained:
                    if not inserted:
                        trial.append(parent)
                        inserted = True
                else:
                    trial.append(r)
            if not inserted:
                trial.append(parent)
            if len(tokenizer.encode('\n\n'.join(r['text'] for r in trial),truncation=False)) <= budget:
                records[:] = trial
                seen = {r['chunk_id'] for r in records}
            else:
                omissions.append({'id':parent['chunk_id'],'reason':'token_budget'})
    return {'records': records, 'omissions': omissions,
            'tokens': len(tokenizer.encode('\n\n'.join(r['text'] for r in records), truncation=False))}
