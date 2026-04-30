#!/usr/bin/env python3

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path


NO_MATCH_MARKERS = (
    "No matches found.",
    "No matches found",
)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Rerun a persona benchmark JSON file and write refreshed results.",
    )
    parser.add_argument(
        "--input",
        required=True,
        help="JSON file containing persona entries with a command array.",
    )
    parser.add_argument(
        "--results-output",
        required=True,
        help="Where to write the refreshed result JSON.",
    )
    parser.add_argument(
        "--metrics-output",
        default=None,
        help="Optional path for aggregate metrics JSON.",
    )
    parser.add_argument(
        "--cwd",
        default=None,
        help="Working directory for subprocess execution. Defaults to the input file directory.",
    )
    parser.add_argument(
        "--label",
        default=None,
        help="Optional label written into the metrics JSON.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero if any command fails.",
    )
    return parser.parse_args()


def load_personas(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise SystemExit(f"Expected a JSON list in {path}")
    return data


def count_candidates(stdout):
    return len(re.findall(r"(?m)^\d+\.\s", stdout or ""))


def has_match(stdout, returncode):
    if returncode != 0:
        return False
    return not any(marker in (stdout or "") for marker in NO_MATCH_MARKERS)


def run_entry(persona, repo_root, index, total):
    persona_id = persona["id"]
    name = persona["name"]
    command = persona["command"]
    if not isinstance(command, list) or not command:
        raise SystemExit(f"Persona {persona_id} has an invalid command array.")

    print(f"[{index:02d}/{total:02d}] running {persona_id} {name}", file=sys.stderr)
    completed = subprocess.run(
        command,
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    stdout = completed.stdout.strip()
    stderr = completed.stderr.strip()
    output = stdout
    if stderr:
        output = f"{stdout}\n\n[stderr]\n{stderr}".strip()

    return {
        "id": persona_id,
        "name": name,
        "persona": persona.get("persona"),
        "command": command,
        "returncode": completed.returncode,
        "has_match": has_match(stdout, completed.returncode),
        "candidate_count": count_candidates(stdout),
        "output": output,
        "ran_at": datetime.now().isoformat(timespec="seconds"),
    }


def summarize_results(results, input_path, label=None):
    persona_count = len(results)
    success_count = sum(1 for item in results if item["returncode"] == 0)
    failure_count = persona_count - success_count
    match_count = sum(1 for item in results if item["has_match"])
    no_match_count = persona_count - match_count
    candidate_counts = [item["candidate_count"] for item in results]
    average_candidate_count = (
        round(sum(candidate_counts) / len(candidate_counts), 4) if candidate_counts else 0.0
    )
    max_candidate_count = max(candidate_counts) if candidate_counts else 0
    metrics = {
        "label": label,
        "source_input": str(input_path),
        "persona_count": persona_count,
        "success_count": success_count,
        "failure_count": failure_count,
        "match_count": match_count,
        "no_match_count": no_match_count,
        "success_rate": round(success_count / persona_count, 4) if persona_count else 0.0,
        "match_rate": round(match_count / persona_count, 4) if persona_count else 0.0,
        "average_candidate_count": average_candidate_count,
        "max_candidate_count": max_candidate_count,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }
    return metrics


def write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    args = parse_args()
    input_path = Path(args.input).resolve()
    results_output_path = Path(args.results_output).resolve()
    metrics_output_path = Path(args.metrics_output).resolve() if args.metrics_output else None
    repo_root = input_path.parent if args.cwd is None else Path(args.cwd).resolve()

    personas = load_personas(input_path)
    print(
        f"[persona-eval] loaded {len(personas)} personas from {input_path}",
        file=sys.stderr,
    )

    results = [
        run_entry(persona, repo_root, index, len(personas))
        for index, persona in enumerate(personas, start=1)
    ]
    write_json(results_output_path, results)
    print(
        f"[persona-eval] wrote {len(results)} results to {results_output_path}",
        file=sys.stderr,
    )

    metrics = summarize_results(results, input_path, args.label)
    if metrics_output_path:
        write_json(metrics_output_path, metrics)
        print(
            f"[persona-eval] wrote metrics to {metrics_output_path}",
            file=sys.stderr,
        )
    else:
        print(json.dumps(metrics, ensure_ascii=False, indent=2), file=sys.stderr)

    if args.strict and metrics["failure_count"] > 0:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
