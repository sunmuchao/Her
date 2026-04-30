#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from openai import OpenAI
from pydantic import BaseModel, Field


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from persona_memory_lib import (  # noqa: E402
    DEFAULT_OBSERVATION_TABLE,
    DEFAULT_PERSONA_TABLE,
    build_profile_payload,
    insert_profile_stub,
    income_wan_to_range,
    mark_profile_sync_results,
    merge_persona,
    mysql_connect,
    normalize_patch,
    now_string,
    profile_columns_for_persona_patch,
    quote_mysql_ident,
    resolve_mysql_source,
)
from upsert_persona_memory import (  # noqa: E402
    fetch_persona,
    insert_observations,
    upsert_persona,
    upsert_profile,
)


DEFAULT_PERSONAS_FILE = SCRIPT_DIR.parent / "references" / "audit_personas.json"
DEFAULT_MODEL = os.environ.get("OPENAI_MODEL") or "gpt-4.1-mini"

INTERVIEWER_PROMPTS = [
    "先简单了解你一下：你现在多大、做什么、平时生活节奏怎么样，这次想找什么样的关系？",
    "我把匹配条件记细一点：你现在婚姻情况怎样，平时抽烟喝酒吗？更倾向找多大、在哪些城市、哪些生活方式的人？",
    "再问细一点：你最看重对方哪几个特质，最不能接受哪几类人？哪些条件是硬边界，哪些只是更匹配？",
    "最后确认一下：哪些信息你接受后台长期记住做匹配，但不希望在公开资料里直接展示？如果系统写错或写重了，你最在意哪类偏差？",
]

STRONG_INFERENCE_FIELDS = {
    "must_have_tags",
    "must_not_have_tags",
    "preferred_traits",
    "disliked_traits",
    "persona_summary_internal",
    "preference_summary_internal",
    "public_profile_summary_draft",
    "public_preference_summary_draft",
}

PERSONA_SNAPSHOT_FIELDS = [
    "display_name",
    "self_gender",
    "self_age",
    "self_city",
    "self_education",
    "self_income_wan",
    "self_job",
    "self_marital_status",
    "self_has_children",
    "self_smoking",
    "self_drinking",
    "self_relationship_goal",
    "target_gender",
    "target_age_min",
    "target_age_max",
    "target_cities",
    "target_height_min",
    "target_height_max",
    "target_education_min",
    "target_marital_statuses",
    "target_marital_status_strength",
    "target_accept_partner_children",
    "target_accept_partner_children_strength",
    "target_accept_long_distance",
    "must_have_tags",
    "must_not_have_tags",
    "preferred_traits",
    "disliked_traits",
    "persona_summary_internal",
    "preference_summary_internal",
    "public_profile_summary_draft",
    "public_preference_summary_draft",
]

PROFILE_SNAPSHOT_FIELDS = [
    "id",
    "name",
    "gender",
    "age",
    "city",
    "education",
    "public_education",
    "job",
    "public_job",
    "income_range",
    "relationship_goal",
    "drinking",
    "smoking",
    "preferred_education_min",
    "accept_marital_status",
    "accept_marital_status_strength",
    "accept_marital_status_semantics",
    "accept_partner_children",
    "accept_partner_children_strength",
    "accept_partner_children_semantics",
    "personality",
    "values",
    "notes",
    "matcher_summary_internal",
    "public_personality",
    "public_values",
    "public_notes",
]

PUBLIC_VIEW_SNAPSHOT_FIELDS = [
    "id",
    "name",
    "gender",
    "age",
    "city",
    "education",
    "job",
    "income_range",
    "relationship_goal",
    "personality",
    "values",
    "notes",
]


