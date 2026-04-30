#!/usr/bin/env python3

import argparse
import json
from collections import Counter
from datetime import datetime
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(
        description="Summarize persona agent feedback into aggregate metrics.",
    )
    parser.add_argument(
        "--input",
        required=True,
        help="JSON file containing persona feedback entries.",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Where to write the aggregate metrics JSON.",
    )
    parser.add_argument(
        "--label",
        default=None,
        help="Optional label written into the metrics JSON.",
    )
    return parser.parse_args()


def round_score(value):
    return round(value, 4)


def main():
    args = parse_args()
    input_path = Path(args.input).resolve()
    output_path = Path(args.output).resolve()

    feedback = json.loads(input_path.read_text(encoding="utf-8"))
    if not isinstance(feedback, list):
        raise SystemExit(f"Expected a JSON list in {input_path}")

    reviews = []
    top1_scores = []
    verdict_counts = Counter()

    for entry in feedback:
        candidate_reviews = entry.get("candidate_reviews", [])
        if not isinstance(candidate_reviews, list):
            raise SystemExit("Each feedback entry must contain a candidate_reviews list.")
        reviews.extend(candidate_reviews)
        ranked_reviews = sorted(
            candidate_reviews,
            key=lambda item: (item.get("rank", 9999), item.get("name", "")),
        )
        if ranked_reviews:
            top1_scores.append(float(ranked_reviews[0].get("score", 0)))
        for review in candidate_reviews:
            verdict = review.get("verdict")
            if verdict:
                verdict_counts[verdict] += 1

    review_scores = [float(review.get("score", 0)) for review in reviews]
    metrics = {
        "label": args.label,
        "source_input": str(input_path),
        "persona_count": len(feedback),
        "candidate_review_count": len(reviews),
        "average_score": round_score(sum(review_scores) / len(review_scores)) if review_scores else 0.0,
        "top1_average_score": round_score(sum(top1_scores) / len(top1_scores)) if top1_scores else 0.0,
        "verdict_counts": dict(sorted(verdict_counts.items())),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
