#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from openai import OpenAI
from pydantic import BaseModel, Field


SCRIPT_DIR = Path(__file__).resolve().parent
LOCAL_SKILLS_DIR = SCRIPT_DIR.parent.parent
PERSONA_MEMORY_SCRIPTS_DIR = LOCAL_SKILLS_DIR / "persona-memory-sync" / "scripts"
PARTNER_SEARCH_SCRIPTS_DIR = LOCAL_SKILLS_DIR / "partner-search" / "scripts"
DEFAULT_PERSONAS_FILE = LOCAL_SKILLS_DIR / "persona-memory-sync" / "references" / "audit_personas.json"
PARTNER_SEARCH_SCRIPT = PARTNER_SEARCH_SCRIPTS_DIR / "search_candidates.py"
RENDER_PUBLIC_PROFILE_SCRIPT = PERSONA_MEMORY_SCRIPTS_DIR / "render_public_profile.py"
DEFAULT_MODEL = os.environ.get("OPENAI_MODEL") or "gpt-4.1-mini"
NO_MATCH_MARKERS = ("No matches found.", "No matches found")


if str(PERSONA_MEMORY_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(PERSONA_MEMORY_SCRIPTS_DIR))
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import run_persona_memory_audit as memory_audit  # noqa: E402
import summarize_agent_feedback  # noqa: E402
from persona_memory_lib import items_from_csv  # noqa: E402


class CandidateReview(BaseModel):
    rank: int
    name: str
    score: int = Field(ge=1, le=10)
    verdict: str
    reason: str = Field(default="")


class SatisfactionResult(BaseModel):
    candidate_reviews: List[CandidateReview] = Field(default_factory=list)
    overall_verdict: str = Field(default="不满意")
    overall_summary: str = Field(default="")
    satisfied: bool = Field(default=False)
    concerns: List[str] = Field(default_factory=list)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a simulated multi-agent matchmaking audit: roleplay, persist persona memory, audit privacy, search candidates, and score satisfaction.",
    )
    parser.add_argument(
        "--personas-file",
        default=str(DEFAULT_PERSONAS_FILE),
        help="JSON file describing the simulated user agents.",
    )
    parser.add_argument(
        "--source",
        default=os.environ.get("PERSONA_MEMORY_MYSQL_SOURCE"),
        help="MySQL DSN for persona-memory-sync tables and profiles.",
    )
    parser.add_argument(
        "--search-source",
        default=os.environ.get("PARTNER_SEARCH_MYSQL_SOURCE"),
        help="Optional MySQL DSN for partner-search. Defaults to --source.",
    )
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Default model for all OpenAI calls.")
    parser.add_argument("--persona-model", default=None, help="Model used for roleplay replies. Defaults to --model.")
    parser.add_argument("--analysis-model", default=None, help="Model used for extraction, review, and satisfaction scoring. Defaults to --model.")
    parser.add_argument("--output-dir", default=".", help="Directory for the JSON and Markdown reports.")
    parser.add_argument("--run-label", default=None, help="Optional stable run label. Defaults to the current timestamp.")
    parser.add_argument("--max-personas", type=int, default=None, help="Only run the first N personas from the input file.")
    parser.add_argument("--persona-ids", default=None, help="Comma-separated subset of persona ids to run.")
    parser.add_argument("--candidate-limit", type=int, default=2, help="Maximum number of candidate matches to return per persona.")
    parser.add_argument("--photo-preview-count", type=int, default=0, help="Forwarded to partner-search for candidate previews.")
    parser.add_argument("--active-within-days", type=int, default=30, help="Recency filter for partner-search.")
    parser.add_argument(
        "--verified-level-min",
        default="basic",
        choices=["none", "basic", "photo", "id", "offline"],
        help="Minimum partner-search verification level.",
    )
    parser.add_argument("--temperature", type=float, default=0.8, help="Temperature used for roleplay replies.")
    parser.add_argument("--api-timeout", type=float, default=90.0, help="OpenAI API timeout in seconds.")
    parser.add_argument("--max-retries", type=int, default=4, help="OpenAI client retry count.")
    parser.add_argument("--fail-fast", action="store_true", help="Stop immediately when one persona run fails.")
    return parser.parse_args()


def count_candidates(stdout: str) -> int:
    return len(re.findall(r"(?m)^\d+\.\s", stdout or ""))


def has_match(stdout: str, returncode: int) -> bool:
    if returncode != 0:
        return False
    return not any(marker in (stdout or "") for marker in NO_MATCH_MARKERS)