class PersonaPatchModel(BaseModel):
    display_name: Optional[str] = None
    self_gender: Optional[str] = None
    self_age: Optional[int] = None
    self_city: Optional[str] = None
    self_district: Optional[str] = None
    self_height: Optional[int] = None
    self_education: Optional[str] = None
    self_income_wan: Optional[int] = None
    self_job: Optional[str] = None
    self_marital_status: Optional[str] = None
    self_has_children: Optional[bool] = None
    self_smoking: Optional[str] = None
    self_drinking: Optional[str] = None
    self_relationship_goal: Optional[str] = None
    target_gender: Optional[str] = None
    target_age_min: Optional[int] = None
    target_age_max: Optional[int] = None
    target_cities: Optional[List[str]] = None
    target_height_min: Optional[int] = None
    target_height_max: Optional[int] = None
    target_education_min: Optional[str] = None
    target_income_min_wan: Optional[int] = None
    target_income_max_wan: Optional[int] = None
    target_marital_statuses: Optional[List[str]] = None
    target_marital_status_strength: Optional[str] = None
    target_accept_partner_children: Optional[str] = None
    target_accept_partner_children_strength: Optional[str] = None
    target_accept_long_distance: Optional[str] = None
    target_want_children: Optional[str] = None
    target_marriage_timeline: Optional[str] = None
    must_have_tags: Optional[List[str]] = None
    must_not_have_tags: Optional[List[str]] = None
    preferred_traits: Optional[List[str]] = None
    disliked_traits: Optional[List[str]] = None
    persona_summary_internal: Optional[str] = None
    preference_summary_internal: Optional[str] = None
    public_profile_summary_draft: Optional[str] = None
    public_preference_summary_draft: Optional[str] = None


class ExtractionResult(BaseModel):
    explicit_patch: PersonaPatchModel
    strong_inference_patch: PersonaPatchModel
    explicit_evidence: str = Field(default="")
    strong_inference_evidence: str = Field(default="")


class ReviewResult(BaseModel):
    accurate: List[str] = Field(default_factory=list)
    drift: List[str] = Field(default_factory=list)
    do_not_public: List[str] = Field(default_factory=list)
    summary: str = Field(default="")
    risk_level: str = Field(default="medium")


class PersonaSpec(BaseModel):
    id: str
    display_name: str
    role_brief: str
    private_boundaries: List[str] = Field(default_factory=list)
    seed_patch: Dict[str, Any] = Field(default_factory=dict)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="One-click persona-memory-sync audit: roleplay, persist, render, and review.",
    )
    parser.add_argument(
        "--personas-file",
        default=str(DEFAULT_PERSONAS_FILE),
        help="JSON file describing the audit personas.",
    )
    parser.add_argument(
        "--source",
        default=None,
        help="MySQL DSN. Defaults to PERSONA_MEMORY_MYSQL_SOURCE.",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help="Model used for all calls unless overridden.",
    )
    parser.add_argument(
        "--persona-model",
        default=None,
        help="Model used for roleplay replies. Defaults to --model.",
    )
    parser.add_argument(
        "--analysis-model",
        default=None,
        help="Model used for extraction and review. Defaults to --model.",
    )
    parser.add_argument(
        "--output-dir",
        default=".",
        help="Directory for the JSON and Markdown reports.",
    )
    parser.add_argument(
        "--run-label",
        default=None,
        help="Optional stable run label. Defaults to the current timestamp.",
    )
    parser.add_argument(
        "--max-personas",
        type=int,
        default=None,
        help="Only run the first N personas from the input file.",
    )
    parser.add_argument(
        "--persona-ids",
        default=None,
        help="Comma-separated subset of persona ids to run.",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.8,
        help="Temperature used for roleplay replies.",
    )
    parser.add_argument(
        "--api-timeout",
        type=float,
        default=90.0,
        help="OpenAI API timeout in seconds.",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=4,
        help="OpenAI client retry count.",
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop immediately when one persona run fails.",
    )
    return parser.parse_args()


def ensure_schema(source: str) -> None:
    subprocess.run(
        [sys.executable, str(SCRIPT_DIR / "ensure_persona_tables.py"), "--source", source],
        check=True,
    )


def load_personas(path: Path, persona_ids: Optional[set[str]], max_personas: Optional[int]) -> List[PersonaSpec]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    personas = [PersonaSpec.model_validate(item) for item in payload]
    if persona_ids:
        personas = [persona for persona in personas if persona.id in persona_ids]
    if max_personas is not None:
        personas = personas[:max_personas]
    if not personas:
        raise ValueError("No personas selected for the audit run.")
    return personas


def build_user_key(run_label: str, persona_id: str) -> str:
    return f"pma_{run_label}_{persona_id}"


