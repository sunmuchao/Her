#!/usr/bin/env python3

import argparse
import json
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from persona_memory_sync.audit import mask_snapshot_for_review  # noqa: E402
from persona_memory_sync.persona_memory_lib import OBSERVATION_FIELD_LABELS  # noqa: E402


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

USER_PERSONA_LABELS = {
    **OBSERVATION_FIELD_LABELS,
    "persona_summary_internal": "内部人物摘要",
    "preference_summary_internal": "内部偏好摘要",
    "public_profile_summary_draft": "公开人物草稿",
    "public_preference_summary_draft": "公开偏好草稿",
}

PROFILE_INTERNAL_FOCUS_LABELS = {
    "education": "学历",
    "public_education": "公开学历",
    "job": "工作",
    "public_job": "公开职业",
    "relationship_goal": "关系目标",
    "smoking": "抽烟情况",
    "drinking": "喝酒情况",
    "long_distance": "异地态度",
    "accept_long_distance": "是否接受异地",
    "location_preference_semantics": "位置偏好补充",
    "accept_partner_children": "是否接受对方有孩子",
    "accept_partner_children_strength": "对子女接受强度",
    "accept_partner_children_semantics": "对子女补充说明",
    "accept_marital_status": "可接受婚况",
    "accept_marital_status_strength": "婚史接受强度",
    "accept_marital_status_semantics": "婚史补充说明",
    "requires_partner_accept_my_children": "是否需要对方接受自己的孩子现实",
    "personality": "内部人物摘要",
    "values": "内部偏好摘要",
    "notes": "内部补充",
    "public_personality": "公开人物展示",
    "public_values": "公开偏好展示",
    "public_notes": "公开备注",
}

PUBLIC_PROFILE_VIEW_LABELS = {
    "id": "资料ID",
    "name": "公开昵称",
    "gender": "性别",
    "age": "年龄",
    "city": "城市",
    "district": "区域",
    "height": "身高",
    "education": "公开学历",
    "job": "公开职业",
    "relationship_goal": "公开关系目标",
    "smoking": "公开抽烟情况",
    "drinking": "公开喝酒情况",
    "personality": "公开人物展示",
    "values": "公开偏好展示",
    "notes": "公开备注",
}


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


def readable_fields(source, label_map):
    if not isinstance(source, dict):
        return {}
    readable = {}
    for key, value in source.items():
        label = label_map.get(key, key)
        readable[label] = value
    return prune_none(readable)


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
        private_boundaries = snapshot.get("private_boundaries") or persona.get("private_boundaries") or []
        remasked_snapshot = mask_snapshot_for_review(
            {
                "user_persona": snapshot.get("user_persona") or {},
                "profile_internal": snapshot.get("profile_internal") or {},
                "public_profile_view": snapshot.get("public_profile_view") or {},
            },
            private_boundaries,
        )
        user_persona = remasked_snapshot.get("user_persona") or {}
        profile_internal_focus = pick_fields(
            remasked_snapshot.get("profile_internal"), PROFILE_INTERNAL_FOCUS_FIELDS
        )
        public_profile_view = remasked_snapshot.get("public_profile_view") or {}
        packets.append(
            prune_none(
                {
                    "persona_id": persona_id,
                    "display_name": persona.get("display_name") or snapshot.get("display_name"),
                    "agent_id": persona.get("agent_id") or snapshot.get("agent_id"),
                    "user_key": persona.get("user_key") or snapshot.get("user_key"),
                    "profile_id": snapshot.get("profile_id") or persona.get("profile_id"),
                    "private_boundaries": private_boundaries,
                    "roleplay_answers": persona.get("roleplay_answers")
                    or snapshot.get("roleplay_answers")
                    or [],
                    "notes_about_possible_drift": persona.get("notes_about_possible_drift")
                    or snapshot.get("notes_about_possible_drift")
                    or [],
                    "user_persona": user_persona,
                    "user_persona_readable": readable_fields(user_persona, USER_PERSONA_LABELS),
                    "profile_internal_focus": profile_internal_focus,
                    "profile_internal_focus_readable": readable_fields(
                        profile_internal_focus, PROFILE_INTERNAL_FOCUS_LABELS
                    ),
                    "public_profile_view": public_profile_view,
                    "public_profile_view_readable": readable_fields(
                        public_profile_view, PUBLIC_PROFILE_VIEW_LABELS
                    ),
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
