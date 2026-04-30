#!/usr/bin/env python3

import argparse
import json
import sys
from pathlib import Path

import summarize_agent_feedback


RAW_RESPONSE_KEYS = (
    "response",
    "raw_response",
    "completed",
    "content",
    "message",
    "text",
)

META_KEYS = (
    "persona_id",
    "display_name",
    "agent_id",
    "user_key",
    "profile_id",
    "private_boundaries",
)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Normalize raw multi-agent reviewer replies into persona-eval agent_feedback.json.",
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Raw feedback JSON. Supports wait_agent status payloads, results reports, and feedback lists.",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Where to write the normalized agent_feedback.json list.",
    )
    parser.add_argument(
        "--persona-index-input",
        default=None,
        help="Optional persona index JSON such as input_personas.json or memory_snapshots.json.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero if any raw entry cannot be normalized cleanly.",
    )
    return parser.parse_args()


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def strip_code_fences(text):
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped

    lines = stripped.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def parse_json_fragment(text):
    cleaned = strip_code_fences(text)
    if not cleaned:
        raise ValueError("empty response text")

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        decoder = json.JSONDecoder()
        for start_char in ("{", "["):
            start = cleaned.find(start_char)
            while start != -1:
                try:
                    value, _end = decoder.raw_decode(cleaned[start:])
                    return value
                except json.JSONDecodeError:
                    start = cleaned.find(start_char, start + 1)
        raise


def maybe_parse_embedded_response(value):
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        return parse_json_fragment(value)
    raise ValueError(f"Unsupported raw response type: {type(value).__name__}")


def load_persona_index(path):
    data = load_json(path)
    if isinstance(data, dict) and "results" in data:
        data = data["results"]
    if not isinstance(data, list):
        raise SystemExit(f"Expected a JSON list or results list in {path}")

    index = {
        "ordered": [],
        "by_persona_id": {},
        "by_agent_id": {},
    }
    for entry in data:
        if not isinstance(entry, dict):
            continue
        record = {key: entry.get(key) for key in META_KEYS if key in entry}
        persona_id = record.get("persona_id")
        agent_id = record.get("agent_id")
        if persona_id:
            index["by_persona_id"][persona_id] = record
            index["ordered"].append(persona_id)
        if agent_id:
            index["by_agent_id"][agent_id] = record
    return index


def build_meta_lookup(entry, persona_index=None, fallback_key=None):
    meta = {}
    if persona_index:
        persona_id = entry.get("persona_id")
        agent_id = entry.get("agent_id") or fallback_key
        if persona_id and persona_id in persona_index["by_persona_id"]:
            meta.update(persona_index["by_persona_id"][persona_id])
        if agent_id and agent_id in persona_index["by_agent_id"]:
            meta.update(persona_index["by_agent_id"][agent_id])
        if not meta and fallback_key and fallback_key in persona_index["by_persona_id"]:
            meta.update(persona_index["by_persona_id"][fallback_key])
    for key in META_KEYS:
        if entry.get(key) is not None:
            meta[key] = entry.get(key)
    return meta


def build_memory_accuracy(entry, has_matching_shape):
    has_memory_shape = any(
        key in entry for key in ("memory_accuracy", "accurate", "drift", "do_not_public")
    )
    if isinstance(entry.get("memory_accuracy"), dict):
        memory_accuracy = dict(entry["memory_accuracy"])
    elif has_memory_shape:
        memory_accuracy = {
            "accurate": summarize_agent_feedback.as_list(entry.get("accurate")),
            "drift": summarize_agent_feedback.as_list(entry.get("drift")),
            "do_not_public": summarize_agent_feedback.as_list(entry.get("do_not_public")),
        }
        summary = entry.get("summary")
        if summary and not has_matching_shape:
            memory_accuracy["summary"] = summary
    else:
        return None

    if "summary" in entry and "summary" not in memory_accuracy and not has_matching_shape:
        memory_accuracy["summary"] = entry["summary"]
    return memory_accuracy


