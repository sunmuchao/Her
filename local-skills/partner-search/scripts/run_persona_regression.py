#!/usr/bin/env python3

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(
        description="Rerun persona search commands from a prior experiment JSON file.",
    )
    parser.add_argument(
        "--input",
        required=True,
        help="JSON file containing persona entries with a command array.",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Where to write the refreshed regression result JSON.",
    )
    parser.add_argument(
        "--cwd",
        default=None,
        help="Working directory for subprocess execution. Defaults to the repo root.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    input_path = Path(args.input).resolve()
    output_path = Path(args.output).resolve()
    repo_root = input_path.parent if args.cwd is None else Path(args.cwd).resolve()

    personas = json.loads(input_path.read_text(encoding="utf-8"))
    results = []

    print(
        f"[persona-regression] loaded {len(personas)} personas from {input_path}",
        file=sys.stderr,
    )

    for index, persona in enumerate(personas, start=1):
        persona_id = persona["id"]
        name = persona["name"]
        command = persona["command"]
        print(
            f"[{index:02d}/{len(personas):02d}] running {persona_id} {name}",
            file=sys.stderr,
        )
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
        results.append(
            {
                "id": persona_id,
                "name": name,
                "persona": persona.get("persona"),
                "command": command,
                "returncode": completed.returncode,
                "has_match": "No matches found." not in stdout and completed.returncode == 0,
                "output": output,
                "ran_at": datetime.now().isoformat(timespec="seconds"),
            }
        )

    output_path.write_text(
        json.dumps(results, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"[persona-regression] wrote {len(results)} results to {output_path}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
