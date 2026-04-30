#!/usr/bin/env python3

import argparse
import json
from collections import Counter
from datetime import datetime
from numbers import Number
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


def as_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return [item for item in value if item not in (None, "")]
    if isinstance(value, str):
        value = value.strip()
        return [value] if value else []
    return [value]


def as_optional_float(value):
    if isinstance(value, Number):
        return float(value)
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
        try:
            return float(value)
        except ValueError:
            return None
    return None


def load_feedback(path):
    feedback = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(feedback, list):
        raise SystemExit(f"Expected a JSON list in {path}")
    return feedback


def extract_candidate_reviews(entry):
    direct_reviews = entry.get("candidate_reviews")
    if direct_reviews is not None:
        if not isinstance(direct_reviews, list):
            raise SystemExit("Each feedback entry must contain a candidate_reviews list.")
        return direct_reviews

    matching_feedback = entry.get("matching_feedback")
    if matching_feedback is None:
        return []
    if not isinstance(matching_feedback, dict):
        raise SystemExit("matching_feedback must be a JSON object when present.")

    nested_reviews = matching_feedback.get("candidate_reviews", [])
    if not isinstance(nested_reviews, list):
        raise SystemExit("matching_feedback.candidate_reviews must be a list.")
    return nested_reviews


def extract_matching_feedback(entry):
    matching_feedback = entry.get("matching_feedback")
    if matching_feedback is None:
        return {}
    if not isinstance(matching_feedback, dict):
        raise SystemExit("matching_feedback must be a JSON object when present.")
    return matching_feedback


def extract_memory_accuracy(entry):
    memory_accuracy = entry.get("memory_accuracy")
    if memory_accuracy is None:
        return {}
    if not isinstance(memory_accuracy, dict):
        raise SystemExit("memory_accuracy must be a JSON object when present.")
    return memory_accuracy


def extract_persona_id(entry, index):
    return (
        entry.get("persona_id")
        or entry.get("id")
        or entry.get("user_key")
        or f"persona_{index:02d}"
    )


def summarize_feedback(feedback, input_path, label=None):
    reviews = []
    top1_scores = []
    overall_scores = []
    verdict_counts = Counter()
    matching_satisfaction_counts = Counter()
    overall_verdict_counts = Counter()

    persona_summaries = []
    memory_reviewed_persona_count = 0
    memory_drift_persona_count = 0
    privacy_flag_persona_count = 0
    systemic_issue_persona_count = 0
    no_match_persona_count = 0

    total_memory_drift_count = 0
    total_privacy_flag_count = 0
    total_systemic_issue_count = 0

    for index, entry in enumerate(feedback, start=1):
        candidate_reviews = extract_candidate_reviews(entry)
        matching_feedback = extract_matching_feedback(entry)
        memory_accuracy = extract_memory_accuracy(entry)
        systemic_issues = as_list(
            matching_feedback.get("systemic_issues", entry.get("systemic_issue"))
        )
        memory_drift = as_list(memory_accuracy.get("drift", entry.get("drift")))
        privacy_flags = as_list(
            memory_accuracy.get("do_not_public", entry.get("do_not_public"))
        )

        reviews.extend(candidate_reviews)
        ranked_reviews = sorted(
            candidate_reviews,
            key=lambda item: (item.get("rank", 9999), item.get("name", "")),
        )
        if ranked_reviews:
            top1_score = as_optional_float(ranked_reviews[0].get("score"))
            if top1_score is not None:
                top1_scores.append(top1_score)
        for review in candidate_reviews:
            verdict = review.get("verdict")
            if verdict:
                verdict_counts[verdict] += 1

        satisfaction = matching_feedback.get("overall_satisfaction")
        if satisfaction:
            matching_satisfaction_counts[str(satisfaction)] += 1

        overall_verdict = entry.get("overall_verdict")
        if overall_verdict:
            overall_verdict_counts[str(overall_verdict)] += 1

        overall_score = as_optional_float(entry.get("overall_score"))
        if overall_score is not None:
            overall_scores.append(overall_score)

        if memory_accuracy:
            memory_reviewed_persona_count += 1
        if memory_drift:
            memory_drift_persona_count += 1
        if privacy_flags:
            privacy_flag_persona_count += 1
        if systemic_issues:
            systemic_issue_persona_count += 1
        if not candidate_reviews:
            no_match_persona_count += 1

        total_memory_drift_count += len(memory_drift)
        total_privacy_flag_count += len(privacy_flags)
        total_systemic_issue_count += len(systemic_issues)

        top_candidate = None
        if ranked_reviews:
            first = ranked_reviews[0]
            top_candidate = {
                "name": first.get("name"),
                "verdict": first.get("verdict"),
                "score": as_optional_float(first.get("score")),
            }

        persona_summaries.append(
            {
                "persona_id": extract_persona_id(entry, index),
                "display_name": entry.get("display_name") or entry.get("name"),
                "overall_score": overall_score,
                "overall_satisfaction": satisfaction,
                "overall_verdict": overall_verdict,
                "candidate_review_count": len(candidate_reviews),
                "memory_drift_count": len(memory_drift),
                "privacy_flag_count": len(privacy_flags),
                "systemic_issue_count": len(systemic_issues),
                "no_match": not candidate_reviews,
                "top_candidate": top_candidate,
            }
        )

    review_scores = [
        score
        for score in (as_optional_float(review.get("score")) for review in reviews)
        if score is not None
    ]
    persona_count = len(feedback)
    return {
        "label": label,
        "source_input": str(input_path),
        "persona_count": persona_count,
        "candidate_review_count": len(reviews),
        "average_score": round_score(sum(review_scores) / len(review_scores)) if review_scores else 0.0,
        "top1_average_score": round_score(sum(top1_scores) / len(top1_scores)) if top1_scores else 0.0,
        "verdict_counts": dict(sorted(verdict_counts.items())),
        "overall_score_average": (
            round_score(sum(overall_scores) / len(overall_scores)) if overall_scores else 0.0
        ),
        "overall_score_count": len(overall_scores),
        "matching_satisfaction_counts": dict(sorted(matching_satisfaction_counts.items())),
        "overall_verdict_counts": dict(sorted(overall_verdict_counts.items())),
        "no_match_persona_count": no_match_persona_count,
        "memory_reviewed_persona_count": memory_reviewed_persona_count,
        "memory_drift_persona_count": memory_drift_persona_count,
        "privacy_flag_persona_count": privacy_flag_persona_count,
        "systemic_issue_persona_count": systemic_issue_persona_count,
        "average_memory_drift_count": (
            round_score(total_memory_drift_count / persona_count) if persona_count else 0.0
        ),
        "average_privacy_flag_count": (
            round_score(total_privacy_flag_count / persona_count) if persona_count else 0.0
        ),
        "average_systemic_issue_count": (
            round_score(total_systemic_issue_count / persona_count) if persona_count else 0.0
        ),
        "personas": persona_summaries,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }


def write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    args = parse_args()
    input_path = Path(args.input).resolve()
    output_path = Path(args.output).resolve()

    feedback = load_feedback(input_path)
    metrics = summarize_feedback(feedback, input_path, args.label)

    write_json(output_path, metrics)


if __name__ == "__main__":
    main()
