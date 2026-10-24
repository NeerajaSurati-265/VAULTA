"""
Retrieval evaluation for the VAULTA knowledge base.

For each retrieval mode it indexes data/documents/ into a throwaway index,
asks every question in eval/questions.jsonl and checks whether the expected
document + page appears in the top-k retrieved chunks.

Metrics (overall and per question type):
  hit@k  share of questions whose expected doc+page is in the top k chunks
  MRR    mean of 1/rank of the first correct chunk (0 if not in the top k)
  ms     average retrieval time per query

Usage (from the repo root):
    python eval/run_eval.py --mode hashing
    python eval/run_eval.py --mode all
"""
import argparse
import json
import logging
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
# Allow `python eval/run_eval.py` without setting PYTHONPATH
sys.path.insert(0, str(REPO_ROOT))
# Importing rag_service builds the app's global knowledge base; point it at a
# throwaway dir in the cheapest mode so the eval never touches data/index.
os.environ["VAULTA_INDEX_DIR"] = tempfile.mkdtemp(prefix="vaulta-eval-global-")
os.environ["VAULTA_RETRIEVAL_MODE"] = "hashing"

from app.config import DOCUMENTS_DIR  # noqa: E402
from app.main_services.rag_service import LocalKnowledgeBase, RETRIEVAL_MODES  # noqa: E402

QUESTIONS_PATH = REPO_ROOT / "eval" / "questions.jsonl"
RESULTS_DIR = REPO_ROOT / "eval" / "results"
TOP_K = 5
GROUPS = ["overall", "lexical", "paraphrase", "exact"]


def load_questions():
    with open(QUESTIONS_PATH, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def summarize(rows):
    n = len(rows)
    ranks = [r["rank"] for r in rows]
    return {
        "n": n,
        "hit@1": sum(1 for r in ranks if r and r <= 1) / n,
        "hit@3": sum(1 for r in ranks if r and r <= 3) / n,
        "hit@5": sum(1 for r in ranks if r and r <= 5) / n,
        "mrr": sum(1 / r for r in ranks if r) / n,
        "ms_per_query": statistics.mean(r["ms"] for r in rows),
    }


def evaluate(mode: str) -> dict:
    questions = load_questions()
    with tempfile.TemporaryDirectory(prefix=f"vaulta-eval-{mode}-") as index_dir:
        started = time.perf_counter()
        kb = LocalKnowledgeBase(retrieval_mode=mode, index_dir=Path(index_dir), documents_dir=DOCUMENTS_DIR)
        index_seconds = time.perf_counter() - started
        status = kb.get_status()

        # One untimed query so model loading (semantic modes) is not counted as query latency
        kb.retrieve("warm-up query", top_k=TOP_K)

        rows = []
        for q in questions:
            t0 = time.perf_counter()
            results = kb.retrieve(q["question"], top_k=TOP_K)
            ms = (time.perf_counter() - t0) * 1000
            rank = next(
                (i for i, c in enumerate(results, start=1)
                 if c["doc_name"] == q["expected_doc"] and c["page_number"] == q["expected_page"]),
                None,
            )
            rows.append({
                **q,
                "rank": rank,
                "ms": round(ms, 2),
                "top": [
                    {k: c.get(k) for k in ("doc_name", "page_number", "score", "bm25_rank", "vector_rank")}
                    for c in results
                ],
            })

    summary = {"overall": summarize(rows)}
    for group in GROUPS[1:]:
        group_rows = [r for r in rows if r["type"] == group]
        if group_rows:
            summary[group] = summarize(group_rows)

    return {
        "mode": mode,
        "embed_model": status.get("embed_model"),
        "top_k": TOP_K,
        "documents": status["documents_count"],
        "chunks": status["total_chunks"],
        "index_seconds": round(index_seconds, 2),
        "summary": summary,
        "questions": rows,
    }


def markdown_table(results) -> str:
    lines = [
        "| Mode | Questions | n | hit@1 | hit@3 | hit@5 | MRR | ms/query |",
        "|------|-----------|---|-------|-------|-------|-----|----------|",
    ]
    for group in GROUPS:
        for res in results:
            s = res["summary"].get(group)
            if not s:
                continue
            lines.append(
                f"| {res['mode']} | {group} | {s['n']} | {s['hit@1']:.0%} | {s['hit@3']:.0%} | "
                f"{s['hit@5']:.0%} | {s['mrr']:.3f} | {s['ms_per_query']:.1f} |"
            )
    lines.append("")
    lines.append("| Mode | Documents | Chunks | Indexing time (s) | Embedding model |")
    lines.append("|------|-----------|--------|-------------------|-----------------|")
    for res in results:
        lines.append(
            f"| {res['mode']} | {res['documents']} | {res['chunks']} | {res['index_seconds']:.2f} | "
            f"{res['embed_model'] or '-'} |"
        )
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Evaluate VAULTA retrieval modes.")
    parser.add_argument("--mode", default="all", choices=list(RETRIEVAL_MODES) + ["all"])
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING)

    modes = list(RETRIEVAL_MODES) if args.mode == "all" else [args.mode]
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    results = []
    for mode in modes:
        res = evaluate(mode)
        (RESULTS_DIR / f"{mode}.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
        results.append(res)

    print(markdown_table(results))


if __name__ == "__main__":
    main()
