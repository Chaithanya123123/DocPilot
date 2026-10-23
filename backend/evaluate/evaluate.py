"""Lightweight evaluation for DocPilot.

Offline mode (default) measures retrieval quality directly:
    python evaluate/evaluate.py --doc <document_id> [--json report.json]

Live mode measures the full answer pipeline against a running server
(latency, grounding flags, citation resolution, abstentions):
    python evaluate/evaluate.py --doc <document_id> --live http://127.0.0.1:8000
"""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import config  # noqa: E402
from app.services.mistral_client import MistralClient  # noqa: E402
from app.services.retrieval import retrieve  # noqa: E402

DEFAULT_QUESTIONS = [
    {"question": "What limitations does the authors' method have?", "expect": "answerable"},
    {"question": "What metric improvements are reported in the experiments?", "expect": "answerable"},
    {"question": "How does the system handle citation validation?", "expect": "answerable"},
    {"question": "What is the recipe for baking sourdough bread?", "expect": "unanswerable"},
    {"question": "Who won the football world cup in 1998?", "expect": "unanswerable"},
]


def evaluate_retrieval(document_id: str, questions: list[dict]) -> dict:
    client = MistralClient()
    rows = []
    try:
        for item in questions:
            q = item["question"]
            t0 = time.perf_counter()
            evidence, best = retrieve(document_id, q, client=client)
            retrieval_ms = (time.perf_counter() - t0) * 1000

            abstained = not evidence or best < config.SUFFICIENCY_THRESHOLD
            rows.append(
                {
                    "question": q,
                    "expect": item.get("expect", "answerable"),
                    "retrieval_ms": round(retrieval_ms, 1),
                    "best_cosine": round(best, 4),
                    "n_evidence": len(evidence),
                    "abstained": abstained,
                    "top_chunk": evidence[0].chunk_id if evidence else None,
                    "top_page": evidence[0].page_number if evidence else None,
                }
            )
    finally:
        client.close()

    answerable = [r for r in rows if r["expect"] == "answerable"]
    unanswerable = [r for r in rows if r["expect"] == "unanswerable"]
    latencies = [r["retrieval_ms"] for r in rows]

    return {
        "mode": "retrieval",
        "document_id": document_id,
        "n_questions": len(rows),
        "retrieval_ms_mean": round(sum(latencies) / max(len(latencies), 1), 1),
        "retrieval_ms_max": round(max(latencies), 1) if latencies else 0,
        "answerable_with_evidence": sum(1 for r in answerable if not r["abstained"]),
        "answerable_total": len(answerable),
        "unanswerable_abstained": sum(1 for r in unanswerable if r["abstained"]),
        "unanswerable_total": len(unanswerable),
        "rows": rows,
    }


