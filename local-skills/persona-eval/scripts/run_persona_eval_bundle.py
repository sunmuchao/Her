#!/usr/bin/env python3

import argparse
import json
import sys
from pathlib import Path

import generate_persona_packets
import run_persona_eval


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run a persona benchmark and emit results JSON, packet markdown, and metrics JSON.",
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
        "--packets-output",
        required=True,
        help="Where to write the markdown packet output.",
    )
    parser.add_argument(
        "--metrics-output",
        required=True,
        help="Where to write aggregate metrics JSON.",
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
        "--section-label",
        default="results",
        help="Markdown section label such as round6 or hard-mode-v2.",
    )
    parser.add_argument(
        "--include-command",
        action="store_true",
        help="Include the original command for each persona block in packets output.",
    )
    parser.add_argument(
        "--include-status",
        action="store_true",
        help="Include returncode, has_match, and ran_at metadata for each persona block in packets output.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero if any benchmark command fails.",
    )
    return parser.parse_args()


def write_text(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def main():
    args = parse_args()
    input_path = Path(args.input).resolve()
    results_output_path = Path(args.results_output).resolve()
    packets_output_path = Path(args.packets_output).resolve()
    metrics_output_path = Path(args.metrics_output).resolve()
    repo_root = input_path.parent if args.cwd is None else Path(args.cwd).resolve()

    personas = run_persona_eval.load_personas(input_path)
    print(
        f"[persona-eval-bundle] loaded {len(personas)} personas from {input_path}",
        file=sys.stderr,
    )

    results = [
        run_persona_eval.run_entry(persona, repo_root, index, len(personas))
        for index, persona in enumerate(personas, start=1)
    ]
    run_persona_eval.write_json(results_output_path, results)
    print(
        f"[persona-eval-bundle] wrote results to {results_output_path}",
        file=sys.stderr,
    )

    metrics = run_persona_eval.summarize_results(results, input_path, args.label)
    run_persona_eval.write_json(metrics_output_path, metrics)
    print(
        f"[persona-eval-bundle] wrote metrics to {metrics_output_path}",
        file=sys.stderr,
    )

    blocks = [
        generate_persona_packets.render_persona_block(
            entry,
            args.section_label,
            include_command=args.include_command,
            include_status=args.include_status,
        )
        for entry in results
    ]
    write_text(packets_output_path, "\n\n".join(blocks) + "\n")
    print(
        f"[persona-eval-bundle] wrote packets to {packets_output_path}",
        file=sys.stderr,
    )

    print(json.dumps(metrics, ensure_ascii=False, indent=2), file=sys.stderr)

    if args.strict and metrics["failure_count"] > 0:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
