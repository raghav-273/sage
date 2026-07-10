#!/usr/bin/env python
# tests/evaluation/run_evaluation.py
"""
SAGE Evaluation Runner.

Runs the 20-question dataset against a live SAGE instance and produces:
  - A structured JSON results file
  - A human-readable summary printed to stdout
  - A CSV review sheet for manual scoring of answer correctness

Usage (from repository root, with the stack running):
    docker compose exec web python tests/evaluation/run_evaluation.py \
        --document-id <uuid> \
        [--output-dir tests/evaluation/results]

Requirements:
    - At least one READY document must exist in the running instance.
    - The document should be relevant to the 20 questions (ideally an RDSO
      track/permanent way specification — the questions are calibrated for
      that document type).
    - DJANGO_SETTINGS_MODULE must be set (handled by manage.py / Docker).

Metrics computed automatically (without manual review):
    Citation Presence     — % of answers with >= 1 validated citation
    Hallucination Rate    — % of answer sessions with any rejected citation
    Median Latency (ms)   — wall-clock time per question
    P95 Latency (ms)
    Negative Compliance   — % of negative questions (Q008, Q015, Q020)
                            correctly refused (has_valid_citations=False
                            AND retrieved_chunk_count=0)

Metrics requiring manual review (exported to CSV):
    Answer Correctness    — is the factual content of the answer correct?
    Citation Accuracy     — does the cited page/section actually say what
                            the answer claims?
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

# Bootstrap Django before importing anything that touches models/settings.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django
django.setup()

from services.generation.generation_service import generate_answer  # noqa: E402


DATASET_PATH = Path(__file__).parent / "dataset.json"
NEGATIVE_IDS = {"Q008", "Q015", "Q020"}
TARGETS = {
    "citation_presence_pct": 100.0,
    "hallucination_rate_pct": 0.0,
    "median_latency_ms": 5000,
    "p95_latency_ms": 10000,
    "negative_compliance_pct": 100.0,
}


def _check_contains(answer: str, terms: list[str]) -> bool:
    lower = answer.lower()
    return all(t.lower() in lower for t in terms) if terms else True


def _run_question(question_data: dict, document_ids: list[uuid.UUID]) -> dict:
    qid = question_data["id"]
    question = question_data["question"]
    is_negative = qid in NEGATIVE_IDS

    t_start = time.monotonic()
    try:
        result = generate_answer(query=question, document_ids=document_ids or None)
        latency_ms = int((time.monotonic() - t_start) * 1000)
        error = None
    except Exception as exc:
        latency_ms = int((time.monotonic() - t_start) * 1000)
        return {
            "id": qid,
            "question": question,
            "query_type": question_data["query_type"],
            "error": str(exc),
            "latency_ms": latency_ms,
            "is_negative": is_negative,
        }

    contains_expected = _check_contains(
        result.answer_text,
        question_data.get("expected_answer_contains") or [],
    )

    if is_negative:
        negative_correctly_refused = (
            not result.has_valid_citations and result.retrieved_chunk_count == 0
        )
    else:
        negative_correctly_refused = None

    return {
        "id": qid,
        "question": question,
        "query_type": question_data["query_type"],
        "is_negative": is_negative,
        "answer_text": result.answer_text,
        "has_valid_citations": result.has_valid_citations,
        "retrieved_chunk_count": result.retrieved_chunk_count,
        "rejected_citation_count": result.rejected_citation_count,
        "citation_count": len(result.citations),
        "citations": [
            {
                "page_number": c.page_number,
                "section_identifier": c.section_identifier,
                "excerpt": c.excerpt[:120],
                "confidence_score": c.confidence_score,
                "retrieval_method": c.retrieval_method,
            }
            for c in result.citations
        ],
        "contains_expected_terms": contains_expected,
        "negative_correctly_refused": negative_correctly_refused,
        "latency_ms": latency_ms,
        "error": None,
    }


def _compute_metrics(results: list[dict]) -> dict:
    successful = [r for r in results if r.get("error") is None]
    if not successful:
        return {}

    positives = [r for r in successful if not r["is_negative"]]
    negatives = [r for r in successful if r["is_negative"]]

    cited = [r for r in positives if r["has_valid_citations"]]
    hallucinated = [r for r in successful if r["rejected_citation_count"] > 0]
    correctly_refused = [r for r in negatives if r.get("negative_correctly_refused")]

    latencies = sorted(r["latency_ms"] for r in successful)
    n = len(latencies)
    median_latency = latencies[n // 2] if latencies else 0
    p95_latency = latencies[min(int(n * 0.95), n - 1)] if latencies else 0

    citation_presence_pct = (len(cited) / len(positives) * 100) if positives else 0.0
    hallucination_rate_pct = (len(hallucinated) / len(successful) * 100) if successful else 0.0
    negative_compliance_pct = (len(correctly_refused) / len(negatives) * 100) if negatives else 0.0

    return {
        "total_questions": len(results),
        "successful": len(successful),
        "errors": len(results) - len(successful),
        "positive_questions": len(positives),
        "negative_questions": len(negatives),
        "citation_presence_pct": round(citation_presence_pct, 1),
        "hallucination_rate_pct": round(hallucination_rate_pct, 1),
        "negative_compliance_pct": round(negative_compliance_pct, 1),
        "median_latency_ms": median_latency,
        "p95_latency_ms": p95_latency,
    }


def _print_summary(metrics: dict, results: list[dict]) -> None:
    print("\n" + "=" * 60)
    print("SAGE EVALUATION REPORT")
    print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    print(f"\nTotal questions:     {metrics.get('total_questions', 0)}")
    print(f"Successful:          {metrics.get('successful', 0)}")
    print(f"Errors:              {metrics.get('errors', 0)}")

    print("\nAUTOMATED METRICS")
    print("-" * 40)
    _metric_line("Citation Presence",       metrics.get("citation_presence_pct"), "%", TARGETS["citation_presence_pct"], higher_is_better=True)
    _metric_line("Hallucination Rate",      metrics.get("hallucination_rate_pct"), "%", TARGETS["hallucination_rate_pct"], higher_is_better=False)
    _metric_line("Negative Compliance",     metrics.get("negative_compliance_pct"), "%", TARGETS["negative_compliance_pct"], higher_is_better=True)
    _metric_line("Median Latency",          metrics.get("median_latency_ms"), "ms", TARGETS["median_latency_ms"], higher_is_better=False)
    _metric_line("P95 Latency",             metrics.get("p95_latency_ms"), "ms", TARGETS["p95_latency_ms"], higher_is_better=False)

    print("\nQUESTION BREAKDOWN")
    print("-" * 40)
    for r in results:
        if r.get("error"):
            status = "ERROR"
        elif r["is_negative"]:
            status = "REFUSED" if r.get("negative_correctly_refused") else "INCORRECT (answered a negative)"
        elif r["has_valid_citations"]:
            status = "CITED"
        elif r["retrieved_chunk_count"] > 0:
            status = "ANSWERED (no citation)"
        else:
            status = "NOT FOUND"

        latency = f"{r['latency_ms']}ms" if r.get("latency_ms") else "—"
        print(f"  {r['id']:5}  {r['query_type']:20}  {status:30}  {latency}")

    print("\nNOTE: Answer Correctness and Citation Accuracy require")
    print("manual review. See the exported CSV for the review sheet.")
    print("=" * 60 + "\n")


def _metric_line(label: str, value, unit: str, target, higher_is_better: bool) -> None:
    if value is None:
        print(f"  {label:30} —")
        return
    if higher_is_better:
        meets_target = value >= target
    else:
        meets_target = value <= target
    flag = "PASS" if meets_target else "FAIL"
    print(f"  {label:30} {value:>8}{unit}   target {'>='+str(target) if higher_is_better else '<='+str(target)}{unit}   {flag}")


def _export_csv(results: list[dict], output_path: Path) -> None:
    fieldnames = [
        "id", "query_type", "question",
        "has_valid_citations", "citation_count", "rejected_citation_count",
        "retrieved_chunk_count", "latency_ms",
        "first_citation_page", "first_citation_section",
        "answer_preview",
        # Manual review columns — leave blank; human fills in
        "answer_correct",
        "citation_accurate",
        "reviewer_notes",
    ]
    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in results:
            first_citation = r.get("citations", [{}])[0] if r.get("citations") else {}
            writer.writerow({
                "id": r["id"],
                "query_type": r["query_type"],
                "question": r["question"],
                "has_valid_citations": r.get("has_valid_citations", ""),
                "citation_count": r.get("citation_count", ""),
                "rejected_citation_count": r.get("rejected_citation_count", ""),
                "retrieved_chunk_count": r.get("retrieved_chunk_count", ""),
                "latency_ms": r.get("latency_ms", ""),
                "first_citation_page": first_citation.get("page_number", ""),
                "first_citation_section": first_citation.get("section_identifier", ""),
                "answer_preview": (r.get("answer_text", "") or "")[:200],
                "answer_correct": "",
                "citation_accurate": "",
                "reviewer_notes": "",
            })


def main() -> None:
    parser = argparse.ArgumentParser(description="SAGE Evaluation Runner")
    parser.add_argument(
        "--document-id",
        help="UUID of the READY document to evaluate against. "
             "If omitted, searches across all READY documents.",
        default=None,
    )
    parser.add_argument(
        "--output-dir",
        default="tests/evaluation/results",
        help="Directory to write JSON results and CSV review sheet.",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    document_ids: list[uuid.UUID] | None = None
    if args.document_id:
        try:
            document_ids = [uuid.UUID(args.document_id)]
        except ValueError:
            print(f"ERROR: '{args.document_id}' is not a valid UUID.", file=sys.stderr)
            sys.exit(1)

    with open(DATASET_PATH, encoding="utf-8") as f:
        dataset = json.load(f)

    print(f"Running {len(dataset)} questions...")
    if document_ids:
        print(f"Scoped to document: {document_ids[0]}")
    else:
        print("Searching across all READY documents.")
    print()

    results = []
    for i, question_data in enumerate(dataset, start=1):
        print(f"  [{i:02d}/{len(dataset)}] {question_data['id']} — {question_data['question'][:60]}...")
        result = _run_question(question_data, document_ids or [])
        results.append(result)
        status = "ok" if not result.get("error") else f"ERROR: {result['error'][:40]}"
        print(f"         {status} ({result.get('latency_ms', '—')}ms)")

    metrics = _compute_metrics(results)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_path = output_dir / f"evaluation_{timestamp}.json"
    csv_path = output_dir / f"review_sheet_{timestamp}.csv"

    with results_path.open("w", encoding="utf-8") as f:
        json.dump({"metrics": metrics, "results": results}, f, indent=2, default=str)

    _export_csv(results, csv_path)
    _print_summary(metrics, results)

    print(f"Results saved to: {results_path}")
    print(f"Review sheet:     {csv_path}\n")

    passes = [
        metrics.get("citation_presence_pct", 0) >= TARGETS["citation_presence_pct"],
        metrics.get("hallucination_rate_pct", 0) <= TARGETS["hallucination_rate_pct"],
        metrics.get("p95_latency_ms", 9999999) <= TARGETS["p95_latency_ms"],
    ]
    sys.exit(0 if all(passes) else 1)


if __name__ == "__main__":
    main()