def evaluate_live(base_url: str, document_id: str, questions: list[dict]) -> dict:
    import httpx

    rows = []
    with httpx.Client(base_url=base_url.rstrip("/"), timeout=180.0) as client:
        for item in questions:
            q = item["question"]
            t0 = time.perf_counter()
            resp = client.post(
                f"/api/documents/{document_id}/questions", json={"question": q}
            )
            latency_ms = (time.perf_counter() - t0) * 1000
            row = {
                "question": q,
                "expect": item.get("expect", "answerable"),
                "latency_ms": round(latency_ms, 1),
                "http_status": resp.status_code,
            }
            if resp.status_code != 200:
                row["error"] = resp.text[:200]
                row["grounded"] = False
                row["citations_resolved"] = 0
                row["citations_total"] = 0
                rows.append(row)
                continue

            body = resp.json()
            citations = body.get("citations", [])
            resolved = 0
            for cite in citations:
                page = client.get(
                    f"/api/documents/{document_id}/pages/{cite['page_number']}"
                )
                if page.status_code != 200:
                    continue
                chunk_ids = {c["chunk_id"] for c in page.json()["chunks"]}
                if cite["chunk_id"] in chunk_ids:
                    resolved += 1
            row.update(
                {
                    "grounded": bool(body.get("grounded")),
                    "citations_total": len(citations),
                    "citations_resolved": resolved,
                    "answer_excerpt": body.get("answer", "")[:160],
                }
            )
            rows.append(row)

    answerable = [r for r in rows if r["expect"] == "answerable"]
    unanswerable = [r for r in rows if r["expect"] == "unanswerable"]
    latencies = [r["latency_ms"] for r in rows if "latency_ms" in r]
    total_cites = sum(r.get("citations_total", 0) for r in rows)
    resolved_cites = sum(r.get("citations_resolved", 0) for r in rows)

    return {
        "mode": "live",
        "document_id": document_id,
        "n_questions": len(rows),
        "latency_ms_mean": round(sum(latencies) / max(len(latencies), 1), 1),
        "latency_ms_max": round(max(latencies), 1) if latencies else 0,
        "answerable_grounded": sum(1 for r in answerable if r.get("grounded")),
        "answerable_total": len(answerable),
        "unanswerable_abstained": sum(
            1 for r in unanswerable if not r.get("grounded")
        ),
        "unanswerable_total": len(unanswerable),
        "citations_resolved": resolved_cites,
        "citations_total": total_cites,
        "rows": rows,
    }


def print_report(report: dict) -> None:
    print(f"Mode: {report['mode']}  Document: {report['document_id']}")
    if report["mode"] == "retrieval":
        print(
            f"Retrieval latency: mean {report['retrieval_ms_mean']}ms, "
            f"max {report['retrieval_ms_max']}ms"
        )
        print(
            f"Answerable with evidence: "
            f"{report['answerable_with_evidence']}/{report['answerable_total']}"
        )
        print(
            f"Unanswerable abstentions: "
            f"{report['unanswerable_abstained']}/{report['unanswerable_total']}"
        )
    else:
        print(
            f"Answer latency: mean {report['latency_ms_mean']}ms, "
            f"max {report['latency_ms_max']}ms"
        )
        print(
            f"Answerable grounded: "
            f"{report['answerable_grounded']}/{report['answerable_total']}"
        )
        print(
            f"Unanswerable abstentions: "
            f"{report['unanswerable_abstained']}/{report['unanswerable_total']}"
        )
        print(
            f"Citations resolved server-side: "
            f"{report['citations_resolved']}/{report['citations_total']}"
        )
    print()
    for r in report["rows"]:
        if report["mode"] == "retrieval":
            flag = "ABSTAIN" if r["abstained"] else "HIT    "
            print(
                f"[{flag}] cos={r['best_cosine']:.3f} {r['retrieval_ms']:7.1f}ms "
                f"({r['expect']}) {r['question']}"
            )
        else:
            flag = "GROUNDED" if r.get("grounded") else "ABSTAIN "
            print(
                f"[{flag}] {r.get('latency_ms', 0):7.1f}ms "
                f"cites={r.get('citations_resolved', 0)}/{r.get('citations_total', 0)} "
                f"({r['expect']}) {r['question']}"
            )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--doc", required=True, help="document_id to evaluate")
    parser.add_argument("--questions", default=None, help="optional JSON question file")
    parser.add_argument("--json", default=None, help="write full report to this path")
    parser.add_argument(
        "--live",
        default=None,
        metavar="URL",
        help="query a running server (e.g. http://127.0.0.1:8000) instead of "
        "calling retrieval directly",
    )
    args = parser.parse_args()

    questions = DEFAULT_QUESTIONS
    if args.questions:
        questions = json.loads(Path(args.questions).read_text(encoding="utf-8"))

    report = (
        evaluate_live(args.live, args.doc, questions)
        if args.live
        else evaluate_retrieval(args.doc, questions)
    )
    print_report(report)

    if args.json:
        Path(args.json).write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"\nreport written to {args.json}")


if __name__ == "__main__":
    main()