def allocate_profile_ids(source: str, count: int) -> List[int]:
    conn = mysql_connect(source)
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT COALESCE(MAX(id), 0) AS max_id FROM `profiles`")
            max_id = int(cursor.fetchone()["max_id"] or 0)
    finally:
        conn.close()
    return [max_id + offset for offset in range(1, count + 1)]


def format_transcript(transcript: List[Dict[str, str]]) -> str:
    return "\n".join(f"{item['speaker']}: {item['text']}" for item in transcript)


def prune_none(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: prune_none(v) for k, v in value.items() if v not in (None, [], {}, "")}
    if isinstance(value, list):
        return [prune_none(item) for item in value if item not in (None, [], {}, "")]
    return value


def mentions_income_privacy(private_boundaries: Optional[Iterable[str]]) -> bool:
    for boundary in private_boundaries or []:
        text = str(boundary).strip()
        if not text:
            continue
        if any(keyword in text for keyword in ("收入", "薪资", "薪水", "工资")):
            return True
    return False


def mask_snapshot_for_review(snapshot: Dict[str, Any], private_boundaries: Optional[Iterable[str]]) -> Dict[str, Any]:
    masked = deepcopy(snapshot)
    if mentions_income_privacy(private_boundaries):
        persona_row = masked.get("user_persona") or {}
        exact_income = persona_row.pop("self_income_wan", None)
        if exact_income is not None:
            income_range = income_wan_to_range(exact_income)
            if income_range:
                persona_row["self_income_range"] = income_range
    return masked


def persona_reply(
    client: OpenAI,
    *,
    model: str,
    persona: PersonaSpec,
    transcript: List[Dict[str, str]],
    temperature: float,
) -> str:
    prompt = f"""你在扮演一个真实感很强的相亲用户，只能用中文交流。

固定 persona：
{persona.role_brief}

不想公开暴露的信息：
{json.dumps(persona.private_boundaries, ensure_ascii=False)}

规则：
1. 只以用户口吻回答，不要解释规则。
2. 信息要逐步透露，不要一次性全说完。
3. 说法自然，不要像填表。
4. 如果某个问题过细，你可以保留一点，但不要直接拒绝整段对话。
5. 单轮尽量控制在 60-140 个汉字。

当前对话：
{format_transcript(transcript)}

请只回复这轮用户会说的话。"""
    response = client.responses.create(
        model=model,
        input=prompt,
        temperature=temperature,
        max_output_tokens=220,
    )
    return (response.output_text or "").strip()


def extract_patches(
    client: OpenAI,
    *,
    model: str,
    transcript: List[Dict[str, str]],
) -> ExtractionResult:
    prompt = f"""你是 persona-memory-sync 的画像抽取器。

任务：只根据下面的真实对话，产出两份 patch：
1. explicit_patch：只放用户明确说过的事实或边界。
2. strong_inference_patch：只放高置信的软总结和公开草稿。

关键规则：
- 绝对不要用对话之外的信息。
- `explicit_patch` 允许硬字段，如年龄、城市、学历、婚况、抽烟喝酒、目标年龄/城市、接受度边界。
- `strong_inference_patch` 只允许这些字段：must_have_tags, must_not_have_tags, preferred_traits, disliked_traits, persona_summary_internal, preference_summary_internal, public_profile_summary_draft, public_preference_summary_draft。
- 如果用户说“更匹配一点，但不是硬门槛”，不要把它写进硬门槛字段。
- 如果用户只给了区间、约数或模糊表达，不要补成更精确的值；例如收入只说“大概 35-40”，就不要写成 38。
- `self_smoking` / `self_drinking` 不要过度标准化；如果用户说“基本不喝”“极少量社交饮酒”，优先保留这个粒度，不要直接写成“偶尔”。
- 如果用户说“接受度偏低/偏谨慎”，可以把 `target_accept_partner_children_strength` 或 `target_marital_status_strength` 写到 `explicit_patch`。
- 如果婚史或对子女是“可以聊、但明显偏保守/更看具体相处”，优先把强度写成 `谨慎接受`，不要轻易写成 `短期可聊`。
- 如果用户说“现阶段不太接受对方已有孩子 / 优先不考虑对方有孩子 / 偏谨慎但不是绝对封死”，`target_accept_partner_children` 优先写 `现阶段不太接受`，不要默认放宽成普通 `可协商`，也不要直接写死成 `不接受`；只有用户明确表达“完全不接受”时才写 `不接受`。
- 不要从“现居上海/苏州/无锡”这类信息推断成“上海本地人/苏州本地人/无锡本地人”。
- `public_*` 草稿不要写成“1-2年内结婚导向”“2年内再婚导向”这类有时间压力的公开措辞，优先改写成“认真了解，合适会稳定推进/考虑结婚”。
- `public_*` 草稿必须克制，不能把用户明确说“不想公开”的内容写进去。
- 列表字段用数组；未提及就留空。

对话如下：
{format_transcript(transcript)}"""
    response = client.responses.parse(
        model=model,
        input=prompt,
        temperature=0,
        max_output_tokens=1200,
        text_format=ExtractionResult,
    )
    return response.output_parsed