def build_matching_feedback(entry, has_memory_shape):
    direct = entry.get("matching_feedback")
    if isinstance(direct, dict):
        matching_feedback = dict(direct)
    else:
        has_matching_shape = any(
            key in entry
            for key in (
                "matching_feedback",
                "candidate_reviews",
                "overall_satisfaction",
                "no_match_reasonable",
                "systemic_issue",
                "systemic_issues",
                "overall_verdict",
            )
        )
        if not has_matching_shape:
            return None

        matching_feedback = {
            "candidate_reviews": entry.get("candidate_reviews", []),
            "overall_satisfaction": entry.get("overall_satisfaction"),
            "no_match_reasonable": entry.get("no_match_reasonable"),
            "systemic_issues": summarize_agent_feedback.as_list(
                entry.get("systemic_issues", entry.get("systemic_issue"))
            ),
        }
        summary = entry.get("summary")
        if summary and not has_memory_shape:
            matching_feedback["summary"] = summary

    if "candidate_reviews" not in matching_feedback:
        matching_feedback["candidate_reviews"] = []
    if not isinstance(matching_feedback["candidate_reviews"], list):
        raise ValueError("candidate_reviews must be a list")

    systemic = matching_feedback.get("systemic_issues")
    if systemic is not None:
        matching_feedback["systemic_issues"] = summarize_agent_feedback.as_list(systemic)
    return matching_feedback


def normalize_entry(entry, persona_index=None, fallback_key=None):
    if not isinstance(entry, dict):
        raise ValueError("raw feedback entry must be a JSON object")

    meta = build_meta_lookup(entry, persona_index=persona_index, fallback_key=fallback_key)
    has_matching_shape = any(
        key in entry
        for key in (
            "matching_feedback",
            "candidate_reviews",
            "overall_satisfaction",
            "no_match_reasonable",
            "systemic_issue",
            "systemic_issues",
            "overall_verdict",
        )
    )
    memory_accuracy = build_memory_accuracy(entry, has_matching_shape)
    matching_feedback = build_matching_feedback(entry, has_memory_shape=memory_accuracy is not None)

    normalized = dict(meta)
    if memory_accuracy is not None:
        normalized["memory_accuracy"] = memory_accuracy
    if matching_feedback is not None:
        normalized["matching_feedback"] = matching_feedback

    overall_score = summarize_agent_feedback.as_optional_float(entry.get("overall_score"))
    if overall_score is not None:
        normalized["overall_score"] = overall_score

    if entry.get("overall_verdict") is not None:
        normalized["overall_verdict"] = entry.get("overall_verdict")
    if entry.get("final_summary") is not None:
        normalized["final_summary"] = entry.get("final_summary")

    if "summary" in entry and "final_summary" not in normalized:
        if memory_accuracy is not None and matching_feedback is not None:
            normalized["final_summary"] = entry["summary"]
        elif memory_accuracy is None and matching_feedback is None:
            normalized["final_summary"] = entry["summary"]

    for passthrough_key in ("risk_level",):
        if entry.get(passthrough_key) is not None:
            normalized[passthrough_key] = entry.get(passthrough_key)

    if "persona_id" not in normalized:
        raise ValueError("persona_id is missing and could not be inferred")
    return normalized


def normalize_from_results_report(payload, persona_index=None):
    results = payload.get("results")
    if not isinstance(results, list):
        raise ValueError("results payload must contain a results list")
    return [normalize_entry(entry, persona_index=persona_index) for entry in results]


