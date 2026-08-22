"""Reproduce a small, auditable part of the Walert evaluation.

This script intentionally uses only the Python standard library. It:

1. rebuilds a BM25 index from Walert's public FAQ passages;
2. retrieves passages for all Walert questions;
3. evaluates the new run and Walert's supplied runs with the supplied qrels; and
4. audits refusal rates in Walert's supplied Falcon answer files.

It does not rerun Falcon-7B or the original Pyserini dense index. Those stages
have substantial legacy/runtime requirements and are treated as supplied
research artifacts in this preliminary reproduction.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Callable, Iterable


EVALUATOR_VERSION = "1.0.0"
TOKEN_RE = re.compile(r"[a-z0-9]+")
KNOWN_TOPICS = {f"W{i:02d}" for i in range(1, 21)} | {"W39"}
INFERRED_TOPICS = {f"W{i:02d}" for i in range(21, 33)}
OUT_OF_KB_TOPICS = {f"W{i:02d}" for i in range(33, 39)} | {
    "W40",
    "W41",
    "W42",
    "W43",
}


def increase_csv_limit() -> None:
    limit = sys.maxsize
    while True:
        try:
            csv.field_size_limit(limit)
            return
        except OverflowError:
            limit //= 10


def topic_id(question_id: str) -> str:
    match = re.match(r"^(W\d+)", question_id)
    if not match:
        raise ValueError(f"Cannot extract topic from question ID: {question_id}")
    raw = match.group(1)
    return f"W{int(raw[1:]):02d}"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def read_qrels(path: Path) -> dict[str, dict[str, int]]:
    qrels: dict[str, dict[str, int]] = defaultdict(dict)
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            fields = line.split()
            if not fields:
                continue
            if len(fields) != 4:
                raise ValueError(f"Malformed qrels line {line_number}: {line!r}")
            query, _, document, relevance = fields
            qrels[query][document] = int(relevance)
    return dict(qrels)


def read_trec_run(path: Path) -> dict[str, list[str]]:
    ranked: dict[str, list[tuple[int, str]]] = defaultdict(list)
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            fields = line.split()
            if not fields:
                continue
            if len(fields) != 6:
                raise ValueError(f"Malformed run line {line_number}: {line!r}")
            query, _, document, rank, _, _ = fields
            ranked[query].append((int(rank), document))
    return {
        query: [document for _, document in sorted(items)]
        for query, items in ranked.items()
    }


def dcg(relevances: Iterable[int]) -> float:
    return sum(rel / math.log2(rank + 1) for rank, rel in enumerate(relevances, 1))


def per_query_metrics(
    judgments: dict[str, int], ranking: list[str], cutoffs: tuple[int, ...]
) -> dict[str, float]:
    relevant_ranks = [
        rank for rank, document in enumerate(ranking, 1) if judgments.get(document, 0) > 0
    ]
    result = {"mrr": 1.0 / relevant_ranks[0] if relevant_ranks else 0.0}
    ideal = sorted(judgments.values(), reverse=True)
    for cutoff in cutoffs:
        observed = [judgments.get(document, 0) for document in ranking[:cutoff]]
        denominator = dcg(ideal[:cutoff])
        result[f"ndcg@{cutoff}"] = dcg(observed) / denominator if denominator else 0.0
        result[f"hit@{cutoff}"] = float(any(value > 0 for value in observed))
    return result


def aggregate_metrics(
    qrels: dict[str, dict[str, int]],
    run: dict[str, list[str]],
    selector: Callable[[str], bool],
    cutoffs: tuple[int, ...] = (1, 3, 5),
) -> dict[str, float | int]:
    query_ids = sorted(query for query in qrels if selector(query))
    rows = [per_query_metrics(qrels[query], run.get(query, []), cutoffs) for query in query_ids]
    metric_names = rows[0].keys() if rows else []
    aggregate: dict[str, float | int] = {
        "questions": len(query_ids),
        "queries_with_results": sum(bool(run.get(query)) for query in query_ids),
    }
    for metric in metric_names:
        aggregate[metric] = round(sum(row[metric] for row in rows) / len(rows), 6)
    return aggregate


def tokenize(text: str) -> list[str]:
    return TOKEN_RE.findall(text.lower())


def build_bm25_run(
    collection_rows: list[dict[str, str]],
    topic_rows: list[dict[str, str]],
    k1: float = 0.9,
    b: float = 0.4,
    max_hits: int = 100,
) -> tuple[dict[str, list[str]], float]:
    documents: list[tuple[str, Counter[str]]] = []
    document_frequency: Counter[str] = Counter()
    lengths: list[int] = []

    for row in collection_rows:
        document_id = row.get("passage_id") or row.get("id")
        content = row.get("passage") or row.get("contents")
        if not document_id or content is None:
            raise ValueError("collection.csv must contain passage_id/passage columns")
        terms = Counter(tokenize(content))
        documents.append((document_id, terms))
        lengths.append(sum(terms.values()))
        document_frequency.update(terms.keys())

    document_count = len(documents)
    average_length = sum(lengths) / document_count
    idf = {
        term: math.log(1 + (document_count - frequency + 0.5) / (frequency + 0.5))
        for term, frequency in document_frequency.items()
    }

    started = time.perf_counter()
    run: dict[str, list[str]] = {}
    for row in topic_rows:
        query_id = row["question_id"]
        query_terms = Counter(tokenize(row["question"]))
        scores: list[tuple[float, str]] = []
        for (document_id, frequencies), length in zip(documents, lengths):
            score = 0.0
            normalizer = k1 * (1 - b + b * length / average_length)
            for term, query_frequency in query_terms.items():
                frequency = frequencies.get(term, 0)
                if frequency:
                    score += (
                        idf[term]
                        * (frequency * (k1 + 1) / (frequency + normalizer))
                        * query_frequency
                    )
            if score > 0:
                scores.append((score, document_id))
        scores.sort(key=lambda item: (-item[0], item[1]))
        run[query_id] = [document_id for _, document_id in scores[:max_hits]]
    elapsed = time.perf_counter() - started
    return run, elapsed


def write_trec_run(path: Path, run: dict[str, list[str]], tag: str) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for query in sorted(run):
            for rank, document in enumerate(run[query], start=1):
                score = 1.0 / rank
                handle.write(f"{query} Q0 {document} {rank} {score:.8f} {tag}\n")


def unanswered_audit(
    topic_rows: list[dict[str, str]],
    intent_rows: list[dict[str, str]],
    summary_files: dict[str, Path],
) -> list[dict[str, float | int | str]]:
    question_to_id = {row["question"]: row["question_id"] for row in topic_rows}
    out_ids = {
        row["question_id"]
        for row in topic_rows
        if topic_id(row["question_id"]) in OUT_OF_KB_TOPICS
    }
    results: list[dict[str, float | int | str]] = []

    intent_by_id = {
        question_to_id[row["question"]]: row
        for row in intent_rows
        if row.get("question") in question_to_id
    }
    evaluated = sorted(out_ids & intent_by_id.keys())
    refusals = sum(
        intent_by_id[query].get("actual", "") == "AMAZON.FallbackIntent"
        for query in evaluated
    )
    results.append(
        {
            "system": "walert_intent_supplied",
            "context_k": 1,
            "out_of_kb_total": len(out_ids),
            "evaluated": len(evaluated),
            "refusals": refusals,
            "unanswered_rate": round(refusals / len(evaluated), 6) if evaluated else 0.0,
        }
    )

    for system, path in summary_files.items():
        rows = read_csv(path)
        by_id = {row["question_id"]: row for row in rows}
        evaluated_ids = sorted(out_ids & by_id.keys())
        for context_k in (1, 3, 5):
            field = f"top{context_k}_na"
            refusal_count = sum(
                by_id[query].get(field, "").strip().lower() == "true"
                for query in evaluated_ids
            )
            results.append(
                {
                    "system": system,
                    "context_k": context_k,
                    "out_of_kb_total": len(out_ids),
                    "evaluated": len(evaluated_ids),
                    "refusals": refusal_count,
                    "unanswered_rate": round(refusal_count / len(evaluated_ids), 6)
                    if evaluated_ids
                    else 0.0,
                }
            )
    return results


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_retrieval_csv(path: Path, retrieval: dict[str, dict[str, dict]]) -> None:
    fields = [
        "subset",
        "system",
        "questions",
        "queries_with_results",
        "mrr",
        "ndcg@1",
        "ndcg@3",
        "ndcg@5",
        "hit@1",
        "hit@3",
        "hit@5",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for subset, systems in retrieval.items():
            for system, values in systems.items():
                writer.writerow({"subset": subset, "system": system, **values})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--walert-root",
        type=Path,
        required=True,
        help="Path to the cloned rmit-ir/walert repository",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parent / "results",
    )
    parser.add_argument("--upstream-commit", default="unknown")
    args = parser.parse_args()
    increase_csv_limit()

    quantitative = args.walert_root.resolve() / "quantitative_eval"
    data_dir = quantitative / "data"
    target_dir = quantitative / "target"
    required = {
        "topics": data_dir / "topics.csv",
        "collection": data_dir / "collection.csv",
        "qrels": data_dir / "qrels.txt",
        "intent_results": data_dir / "walert_intent_results.csv",
        "intent_run": target_dir / "runs" / "walert-intent.txt",
        "bm25_run": target_dir / "runs" / "rag-bm25.txt",
        "dense_run": target_dir / "runs" / "rag-dense-faiss.txt",
        "bm25_answers": target_dir / "summaries" / "falcon_bm25_eval.csv",
        "dense_answers": target_dir / "summaries" / "falcon_dense_eval.csv",
    }
    missing = [str(path) for path in required.values() if not path.is_file()]
    if missing:
        raise FileNotFoundError("Missing Walert artifacts:\n" + "\n".join(missing))

    topic_rows = read_csv(required["topics"])
    collection_rows = read_csv(required["collection"])
    qrels = read_qrels(required["qrels"])

    reproduced_bm25, elapsed = build_bm25_run(collection_rows, topic_rows)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    reproduced_run_path = args.output_dir / "reproduced_bm25.trec"
    write_trec_run(reproduced_run_path, reproduced_bm25, "fintrace.walert.bm25")

    runs = {
        "reproduced_bm25_stdlib": reproduced_bm25,
        "walert_bm25_supplied": read_trec_run(required["bm25_run"]),
        "walert_dense_supplied": read_trec_run(required["dense_run"]),
        "walert_intent_supplied": read_trec_run(required["intent_run"]),
    }
    selectors: dict[str, Callable[[str], bool]] = {
        "known": lambda query: topic_id(query) in KNOWN_TOPICS,
        "inferred": lambda query: topic_id(query) in INFERRED_TOPICS,
        "all_answerable": lambda query: topic_id(query)
        in (KNOWN_TOPICS | INFERRED_TOPICS),
    }
    retrieval = {
        subset: {
            system: aggregate_metrics(qrels, run, selector)
            for system, run in runs.items()
        }
        for subset, selector in selectors.items()
    }
    refusal = unanswered_audit(
        topic_rows,
        read_csv(required["intent_results"]),
        {
            "walert_bm25_falcon_supplied": required["bm25_answers"],
            "walert_dense_falcon_supplied": required["dense_answers"],
        },
    )

    result = {
        "evaluation_version": EVALUATOR_VERSION,
        "upstream": {
            "repository": "https://github.com/rmit-ir/walert",
            "commit": args.upstream_commit,
        },
        "dataset": {
            "passages": len(collection_rows),
            "questions": len(topic_rows),
            "topics": len({topic_id(row["question_id"]) for row in topic_rows}),
            "known_questions": sum(
                topic_id(row["question_id"]) in KNOWN_TOPICS for row in topic_rows
            ),
            "inferred_questions": sum(
                topic_id(row["question_id"]) in INFERRED_TOPICS for row in topic_rows
            ),
            "out_of_kb_questions": sum(
                topic_id(row["question_id"]) in OUT_OF_KB_TOPICS for row in topic_rows
            ),
        },
        "reproduced_bm25": {
            "implementation": "Python standard library",
            "k1": 0.9,
            "b": 0.4,
            "max_hits": 100,
            "retrieval_seconds": round(elapsed, 6),
            "mean_milliseconds_per_question": round(elapsed * 1000 / len(topic_rows), 6),
        },
        "retrieval": retrieval,
        "out_of_kb_refusal_audit": refusal,
        "input_sha256": {name: sha256(path) for name, path in required.items()},
        "limitations": [
            "The new run reproduces the BM25 retrieval idea, not Pyserini's exact Lucene analyzer.",
            "Dense retrieval and Falcon generation are audited from Walert's supplied run files; they are not re-executed here.",
            "NDCG uses linear graded relevance and log2 rank discount, matching conventional TREC evaluation.",
            "A refusal can be appropriate for out-of-KB questions, but refusal rate alone does not measure answer correctness.",
        ],
    }

    json_path = args.output_dir / "walert_reproduction.json"
    json_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    write_retrieval_csv(args.output_dir / "retrieval_metrics.csv", retrieval)

    print(json.dumps({"dataset": result["dataset"], "retrieval": retrieval, "refusal": refusal}, indent=2))
    print(f"\nSaved {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