def filter_strong_inference_patch(patch: Dict[str, Any]) -> Dict[str, Any]:
    return {key: value for key, value in patch.items() if key in STRONG_INFERENCE_FIELDS}


def apply_persona_patch(
    *,
    source: str,
    user_key: str,
    profile_id: int,
    display_name: str,
    source_type: str,
    patch: Dict[str, Any],
    evidence_text: str,
    confidence_score: int,
    conversation_ref: str,
    persona_table: str = DEFAULT_PERSONA_TABLE,
    observation_table: str = DEFAULT_OBSERVATION_TABLE,
    profile_table: str = "profiles",
) -> Dict[str, Any]:
    normalized_patch = normalize_patch(patch)
    conn = mysql_connect(source)
    profile_synced = False
    field_results: List[Dict[str, Any]] = []
    try:
        with conn.cursor() as cursor:
            existing = fetch_persona(cursor, persona_table, user_key)
            base = dict(existing or {})
            base["user_key"] = user_key
            merged, field_results = merge_persona(base, normalized_patch, source_type)
            merged["user_key"] = user_key
            saved_persona = upsert_persona(cursor, persona_table, merged)

            if source_type != "weak_inference":
                current_profile_id = saved_persona.get("profile_id") or profile_id
                persona_for_profile = dict(saved_persona)
                persona_for_profile["user_key"] = user_key
                persona_for_profile["profile_id"] = current_profile_id
                if saved_persona.get("profile_id") is None:
                    initial_payload = build_profile_payload(persona_for_profile, existing_profile={})
                    if current_profile_id is None:
                        current_profile_id = insert_profile_stub(cursor, profile_table, initial_payload)
                    else:
                        cursor.execute(
                            f"""
                            INSERT IGNORE INTO {quote_mysql_ident(profile_table)}
                              (id, name, profile_status, verified_level, source_channel, last_active_at)
                            VALUES (%s, %s, %s, %s, %s, %s)
                            """,
                            (
                                current_profile_id,
                                initial_payload["name"],
                                initial_payload["profile_status"],
                                initial_payload["verified_level"],
                                initial_payload["source_channel"],
                                initial_payload["last_active_at"],
                            ),
                        )
                    cursor.execute(
                        f"UPDATE {quote_mysql_ident(persona_table)} SET profile_id = %s WHERE id = %s",
                        (current_profile_id, saved_persona["id"]),
                    )
                    saved_persona["profile_id"] = current_profile_id
                    persona_for_profile["profile_id"] = current_profile_id

                cursor.execute(
                    f"SELECT * FROM {quote_mysql_ident(profile_table)} WHERE id = %s",
                    (saved_persona["profile_id"],),
                )
                existing_profile = cursor.fetchone() or {}
                payload = build_profile_payload(
                    persona_for_profile,
                    existing_profile=existing_profile,
                    include_null_persona_fields=normalized_patch.keys(),
                )
                upsert_profile(
                    cursor,
                    profile_table,
                    payload,
                    saved_persona["profile_id"],
                    force_columns=profile_columns_for_persona_patch(normalized_patch),
                )
                profile_synced = True

            mark_profile_sync_results(field_results, synced_profile=profile_synced)
            insert_observations(
                cursor=cursor,
                observation_table=observation_table,
                user_key=user_key,
                persona_id=saved_persona["id"],
                source_type=source_type,
                confidence_score=confidence_score,
                evidence_text=evidence_text,
                conversation_ref=conversation_ref,
                field_results=field_results,
            )

        conn.commit()
    finally:
        conn.close()

    return {
        "user_key": user_key,
        "source_type": source_type,
        "profile_id": profile_id,
        "display_name": display_name,
        "applied_fields": [item for item in field_results if item["applied_to_persona"]],
        "skipped_fields": [item for item in field_results if not item["applied_to_persona"]],
        "synced_profile": profile_synced,
        "normalized_patch": normalized_patch,
    }


