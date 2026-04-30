#!/usr/bin/env python3

import argparse
import json
from pathlib import Path


PROFILE_INTERNAL_FOCUS_FIELDS = [
    "education",
    "public_education",
    "job",
    "public_job",
    "relationship_goal",
    "smoking",
    "drinking",
    "long_distance",
    "accept_long_distance",
    "location_preference_semantics",
    "accept_partner_children",
    "accept_partner_children_strength",
    "accept_partner_children_semantics",
    "accept_marital_status",
    "accept_marital_status_strength",
    "accept_marital_status_semantics",
    "requires_partner_accept_my_children",
    "personality",
    "values",
    "notes",
    "public_personality",
    "public_values",
    "public_notes",
]


def parse_args():
    parser = argparse.ArgumentParser(
        description="Merge persona inputs, memory snapshots, and full search results into review_packets.json.",
    )
    parser.add_argument("--input-personas", required=True)
    parser.add_argument("--memory-snapshots", required=True)
    parser.add_argument("--search-results", required=True)
    parser.add_argument("--output", required=True)
    return parser.parse_args()


def load_json_list(path):
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise SystemExit(f"Expected a JSON list in {path}")
    return payload


def write_json(path, payload):
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def prune_none(value):
    if isinstance(value, dict):
        return {key: prune_none(item) for key, item in value.items() if item is not None}
    if isinstance(value, list):
        return [prune_none(item) for item in value]
    return value


def pick_fields(source, field_names):
    if not isinstance(source, dict):
        return {}
    return prune_none({field: source.get(field) for field in field_names})


def build_packets(input_personas, memory_snapshots, search_results):
    snapshot_index = {
        item.get("persona_id"): item for item in memory_snapshots if item.get("persona_id")
    }
    search_index = {
        item.get("persona_id") or item.get("id"): item
        for item in search_results
        if item.get("persona_id") or item.get("id")
    }

    packets = []
    for persona in input_personas:
        persona_id = persona.get("persona_id")
        snapshot = snapshot_index.get(persona_id, {})
        search_result = search_index.get(persona_id, {})
        packets.append(
            prune_none(
                {
                    "persona_id": persona_id,
                    "display_name": persona.get("display_name") or snapshot.get("display_name"),
                    "agent_id": persona.get("agent_id") or snapshot.get("agent_id"),
                    "user_key": persona.get("user_key") or snapshot.get("user_key"),
                    "profile_id": snapshot.get("profile_id") or persona.get("profile_id"),
                    "private_boundaries": snapshot.get("private_boundaries")
                    or persona.get("private_boundaries")
                    or [],
                    "roleplay_answers": persona.get("roleplay_answers")
                    or snapshot.get("roleplay_answers")
                    or [],
                    "notes_about_possible_drift": persona.get("notes_about_possible_drift")
                    or snapshot.get("notes_about_possible_drift")
                    or [],
                    "user_persona": snapshot.get("user_persona") or {},
                    "profile_internal_focus": pick_fields(
                        snapshot.get("profile_internal"), PROFILE_INTERNAL_FOCUS_FIELDS
                    ),
                    "public_profile_view": snapshot.get("public_profile_view") or {},
                    "search_output": search_result or {},
                }
            )
        )
    return packets


def main():
    args = parse_args()
    input_personas = load_json_list(args.input_personas)
    memory_snapshots = load_json_list(args.memory_snapshots)
    search_results = load_json_list(args.search_results)
    packets = build_packets(input_personas, memory_snapshots, search_results)
    write_json(args.output, packets)
    print(
        json.dumps(
            {
                "input_persona_count": len(input_personas),
                "memory_snapshot_count": len(memory_snapshots),
                "search_result_count": len(search_results),
                "output": str(Path(args.output).resolve()),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
