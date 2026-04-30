#!/usr/bin/env python3

import argparse
import json
import shlex
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(
        description="Render persona evaluation results into markdown review packets.",
    )
    parser.add_argument(
        "--input",
        required=True,
        help="JSON results file from a persona evaluation run.",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Where to write the markdown packet file.",
    )
    parser.add_argument(
        "--section-label",
        default="results",
        help="Markdown section label such as round6 or hard-mode-v2.",
    )
    parser.add_argument(
        "--include-command",
        action="store_true",
        help="Include the original command for each persona block.",
    )
    parser.add_argument(
        "--include-status",
        action="store_true",
        help="Include returncode, has_match, and ran_at metadata for each persona block.",
    )
    return parser.parse_args()


def load_results(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise SystemExit(f"Expected a JSON list in {path}")
    return data


def render_persona_block(entry, section_label, include_command=False, include_status=False):
    persona_id = entry.get("id", "unknown")
    name = entry.get("name", "unknown")
    persona = entry.get("persona") or "未提供"
    lines = [
        f"## {persona_id} {name}",
        f"persona: {persona}",
        "",
    ]

    if include_status:
        returncode = entry.get("returncode")
        has_match = entry.get("has_match")
        ran_at = entry.get("ran_at")
        status_bits = [
            f"returncode={returncode}",
            f"has_match={has_match}",
        ]
        if ran_at:
            status_bits.append(f"ran_at={ran_at}")
        lines.append("status: " + " | ".join(status_bits))
        lines.append("")

    if include_command:
        command = entry.get("command")
        if isinstance(command, list) and command:
            lines.append("command: " + shlex.join(str(part) for part in command))
        else:
            lines.append("command: <missing>")
        lines.append("")

    lines.append(f"### {section_label}")

    output = str(entry.get("output") or "").strip()
    if output:
        lines.extend(output.splitlines())
    else:
        lines.append("No output captured.")

    return "\n".join(lines)


def main():
    args = parse_args()
    input_path = Path(args.input).resolve()
    output_path = Path(args.output).resolve()

    results = load_results(input_path)
    blocks = [
        render_persona_block(
            entry,
            args.section_label,
            include_command=args.include_command,
            include_status=args.include_status,
        )
        for entry in results
    ]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n\n".join(blocks) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