def fetch_snapshot(
    source: str,
    *,
    user_key: str,
    profile_id: int,
    private_boundaries: Optional[Iterable[str]] = None,
    persona_table: str = DEFAULT_PERSONA_TABLE,
    profile_table: str = "profiles",
    public_view: str = "public_profile_view",
) -> Dict[str, Any]:
    conn = mysql_connect(source)
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                f"SELECT * FROM {quote_mysql_ident(persona_table)} WHERE user_key = %s",
                (user_key,),
            )
            persona_row = cursor.fetchone() or {}
            cursor.execute(
                f"SELECT * FROM {quote_mysql_ident(profile_table)} WHERE id = %s",
                (profile_id,),
            )
            profile_row = cursor.fetchone() or {}
            cursor.execute(
                f"SELECT * FROM {quote_mysql_ident(public_view)} WHERE id = %s",
                (profile_id,),
            )
            public_row = cursor.fetchone() or {}
    finally:
        conn.close()

    persona_excerpt = {field: persona_row.get(field) for field in PERSONA_SNAPSHOT_FIELDS}
    profile_excerpt = {field: profile_row.get(field) for field in PROFILE_SNAPSHOT_FIELDS}
    public_excerpt = {field: public_row.get(field) for field in PUBLIC_VIEW_SNAPSHOT_FIELDS}
    snapshot = {
        "user_persona": prune_none(persona_excerpt),
        "profile_internal": prune_none(profile_excerpt),
        "public_profile_view": prune_none(public_excerpt),
    }
    return mask_snapshot_for_review(snapshot, private_boundaries)


def review_snapshot(
    client: OpenAI,
    *,
    model: str,
    persona: PersonaSpec,
    transcript: List[Dict[str, str]],
    snapshot: Dict[str, Any],
) -> ReviewResult:
    prompt = f"""你现在切到“本人审核模式”。

你的真实 persona：
{persona.role_brief}

你明确不想公开暴露的内容：
{json.dumps(persona.private_boundaries, ensure_ascii=False)}

下面是你和系统的对话，以及系统最终写入/展示的摘录。
请按本人视角判断：
1. 哪些记录准确。
2. 哪些记录有偏差、写重了、或把软偏好写成了硬条件。
3. 哪些内容不应该公开展示。

对话：
{format_transcript(transcript)}

系统摘录：
{json.dumps(snapshot, ensure_ascii=False, indent=2)}

要求：
- `accurate`、`drift`、`do_not_public` 都用短句列表。
- `summary` 用 2-4 句总结最重要的问题。
- `risk_level` 只能填 low / medium / high。"""
    response = client.responses.parse(
        model=model,
        input=prompt,
        temperature=0,
        max_output_tokens=1200,
        text_format=ReviewResult,
    )
    return response.output_parsed