def mask_observation_rows_for_review(
    observation_rows: List[Dict[str, Any]],
    private_boundaries: Optional[Iterable[str]],
) -> List[Dict[str, Any]]:
    if not memory_audit.mentions_income_privacy(private_boundaries):
        return observation_rows

    masked_rows: List[Dict[str, Any]] = []
    for row in observation_rows:
        masked = dict(row)
        if masked.get("field_name") == "self_income_wan":
            income_range = memory_audit.income_wan_to_range(masked.get("field_value"))
            if income_range:
                masked["field_value"] = income_range
        masked_rows.append(masked)
    return masked_rows


def fetch_observation_excerpt(
    source: str,
    *,
    user_key: str,
    observation_table: str = memory_audit.DEFAULT_OBSERVATION_TABLE,
    private_boundaries: Optional[Iterable[str]] = None,
) -> List[Dict[str, Any]]:
    conn = memory_audit.mysql_connect(source)
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT field_name, field_value, source_type, confidence_score, action_type,
                       applied_to_persona, applied_to_profile, conversation_ref, created_at
                FROM {memory_audit.quote_mysql_ident(observation_table)}
                WHERE user_key = %s
                ORDER BY id ASC
                """,
                (user_key,),
            )
            rows = cursor.fetchall() or []
    finally:
        conn.close()

    excerpt = [
        {
            "field_name": row.get("field_name"),
            "field_value": row.get("field_value"),
            "source_type": row.get("source_type"),
            "confidence_score": row.get("confidence_score"),
            "action_type": row.get("action_type"),
            "applied_to_persona": row.get("applied_to_persona"),
            "applied_to_profile": row.get("applied_to_profile"),
            "conversation_ref": row.get("conversation_ref"),
            "created_at": str(row.get("created_at")) if row.get("created_at") is not None else None,
        }
        for row in rows
    ]
    return memory_audit.prune_none(mask_observation_rows_for_review(excerpt, private_boundaries))


def refresh_public_profile(source: str, *, user_key: str) -> Dict[str, Any]:
    completed = subprocess.run(
        [
            sys.executable,
            str(RENDER_PUBLIC_PROFILE_SCRIPT),
            "--source",
            source,
            "--user-key",
            user_key,
            "--write-profile",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    return json.loads(completed.stdout or "{}")


def fetch_full_snapshot(
    source: str,
    *,
    user_key: str,
    profile_id: int,
    private_boundaries: Optional[Iterable[str]] = None,
) -> Dict[str, Any]:
    snapshot = memory_audit.fetch_snapshot(
        source,
        user_key=user_key,
        profile_id=profile_id,
        private_boundaries=private_boundaries,
    )
    snapshot["user_persona_observations"] = fetch_observation_excerpt(
        source,
        user_key=user_key,
        private_boundaries=private_boundaries,
    )
    return snapshot


def fetch_persona_row(
    source: str,
    *,
    user_key: str,
    persona_table: str = memory_audit.DEFAULT_PERSONA_TABLE,
) -> Dict[str, Any]:
    conn = memory_audit.mysql_connect(source)
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                f"SELECT * FROM {memory_audit.quote_mysql_ident(persona_table)} WHERE user_key = %s",
                (user_key,),
            )
            row = cursor.fetchone() or {}
    finally:
        conn.close()
    return row


def add_repeat_flags(command: List[str], flag: str, values: Iterable[Any]) -> None:
    for value in values:
        if value in (None, ""):
            continue
        command.extend([flag, str(value)])


def build_search_command(
    *,
    persona_row: Dict[str, Any],
    profile_id: int,
    search_source: str,
    candidate_limit: int,
    photo_preview_count: int,
    active_within_days: int,
    verified_level_min: str,
) -> List[str]:
    command = [
        sys.executable,
        str(PARTNER_SEARCH_SCRIPT),
        "--source",
        search_source,
        "--self-id",
        str(profile_id),
        "--limit",
        str(candidate_limit),
        "--active-within-days",
        str(active_within_days),
        "--verified-level-min",
        verified_level_min,
    ]

    if photo_preview_count > 0:
        command.extend(["--photo-preview-count", str(photo_preview_count)])

    target_gender = persona_row.get("target_gender")
    if target_gender:
        command.extend(["--gender", str(target_gender)])

    if persona_row.get("target_age_min") is not None:
        command.extend(["--age-min", str(persona_row["target_age_min"])])
    if persona_row.get("target_age_max") is not None:
        command.extend(["--age-max", str(persona_row["target_age_max"])])
    if persona_row.get("target_height_min") is not None:
        command.extend(["--height-min", str(persona_row["target_height_min"])])
    if persona_row.get("target_height_max") is not None:
        command.extend(["--height-max", str(persona_row["target_height_max"])])

    add_repeat_flags(command, "--city", items_from_csv(persona_row.get("target_cities")))
    add_repeat_flags(command, "--marital-status", items_from_csv(persona_row.get("target_marital_statuses")))
    add_repeat_flags(command, "--relationship-goal", [persona_row.get("self_relationship_goal")])
    add_repeat_flags(command, "--must-have", items_from_csv(persona_row.get("must_have_tags")))
    add_repeat_flags(command, "--must-not-have", items_from_csv(persona_row.get("must_not_have_tags")))
    add_repeat_flags(command, "--prefer", items_from_csv(persona_row.get("preferred_traits"))[:3])
    add_repeat_flags(command, "--marriage-timeline", [persona_row.get("target_marriage_timeline")])
    add_repeat_flags(command, "--want-children", [persona_row.get("target_want_children")])
    add_repeat_flags(command, "--accept-marital-status-strength", [persona_row.get("target_marital_status_strength")])
    add_repeat_flags(
        command,
        "--accept-partner-children-strength",
        [persona_row.get("target_accept_partner_children_strength")],
    )

    return command


def run_search(command: List[str]) -> Dict[str, Any]:
    completed = subprocess.run(
        command,
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
        "command": command,
        "returncode": completed.returncode,
        "has_match": has_match(stdout, completed.returncode),
        "candidate_count": count_candidates(stdout),
        "output": output,
    }


def review_candidates(
    client: OpenAI,
    *,
    model: str,
    persona: memory_audit.PersonaSpec,
    transcript: List[Dict[str, str]],
    search_output: Dict[str, Any],
) -> SatisfactionResult:
    prompt = f"""你继续扮演这个真实用户，并以“本人视角”判断红娘推荐的人选是否满意。