def normalize_from_wait_status(payload, persona_index=None):
    status = payload.get("status")
    if not isinstance(status, dict):
        raise ValueError("status payload must contain a status object")

    normalized = []
    errors = []
    for agent_id, agent_status in status.items():
        if not isinstance(agent_status, dict):
            errors.append(f"{agent_id}: status payload is not an object")
            continue
        if "completed" not in agent_status:
            errors.append(f"{agent_id}: missing completed field")
            continue
        try:
            parsed = maybe_parse_embedded_response(agent_status["completed"])
            if not isinstance(parsed, dict):
                raise ValueError("completed payload must decode to a JSON object")
            parsed.setdefault("agent_id", agent_id)
            normalized.append(
                normalize_entry(parsed, persona_index=persona_index, fallback_key=agent_id)
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{agent_id}: {exc}")
    return normalized, errors


def normalize_from_list(payload, persona_index=None):
    normalized = []
    errors = []
    for index, item in enumerate(payload, start=1):
        try:
            entry = item
            if isinstance(item, dict):
                raw_value = None
                for key in RAW_RESPONSE_KEYS:
                    if key in item:
                        raw_value = item[key]
                        break
                if raw_value is not None:
                    parsed = maybe_parse_embedded_response(raw_value)
                    if not isinstance(parsed, dict):
                        raise ValueError("embedded response must decode to a JSON object")
                    merged = dict(item)
                    for key in RAW_RESPONSE_KEYS:
                        merged.pop(key, None)
                    merged.update(parsed)
                    entry = merged
            elif isinstance(item, str):
                entry = maybe_parse_embedded_response(item)

            normalized.append(normalize_entry(entry, persona_index=persona_index))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"item[{index}]: {exc}")
    return normalized, errors


def normalize_from_mapping(payload, persona_index=None):
    normalized = []
    errors = []
    for key, raw_value in payload.items():
        if key in ("status", "timed_out", "summary", "results"):
            continue
        try:
            parsed = maybe_parse_embedded_response(raw_value)
            if not isinstance(parsed, dict):
                raise ValueError("mapping entry must decode to a JSON object")
            parsed.setdefault("agent_id", key)
            parsed.setdefault("persona_id", key)
            normalized.append(
                normalize_entry(parsed, persona_index=persona_index, fallback_key=key)
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{key}: {exc}")
    return normalized, errors


def sort_feedback(feedback, persona_index=None):
    if persona_index and persona_index["ordered"]:
        order = {persona_id: idx for idx, persona_id in enumerate(persona_index["ordered"])}
        feedback.sort(
            key=lambda entry: (
                order.get(entry.get("persona_id"), 10**9),
                entry.get("persona_id", ""),
                entry.get("display_name", ""),
            )
        )
        return feedback

    feedback.sort(key=lambda entry: (entry.get("persona_id", ""), entry.get("display_name", "")))
    return feedback


def normalize_feedback_payload(payload, persona_index=None):
    errors = []
    if isinstance(payload, dict) and "status" in payload:
        normalized, errors = normalize_from_wait_status(payload, persona_index=persona_index)
    elif isinstance(payload, dict) and "results" in payload:
        normalized = normalize_from_results_report(payload, persona_index=persona_index)
    elif isinstance(payload, list):
        normalized, errors = normalize_from_list(payload, persona_index=persona_index)
    elif isinstance(payload, dict):
        normalized, errors = normalize_from_mapping(payload, persona_index=persona_index)
    else:
        raise SystemExit("Unsupported raw feedback payload shape")

    return sort_feedback(normalized, persona_index=persona_index), errors


def main():
    args = parse_args()
    input_path = Path(args.input).resolve()
    output_path = Path(args.output).resolve()
    persona_index = (
        load_persona_index(Path(args.persona_index_input).resolve())
        if args.persona_index_input
        else None
    )

    payload = load_json(input_path)
    normalized, errors = normalize_feedback_payload(payload, persona_index=persona_index)
    write_json(output_path, normalized)

    print(
        f"[normalize-agent-feedback] wrote {len(normalized)} entries to {output_path}",
        file=sys.stderr,
    )
    if errors:
        for error in errors:
            print(f"[normalize-agent-feedback] warning: {error}", file=sys.stderr)
        if args.strict:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
