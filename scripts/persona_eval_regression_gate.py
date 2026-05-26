#!/usr/bin/env python3
"""Compare persona-eval metrics against a baseline (§10.3 AI regression gate)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _load(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def compare_metrics(*, baseline: dict[str, Any], candidate: dict[str, Any], min_avg: float) -> list[str]:
    errors: list[str] = []
    base_avg = float(baseline.get("average_score") or 0)
    cand_avg = float(candidate.get("average_score") or 0)
    floor = max(min_avg, base_avg - 0.5)
    if cand_avg < floor:
        errors.append(
            f"average_score regressed: candidate={cand_avg} baseline={base_avg} floor={floor}"
        )
    base_count = int(baseline.get("persona_count") or 0)
    cand_count = int(candidate.get("persona_count") or 0)
    if base_count and cand_count < base_count:
        errors.append(f"persona_count dropped: candidate={cand_count} baseline={base_count}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Persona-eval regression gate")
    parser.add_argument(
        "--baseline",
        type=Path,
        default=Path("artifacts/persona-eval/persona_agent_metrics_v11_2026-04-29.json"),
    )
    parser.add_argument("--candidate", type=Path, default=None)
    parser.add_argument("--min-average-score", type=float, default=8.0)
    parser.add_argument(
        "--self-check",
        action="store_true",
        help="Validate baseline file only (CI smoke).",
    )
    args = parser.parse_args()

    if not args.baseline.is_file():
        print(f"Baseline metrics missing: {args.baseline}")
        return 1

    baseline = _load(args.baseline)
    if args.self_check:
        print(f"Baseline OK: persona_count={baseline.get('persona_count')} avg={baseline.get('average_score')}")
        return 0

    if args.candidate is None:
        print("--candidate is required unless --self-check is set")
        return 1
    if not args.candidate.is_file():
        print(f"Candidate metrics missing: {args.candidate}")
        return 1

    candidate = _load(args.candidate)
    errors = compare_metrics(
        baseline=baseline,
        candidate=candidate,
        min_avg=float(args.min_average_score),
    )
    if errors:
        print("Persona-eval regression gate failed:")
        for err in errors:
            print(f"  - {err}")
        return 1
    print("Persona-eval regression gate passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