你的真实 persona：
{persona.role_brief}

你和红娘刚才的对话：
{memory_audit.format_transcript(transcript)}

红娘给出的候选结果：
{search_output['output']}

要求：
1. 只按你本人的真实偏好判断，不要替系统找理由。
2. 每个候选人给 1-10 分。
3. `verdict` 只能填：愿意继续聊 / 观望 / 不考虑。
4. `overall_verdict` 只能填：满意 / 部分满意 / 不满意。
5. `satisfied` 只有在至少有一个人你明确愿意继续聊，而且没有明显踩中核心雷点时才填 true。
6. 如果没有匹配到人，也要说明为什么不满意。"""
    response = client.responses.parse(
        model=model,
        input=prompt,
        temperature=0,
        max_output_tokens=1400,
        text_format=SatisfactionResult,
    )
    return response.output_parsed


def build_feedback_entry(
    *,
    persona_id: str,
    display_name: str,
    satisfaction: SatisfactionResult,
    search_output: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "persona_id": persona_id,
        "display_name": display_name,
        "overall_verdict": satisfaction.overall_verdict,
        "overall_summary": satisfaction.overall_summary,
        "satisfied": satisfaction.satisfied,
        "concerns": satisfaction.concerns,
        "has_match": search_output["has_match"],
        "candidate_reviews": [review.model_dump() for review in satisfaction.candidate_reviews],
    }


def summarize_journey_results(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    completed = [item for item in results if "review" in item and "search" in item and "satisfaction" in item]
    drift_count = sum(len(item["review"]["drift"]) for item in completed)
    privacy_count = sum(len(item["review"]["do_not_public"]) for item in completed)
    high_risk_count = sum(1 for item in completed if item["review"]["risk_level"] == "high")
    satisfied_count = sum(1 for item in completed if item["satisfaction"]["satisfied"])
    partial_count = sum(1 for item in completed if item["satisfaction"]["overall_verdict"] == "部分满意")
    no_match_count = sum(1 for item in completed if not item["search"]["has_match"])
    return {
        "persona_count": len(results),
        "completed_count": len(completed),
        "error_count": len(results) - len(completed),
        "drift_count": drift_count,
        "privacy_count": privacy_count,
        "high_risk_count": high_risk_count,
        "satisfied_count": satisfied_count,
        "partial_satisfaction_count": partial_count,
        "no_match_count": no_match_count,
    }


def render_markdown_report(report: Dict[str, Any]) -> str:
    lines = [
        f"# Matchmaking Journey Audit {report['run_label']}",
        "",
        "## Summary",
        "",
        f"- persona_count: {report['summary']['persona_count']}",
        f"- completed_count: {report['summary']['completed_count']}",
        f"- error_count: {report['summary']['error_count']}",
        f"- drift_count: {report['summary']['drift_count']}",
        f"- privacy_count: {report['summary']['privacy_count']}",
        f"- high_risk_count: {report['summary']['high_risk_count']}",
        f"- satisfied_count: {report['summary']['satisfied_count']}",
        f"- partial_satisfaction_count: {report['summary']['partial_satisfaction_count']}",
        f"- no_match_count: {report['summary']['no_match_count']}",
        "",
    ]
    for result in report["results"]:
        lines.extend(
            [
                f"## {result['persona_id']} {result['display_name']}",
                "",
                "### Role Brief",
                "",
                result["role_brief"],
                "",
                "### Private Boundaries",
                "",
            ]
        )
        for item in result["private_boundaries"]:
            lines.append(f"- {item}")
        lines.extend(["", "### Transcript", ""])
        for turn in result["transcript"]:
            lines.append(f"- {turn['speaker']}: {turn['text']}")
        if result.get("error"):
            lines.extend(["", "### Error", "", result["error"], ""])
            continue
        lines.extend(
            [
                "",
                "### Extraction",
                "",
                "```json",
                json.dumps(result["extraction"], ensure_ascii=False, indent=2),
                "```",
                "",
                "### Snapshot",
                "",
                "```json",
                json.dumps(result["snapshot"], ensure_ascii=False, indent=2),
                "```",
                "",
                "### Persona Review",
                "",
                "```json",
                json.dumps(result["review"], ensure_ascii=False, indent=2),
                "```",
                "",
                "### Search Command",
                "",
                "```bash",
                " ".join(result["search"]["command"]),
                "```",
                "",
                "### Search Output",
                "",
                "```text",
                result["search"]["output"],
                "```",
                "",
                "### Satisfaction",
                "",
                "```json",
                json.dumps(result["satisfaction"], ensure_ascii=False, indent=2),
                "```",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    args = parse_args()
    run_label = args.run_label or datetime.now().strftime("%Y%m%d_%H%M%S")
    personas_path = Path(args.personas_file).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    source = memory_audit.resolve_mysql_source(args.source)
    search_source = args.search_source or source
    persona_model = args.persona_model or args.model
    analysis_model = args.analysis_model or args.model
    selected_ids = {item.strip() for item in (args.persona_ids or "").split(",") if item.strip()} or None

    memory_audit.ensure_schema(source)
    personas = memory_audit.load_personas(personas_path, selected_ids, args.max_personas)
    profile_ids = memory_audit.allocate_profile_ids(source, len(personas))
    client = OpenAI(timeout=args.api_timeout, max_retries=args.max_retries)
    started_at = datetime.now().isoformat(timespec="seconds")
    results: List[Dict[str, Any]] = []
    feedback_entries: List[Dict[str, Any]] = []

    for index, (persona, profile_id) in enumerate(zip(personas, profile_ids), start=1):
        print(
            f"[{index:02d}/{len(personas):02d}] auditing matchmaking journey for {persona.id} {persona.display_name}",
            file=sys.stderr,
        )
        user_key = memory_audit.build_user_key(run_label, persona.id)
        transcript: List[Dict[str, str]] = []
        try:
            for prompt in memory_audit.INTERVIEWER_PROMPTS:
                transcript.append({"speaker": "matchmaker", "text": prompt})
                reply = memory_audit.persona_reply(
                    client,
                    model=persona_model,
                    persona=persona,
                    transcript=transcript,
                    temperature=args.temperature,
                )
                transcript.append({"speaker": "persona", "text": reply})

            extraction = memory_audit.extract_patches(client, model=analysis_model, transcript=transcript)
            explicit_patch = memory_audit.prune_none(extraction.explicit_patch.model_dump(exclude_none=True))
            explicit_patch.update(persona.seed_patch)
            explicit_patch["display_name"] = persona.display_name
            explicit_patch["profile_id"] = profile_id

            strong_inference_patch = memory_audit.filter_strong_inference_patch(
                memory_audit.prune_none(extraction.strong_inference_patch.model_dump(exclude_none=True))
            )
            conversation_ref = f"matchmaking-journey/{run_label}/{persona.id}"

            explicit_result = memory_audit.apply_persona_patch(
                source=source,
                user_key=user_key,
                profile_id=profile_id,
                display_name=persona.display_name,
                source_type="explicit",
                patch=explicit_patch,
                evidence_text=extraction.explicit_evidence or "matchmaking journey explicit extraction",
                confidence_score=96,
                conversation_ref=conversation_ref,
            )
            inference_result = None
            if strong_inference_patch:
                inference_result = memory_audit.apply_persona_patch(
                    source=source,
                    user_key=user_key,
                    profile_id=profile_id,
                    display_name=persona.display_name,
                    source_type="strong_inference",
                    patch=strong_inference_patch,
                    evidence_text=extraction.strong_inference_evidence or "matchmaking journey strong inference extraction",
                    confidence_score=84,
                    conversation_ref=conversation_ref,
                )

            public_render = refresh_public_profile(source, user_key=user_key)
            snapshot = fetch_full_snapshot(
                source,
                user_key=user_key,
                profile_id=profile_id,
                private_boundaries=persona.private_boundaries,
            )
            review = memory_audit.review_snapshot(
                client,
                model=analysis_model,
                persona=persona,
                transcript=transcript,
                snapshot=snapshot,
            )

            persona_row = fetch_persona_row(source, user_key=user_key)
            search_command = build_search_command(
                persona_row=persona_row,
                profile_id=profile_id,
                search_source=search_source,
                candidate_limit=args.candidate_limit,
                photo_preview_count=args.photo_preview_count,
                active_within_days=args.active_within_days,
                verified_level_min=args.verified_level_min,
            )
            search_output = run_search(search_command)
            satisfaction = review_candidates(
                client,
                model=analysis_model,
                persona=persona,
                transcript=transcript,
                search_output=search_output,
            )
            feedback_entry = build_feedback_entry(
                persona_id=persona.id,
                display_name=persona.display_name,
                satisfaction=satisfaction,
                search_output=search_output,
            )
            feedback_entries.append(feedback_entry)

            results.append(
                {
                    "persona_id": persona.id,
                    "display_name": persona.display_name,
                    "user_key": user_key,
                    "profile_id": profile_id,
                    "role_brief": persona.role_brief,
                    "private_boundaries": persona.private_boundaries,
                    "transcript": transcript,
                    "extraction": {
                        "explicit_patch": explicit_result["normalized_patch"],
                        "strong_inference_patch": inference_result["normalized_patch"] if inference_result else {},
                        "explicit_evidence": extraction.explicit_evidence,
                        "strong_inference_evidence": extraction.strong_inference_evidence,
                    },
                    "public_render": public_render,
                    "snapshot": snapshot,
                    "review": review.model_dump(),
                    "search": search_output,
                    "satisfaction": satisfaction.model_dump(),
                }
            )
        except Exception as exc:
            results.append(
                {
                    "persona_id": persona.id,
                    "display_name": persona.display_name,
                    "user_key": user_key,
                    "profile_id": profile_id,
                    "role_brief": persona.role_brief,
                    "private_boundaries": persona.private_boundaries,
                    "transcript": transcript,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            if args.fail_fast:
                raise

    report = {
        "run_label": run_label,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "started_at": started_at,
        "personas_file": str(personas_path),
        "source": source,
        "search_source": search_source,
        "persona_model": persona_model,
        "analysis_model": analysis_model,
        "summary": summarize_journey_results(results),
        "feedback_metrics": feedback_metrics,
        "results": results,
    }

    report_path = output_dir / f"matchmaking_journey_report_{run_label}.json"
    packets_path = output_dir / f"matchmaking_journey_packets_{run_label}.md"
    feedback_path = output_dir / f"matchmaking_journey_feedback_{run_label}.json"
    feedback_metrics_path = output_dir / f"matchmaking_journey_feedback_metrics_{run_label}.json"
    feedback_metrics = summarize_agent_feedback.summarize_feedback(
        feedback_entries,
        feedback_path,
        label=run_label,
    )
    report["feedback_metrics"] = feedback_metrics

    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    packets_path.write_text(render_markdown_report(report), encoding="utf-8")
    feedback_path.write_text(json.dumps(feedback_entries, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summarize_agent_feedback.write_json(feedback_metrics_path, feedback_metrics)

    print(f"[matchmaking-journey] wrote {report_path}", file=sys.stderr)
    print(f"[matchmaking-journey] wrote {packets_path}", file=sys.stderr)
    print(f"[matchmaking-journey] wrote {feedback_path}", file=sys.stderr)
    print(f"[matchmaking-journey] wrote {feedback_metrics_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