def summarize_reviews(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    completed = [item for item in results if "review" in item]
    drift_count = sum(len(item["review"]["drift"]) for item in completed)
    privacy_count = sum(len(item["review"]["do_not_public"]) for item in completed)
    high_risk_count = sum(1 for item in completed if item["review"]["risk_level"] == "high")
    return {
        "persona_count": len(results),
        "completed_count": len(completed),
        "error_count": len(results) - len(completed),
        "drift_count": drift_count,
        "privacy_count": privacy_count,
        "high_risk_count": high_risk_count,
    }


def render_markdown_report(report: Dict[str, Any]) -> str:
    lines = [
        f"# Persona Memory Audit {report['run_label']}",
        "",
        "## Summary",
        "",
        f"- persona_count: {report['summary']['persona_count']}",
        f"- completed_count: {report['summary']['completed_count']}",
        f"- error_count: {report['summary']['error_count']}",
        f"- drift_count: {report['summary']['drift_count']}",
        f"- privacy_count: {report['summary']['privacy_count']}",
        f"- high_risk_count: {report['summary']['high_risk_count']}",
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
            lines.extend(
                [
                    "",
                    "### Error",
                    "",
                    result["error"],
                    "",
                ]
            )
            continue
        lines.extend(
            [
                "",
                "### Explicit Patch",
                "",
                "```json",
                json.dumps(result["extraction"]["explicit_patch"], ensure_ascii=False, indent=2),
                "```",
                "",
                "### Strong Inference Patch",
                "",
                "```json",
                json.dumps(result["extraction"]["strong_inference_patch"], ensure_ascii=False, indent=2),
                "```",
                "",
                "### Snapshot",
                "",
                "```json",
                json.dumps(result["snapshot"], ensure_ascii=False, indent=2),
                "```",
                "",
                "### Review",
                "",
                "```json",
                json.dumps(result["review"], ensure_ascii=False, indent=2),
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

    source = resolve_mysql_source(args.source)
    persona_model = args.persona_model or args.model
    analysis_model = args.analysis_model or args.model
    selected_ids = {item.strip() for item in (args.persona_ids or "").split(",") if item.strip()} or None

    ensure_schema(source)
    personas = load_personas(personas_path, selected_ids, args.max_personas)
    profile_ids = allocate_profile_ids(source, len(personas))
    client = OpenAI(timeout=args.api_timeout, max_retries=args.max_retries)
    started_at = datetime.now().isoformat(timespec="seconds")
    results: List[Dict[str, Any]] = []

    for index, (persona, profile_id) in enumerate(zip(personas, profile_ids), start=1):
        print(f"[{index:02d}/{len(personas):02d}] auditing {persona.id} {persona.display_name}", file=sys.stderr)
        user_key = build_user_key(run_label, persona.id)
        transcript: List[Dict[str, str]] = []
        try:
            for prompt in INTERVIEWER_PROMPTS:
                transcript.append({"speaker": "matchmaker", "text": prompt})
                reply = persona_reply(
                    client,
                    model=persona_model,
                    persona=persona,
                    transcript=transcript,
                    temperature=args.temperature,
                )
                transcript.append({"speaker": "persona", "text": reply})

            extraction = extract_patches(client, model=analysis_model, transcript=transcript)
            explicit_patch = prune_none(extraction.explicit_patch.model_dump(exclude_none=True))
            explicit_patch.update(persona.seed_patch)
            explicit_patch["display_name"] = persona.display_name
            explicit_patch["profile_id"] = profile_id

            strong_inference_patch = filter_strong_inference_patch(
                prune_none(extraction.strong_inference_patch.model_dump(exclude_none=True))
            )

            conversation_ref = f"persona-memory-audit/{run_label}/{persona.id}"
            explicit_result = apply_persona_patch(
                source=source,
                user_key=user_key,
                profile_id=profile_id,
                display_name=persona.display_name,
                source_type="explicit",
                patch=explicit_patch,
                evidence_text=extraction.explicit_evidence or "audit roleplay explicit extraction",
                confidence_score=96,
                conversation_ref=conversation_ref,
            )
            inference_result = None
            if strong_inference_patch:
                inference_result = apply_persona_patch(
                    source=source,
                    user_key=user_key,
                    profile_id=profile_id,
                    display_name=persona.display_name,
                    source_type="strong_inference",
                    patch=strong_inference_patch,
                    evidence_text=extraction.strong_inference_evidence or "audit roleplay strong inference extraction",
                    confidence_score=84,
                    conversation_ref=conversation_ref,
                )

            snapshot = fetch_snapshot(
                source,
                user_key=user_key,
                profile_id=profile_id,
                private_boundaries=persona.private_boundaries,
            )
            review = review_snapshot(
                client,
                model=analysis_model,
                persona=persona,
                transcript=transcript,
                snapshot=snapshot,
            )

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
                    "snapshot": snapshot,
                    "review": review.model_dump(),
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
        "persona_model": persona_model,
        "analysis_model": analysis_model,
        "summary": summarize_reviews(results),
        "results": results,
    }

    json_path = output_dir / f"persona_memory_audit_report_{run_label}.json"
    md_path = output_dir / f"persona_memory_audit_packets_{run_label}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown_report(report), encoding="utf-8")
    print(f"[persona-memory-audit] wrote {json_path}", file=sys.stderr)
    print(f"[persona-memory-audit] wrote {md_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
