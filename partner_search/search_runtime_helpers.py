from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any, Callable, Sequence

from her_json_utils import json_safe


PROFILE_FILTER_ARGUMENT_SPECS = [
    (("--gender",), {"help": "Filter by gender."}),
    (("--age-min",), {"type": int, "help": "Minimum age."}),
    (("--age-max",), {"type": int, "help": "Maximum age."}),
    (("--height-min",), {"type": int, "help": "Minimum height in cm."}),
    (("--height-max",), {"type": int, "help": "Maximum height in cm."}),
    (("--city",), {"action": "append", "help": "Allowed city. Repeat or use comma-separated values."}),
    (("--district",), {"action": "append", "help": "Allowed district. Repeat or use comma-separated values."}),
    (
        ("--settlement-city",),
        {"action": "append", "help": "Allowed long-term settlement city. Repeat or use comma-separated values."},
    ),
    (
        ("--relationship-goal",),
        {"action": "append", "help": "Allowed relationship goal. Repeat or use comma-separated values."},
    ),
    (("--must-have",), {"action": "append", "help": "Required keyword. Repeat or use comma-separated values."}),
    (("--must-not-have",), {"action": "append", "help": "Excluded keyword. Repeat or use comma-separated values."}),
    (("--prefer",), {"action": "append", "help": "Preferred keyword. Repeat or use comma-separated values."}),
    (
        ("--require-known",),
        {
            "action": "append",
            "help": (
                "Require these fields to be explicitly filled instead of missing. "
                "Repeat or use comma-separated canonical field names such as smoking,want_children,accept_partner_children."
            ),
        },
    ),
    (("--smoking",), {"help": "Exact smoking preference, for example 否."}),
    (("--drinking",), {"help": "Exact drinking preference, for example 否."}),
    (("--long-distance",), {"help": "Exact long-distance preference, for example 不接受."}),
    (("--housing-status",), {"action": "append", "help": "Allowed housing status. Repeat or use comma-separated values."}),
    (("--car-status",), {"action": "append", "help": "Allowed car status. Repeat or use comma-separated values."}),
    (("--marital-status",), {"action": "append", "help": "Allowed candidate marital status. Repeat or use comma-separated values."}),
    (("--has-children",), {"type": int, "choices": [0, 1], "help": "Filter whether the candidate has children."}),
    (("--want-children",), {"help": "Candidate child plan, for example 想要 or 可协商."}),
    (
        ("--accept-partner-children",),
        {"help": "Candidate acceptance of a partner who already has children."},
    ),
    (
        ("--accept-marital-status-strength",),
        {"help": "Required candidate marital-history acceptance strength, for example 明确接受."},
    ),
    (
        ("--accept-partner-children-strength",),
        {"help": "Required candidate child-acceptance strength, for example 明确接受."},
    ),
    (
        ("--marriage-timeline",),
        {"action": "append", "help": "Allowed marriage timeline. Repeat or use comma-separated values."},
    ),
]


QUALITY_ARGUMENT_SPECS = [
    (
        ("--profile-status",),
        {"action": "append", "help": "Allowed profile status. Defaults to active. Repeat or use comma-separated values."},
    ),
    (("--active-within-days",), {"type": int, "help": "Require recent activity within N days."}),
    (
        ("--verified-level-min",),
        {"choices": ["none", "basic", "photo", "id", "offline"], "help": "Minimum verification level."},
    ),
    (
        ("--verified-level",),
        {"action": "append", "help": "Exact allowed verification level. Repeat or use comma-separated values."},
    ),
    (
        ("--photo-verification-level-min",),
        {
            "choices": ["none", "uploaded", "human_verified", "live_video_verified", "offline_verified"],
            "help": "Minimum required photo verification level.",
        },
    ),
    (
        ("--photo-verification-level",),
        {
            "action": "append",
            "help": "Exact allowed photo verification level. Repeat or use comma-separated values.",
        },
    ),
    (("--photo-count-min",), {"type": int, "help": "Minimum required photo count."}),
    (
        ("--photo-preview-count",),
        {
            "type": int,
            "default": 0,
            "help": "Return the top N photo URLs from the MySQL photos table for each result.",
        },
    ),
    (
        ("--photos-table",),
        {
            "help": "MySQL photos table name when not using the default profile_photos or DSN photos_table query param.",
        },
    ),
]


SELF_PROFILE_ARGUMENT_SPECS = [
    (("--self-id",), {"type": int, "help": "Use an existing profile id as your own profile for reciprocal matching."}),
    (("--self-age",), {"type": int, "help": "Your age for reciprocal matching."}),
    (("--self-city",), {"help": "Your city for reciprocal matching."}),
    (("--self-height",), {"type": int, "help": "Your height in cm for reciprocal matching."}),
    (("--self-education",), {"help": "Your education for reciprocal matching."}),
    (("--self-job",), {"help": "Your job for contextual matching, for example 医生 or 金融."}),
    (("--self-income-wan",), {"type": int, "help": "Your annual income in 万 for reciprocal matching."}),
    (("--self-marital-status",), {"help": "Your marital status for reciprocal matching."}),
    (("--self-has-children",), {"type": int, "choices": [0, 1], "help": "Whether you have children for reciprocal matching."}),
    (("--self-smoking",), {"help": "Your smoking habit for reciprocal matching."}),
    (("--self-drinking",), {"help": "Your drinking habit for reciprocal matching."}),
]


OUTPUT_ARGUMENT_SPECS = [
    (("--exclude-id",), {"action": "append", "type": int, "help": "Profile id to exclude from results. Repeatable."}),
    (
        ("--exclude-source-channel",),
        {
            "action": "append",
            "help": "Profile source_channel to exclude from results. Repeatable or comma-separated.",
        },
    ),
    (
        ("--show-source",),
        {"action": "store_true", "help": "Include the redacted source DSN and table in the text output for debugging."},
    ),
    (
        ("--output-format",),
        {
            "choices": ["text", "json"],
            "default": "text",
            "help": "Render human-readable text or structured JSON output.",
        },
    ),
    (("--limit",), {"type": int, "default": 10, "help": "Maximum number of results to return."}),
]


@dataclass(frozen=True)
class SearchRuntime:
    signal_field_specs: Sequence[tuple[str, str]]
    default_mysql_source: str | None
    as_int: Callable[[Any], int | None]
    default_source_help_text: Callable[[], str]
    normalize_request_criteria: Callable[[Any], dict[str, Any]]
    normalize_self_profile_input: Callable[[Any], dict[str, Any] | None]
    build_criteria_from_args: Callable[[Any], dict[str, Any]]
    build_self_profile_input_from_args: Callable[[Any], dict[str, Any]]
    load_source: Callable[..., list[dict[str, Any]]]
    iter_source_batches: Callable[..., Any] | None
    overlay_records_with_moderation: Callable[..., list[dict[str, Any]]]
    evaluate_candidate: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any] | None]
    result_sort_key: Callable[[dict[str, Any]], Any]
    select_diverse_results: Callable[[list[dict[str, Any]], int], list[dict[str, Any]]]
    build_self_profile: Callable[..., dict[str, Any] | None]
    record_ref: Callable[[dict[str, Any] | None], Any]
    build_fallback_candidates: Callable[..., list[dict[str, Any]]]
    build_no_match_diagnostics: Callable[..., dict[str, Any]]
    attach_photo_previews: Callable[..., None]
    attach_photo_features: Callable[..., None]
    load_user_appearance_preference: Callable[..., dict[str, Any] | None]
    effective_activity_info: Callable[[dict[str, Any]], tuple[str | None, Any]]
    effective_activity_datetime: Callable[[dict[str, Any]], Any]
    format_datetime: Callable[[Any], str | None]
    build_trust_summary: Callable[..., dict[str, Any]]
    summarize_notes: Callable[..., Any]
    build_verification_items: Callable[[dict[str, Any]], list[dict[str, Any]]]
    activity_score_info: Callable[[dict[str, Any]], tuple[Any, Any]]
    redact_source_ref: Callable[[str], str]
    format_no_match_text: Callable[..., str]


class SearchRuntimeHelpers:
    def __init__(self, runtime: SearchRuntime) -> None:
        self.runtime = runtime

    def summarize_signal_parts(self, profile, limit=8):
        parts = []
        for field, label in self.runtime.signal_field_specs:
            value = profile.get(field)
            if value:
                parts.append(f"{label}={value}")
            if len(parts) >= limit:
                break
        return parts

    def format_result_headline(self, result, profile):
        headline_parts = [f"{profile.get('age', '未知')}岁"]
        if profile.get("height") is not None:
            headline_parts.append(f"{profile.get('height')}cm")
        if profile.get("city"):
            headline_parts.append(profile.get("city"))
        else:
            headline_parts.append("城市未知")
        if profile.get("education"):
            headline_parts.append(profile.get("education"))
        headline_parts.append(profile.get("job", "工作未知"))
        return f"{result['index']}. {result['name']} | score={result['score']} | " + " | ".join(headline_parts)

    def format_result_scoring_line(self, result):
        return (
            "   scoring: "
            f"fit={result.get('fit_score', result['score'])} | "
            f"confidence={result.get('confidence_score', 0)} | "
            f"risk={result.get('risk_score', 0)}"
        )

    def build_result_meta_parts(self, profile):
        meta_parts = []
        if profile.get("profile_status"):
            meta_parts.append(f"status={profile.get('profile_status')}")
        if profile.get("verified_level"):
            meta_parts.append(f"verified={profile.get('verified_level')}")
        if profile.get("photo_count") is not None:
            meta_parts.append(f"photos={profile.get('photo_count')}")
        activity_field, activity_dt = self.runtime.effective_activity_info(profile)
        active_at = self.runtime.format_datetime(activity_dt)
        if activity_field and active_at:
            meta_parts.append(f"{activity_field}={active_at}")
        return meta_parts

    def append_labeled_line(self, lines, label, value):
        if value:
            lines.append(f"   {label}: {value}")

    def append_joined_line(self, lines, label, values, separator=", "):
        if values:
            lines.append(f"   {label}: {separator.join(values)}")

    def append_result_detail_lines(self, lines, result, profile, include_source=False):
        display_cache = self.prepare_result_display_cache(result)
        signal_parts = self.summarize_signal_parts(profile)
        self.append_labeled_line(lines, "match_tier", result.get("match_tier"))
        self.append_joined_line(lines, "compatibility_flags", result.get("compatibility_flags"))
        self.append_joined_line(lines, "signals", signal_parts, separator=" | ")
        self.append_labeled_line(lines, "trust", display_cache["trust_summary"].get("headline"))
        self.append_joined_line(lines, "photo_preview", result.get("photo_preview"))
        self.append_joined_line(lines, "matched_on", result["matched_on"])
        self.append_joined_line(lines, "reciprocal_on", result["reciprocal_on"])
        self.append_joined_line(lines, "missing_fields", result["missing_fields"])
        self.append_joined_line(lines, "self_profile_gaps", result.get("self_profile_gaps"))
        self.append_joined_line(lines, "risk_flags", result["risk_flags"])
        self.append_labeled_line(lines, "fallback_reason", result.get("fallback_reason"))
        self.append_joined_line(lines, "match_evidence", result.get("match_evidence"), separator=" | ")
        self.append_joined_line(lines, "follow_up_questions", result.get("follow_up_questions"), separator=" | ")
        if "display_notes" in result:
            notes_summary = result.get("display_notes")
        else:
            notes_summary = self.runtime.summarize_notes(profile.get("notes"))
        self.append_labeled_line(lines, "notes", notes_summary)
        if include_source and result.get("source_file"):
            self.append_labeled_line(lines, "source", self.runtime.redact_source_ref(result["source_file"]))

    def format_result_block(self, result, index, include_source=False):
        profile = result["profile"]
        lines = []
        display_result = dict(result)
        display_result["index"] = index
        lines.append(self.format_result_headline(display_result, profile))
        lines.append(self.format_result_scoring_line(display_result))
        meta_parts = self.build_result_meta_parts(profile)
        self.append_joined_line(lines, "meta", meta_parts, separator=" | ")
        self.append_result_detail_lines(lines, display_result, profile, include_source=include_source)
        return lines

    def format_text(self, results, include_source=False):
        lines = []
        for index, result in enumerate(results, start=1):
            lines.extend(self.format_result_block(result, index, include_source=include_source))
        return "\n".join(lines)

    def register_argument_specs(self, parser, specs):
        for flags, kwargs in specs:
            parser.add_argument(*flags, **kwargs)

    def build_source_argument_specs(self):
        return [
            (
                ("--source",),
                {
                    "action": "append",
                    "help": (
                        "MySQL DSN such as mysql://user:pass@host:3306/db?table=profiles. "
                        f"Repeatable. {self.runtime.default_source_help_text()}"
                    ),
                },
            ),
            (
                ("--table",),
                {
                    "help": "MySQL table name when the table is not included in the DSN.",
                },
            ),
        ]

    def add_source_arguments(self, parser):
        self.register_argument_specs(parser, self.build_source_argument_specs())

    def add_profile_filter_arguments(self, parser):
        self.register_argument_specs(parser, PROFILE_FILTER_ARGUMENT_SPECS)

    def add_quality_arguments(self, parser):
        self.register_argument_specs(parser, QUALITY_ARGUMENT_SPECS)

    def add_self_profile_arguments(self, parser):
        self.register_argument_specs(parser, SELF_PROFILE_ARGUMENT_SPECS)

    def add_output_arguments(self, parser):
        self.register_argument_specs(parser, OUTPUT_ARGUMENT_SPECS)

    def build_parser(self):
        parser = argparse.ArgumentParser(description="Search profile sources for partner candidates.")
        self.add_source_arguments(parser)
        self.add_profile_filter_arguments(parser)
        self.add_quality_arguments(parser)
        self.add_self_profile_arguments(parser)
        self.add_output_arguments(parser)
        return parser

    def build_search_request(
        self,
        source=None,
        sources=None,
        table_name=None,
        photos_table_name=None,
        persona_source=None,
        criteria=None,
        self_profile=None,
        self_id=None,
        requester_id=None,
        limit=10,
        photo_preview_count=0,
        moderation_dsn=None,
        include_moderation_blocked=False,
    ):
        request_sources = sources if sources is not None else source
        if request_sources is None:
            normalized_sources = []
        elif isinstance(request_sources, (list, tuple, set)):
            normalized_sources = [item for item in request_sources if item]
        else:
            normalized_sources = [request_sources]
        return {
            "sources": normalized_sources,
            "table_name": table_name,
            "photos_table_name": photos_table_name,
            "persona_source": persona_source,
            "criteria": self.runtime.normalize_request_criteria(criteria),
            "self_profile": self.runtime.normalize_self_profile_input(self_profile),
            "self_id": self.runtime.as_int(self_id),
            "requester_id": self.runtime.as_int(requester_id),
            "limit": self.runtime.as_int(limit) or 10,
            "photo_preview_count": self.runtime.as_int(photo_preview_count) or 0,
            "moderation_dsn": moderation_dsn,
            "include_moderation_blocked": bool(include_moderation_blocked),
        }

    def build_cli_self_profile_input(self, args):
        return self.runtime.build_self_profile_input_from_args(args)

    def build_search_request_from_args(self, args):
        return self.build_search_request(
            sources=args.source,
            table_name=args.table,
            photos_table_name=args.photos_table,
            persona_source=None,
            criteria=self.runtime.build_criteria_from_args(args),
            self_profile=self.build_cli_self_profile_input(args),
            self_id=args.self_id,
            requester_id=None,
            limit=args.limit,
            photo_preview_count=args.photo_preview_count,
        )

    def resolve_request_sources(self, request):
        sources = request.get("sources") or ([self.runtime.default_mysql_source] if self.runtime.default_mysql_source else [])
        if not sources:
            raise ValueError(
                "No profile source configured. Pass --source mysql://user:pass@host:3306/db?table=profiles "
                "or set PARTNER_SEARCH_MYSQL_SOURCE."
            )
        return sources

    def resolve_sources(self, args):
        return self.resolve_request_sources(self.build_search_request_from_args(args))

    def collect_source_records_for_request(self, sources, table_name=None, criteria=None, self_id=None):
        records = []
        include_ids = [self_id] if self_id is not None else []
        for source in sources:
            records.extend(
                self.runtime.load_source(
                    source,
                    table_name=table_name,
                    criteria=criteria,
                    include_ids=include_ids,
                )
            )
        return records

    def iter_source_record_batches(self, source, *, table_name=None, criteria=None, include_ids=None, include_ids_mode="or"):
        iter_source_batches = self.runtime.iter_source_batches
        if iter_source_batches is None:
            yield self.runtime.load_source(
                source,
                table_name=table_name,
                criteria=criteria,
                include_ids=include_ids,
                include_ids_mode=include_ids_mode,
            )
            return
        yield from iter_source_batches(
            source,
            table_name=table_name,
            criteria=criteria,
            include_ids=include_ids,
            include_ids_mode=include_ids_mode,
        )

    def collect_source_records(self, args, criteria, sources):
        return self.collect_source_records_for_request(
            sources,
            table_name=args.table,
            criteria=criteria,
            self_id=args.self_id,
        )

    def evaluate_records(self, records, criteria, limit):
        """并行评估候选记录。

        性能优化版本（升级版）：
        - 降低并行阈值（20 条即启用并行）
        - 提升最大线程数上限（最多 16 个线程）
        - 自适应批处理大小（根据记录数量动态调整）
        - 预计算 criteria 缓存避免线程安全问题
        """
        if not records:
            return []

        # 性能优化：预计算 criteria 缓存，避免并行执行时的竞态条件
        # 预计算 active_within_cutoff
        if criteria.get("active_within_days") is not None and "__active_within_cutoff" not in criteria:
            from datetime import datetime, timedelta
            criteria["__active_within_cutoff"] = datetime.now() - timedelta(days=criteria["active_within_days"])

        # 预计算 required_known_candidate_fields
        if "__required_known_candidate_fields" not in criteria:
            criteria["__required_known_candidate_fields"] = {
                field
                for field in criteria.get("required_known_fields", [])
                if not str(field).startswith("self_")
            }

        # 性能优化：提升并行阈值（从 20 改为 50），避免小批量线程创建开销
        # 小批量（<50条）使用串行更高效（避免线程池开销）
        if len(records) < 50:
            return self._evaluate_records_serial(records, criteria, limit)

        return self._evaluate_records_parallel(records, criteria, limit)

    def _evaluate_records_serial(self, records, criteria, limit):
        """串行评估（小批量使用）。"""
        results = []
        append_result = results.append
        evaluate_candidate = self.runtime.evaluate_candidate
        for record in records:
            evaluated = evaluate_candidate(record, criteria)
            if evaluated:
                append_result(evaluated)
        results.sort(key=self.runtime.result_sort_key, reverse=True)
        return self.runtime.select_diverse_results(results, limit)

    def _evaluate_records_parallel(self, records, criteria, limit):
        """并行评估（大批量使用，优化版）。

        性能优化：
        - 提升最大线程数上限（从 8 改为 16）
        - 自适应批处理大小（根据记录数量动态调整）
        - 更充分利用现代多核 CPU
        """
        import os

        # 根据 CPU 核心数和记录数量决定线程数
        cpu_count = os.cpu_count() or 4

        # 性能优化：自适应批处理大小，根据记录数量动态调整
        # 小批量（50-200）：批大小 50，细粒度并行（适合快速返回场景）
        # 中批量（200-1000）：批大小 100（平衡并行开销和吞吐）
        # 大批量（1000+）：批大小 200（减少线程创建开销，最大化吞吐）
        if len(records) < 200:
            batch_size = 50
        elif len(records) < 1000:
            batch_size = 100
        else:
            batch_size = 200

        # 性能优化：线程数上限保持 16（充分利用现代多核 CPU）
        # 线程数 = min(CPU核心数 * 2, 记录数 / 批大小, 16)
        max_workers = max(1, min(cpu_count * 2, len(records) // batch_size))
        max_workers = min(max_workers, 16)  # 上限保持 16

        results = []
        evaluate_candidate = self.runtime.evaluate_candidate

        # 批量处理：每批 batch_size 条记录
        batches = [records[i:i + batch_size] for i in range(0, len(records), batch_size)]

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 提交所有批次任务
            future_to_batch = {
                executor.submit(
                    self._evaluate_batch, batch, criteria, evaluate_candidate
                ): batch for batch in batches
            }

            # 收集结果
            for future in as_completed(future_to_batch):
                batch_results = future.result()
                if batch_results:
                    results.extend(batch_results)

        results.sort(key=self.runtime.result_sort_key, reverse=True)
        return self.runtime.select_diverse_results(results, limit)

    def _evaluate_batch(self, batch, criteria, evaluate_candidate):
        """评估单个批次的记录（线程安全）。"""
        results = []
        for record in batch:
            evaluated = evaluate_candidate(record, criteria)
            if evaluated:
                results.append(evaluated)
        return results


    def apply_request_self_profile_context(self, request, criteria, records):
        self_profile = self.runtime.build_self_profile(
            records,
            self_id=request.get("self_id"),
            profile_input=request.get("self_profile"),
        )
        if self_profile:
            criteria["self_profile"] = self_profile
        if request.get("self_id") is not None:
            criteria.setdefault("exclude_record_refs", set()).add(self.runtime.record_ref(self_profile))
        return self_profile

    def apply_self_profile_context(self, args, criteria, records):
        return self.apply_request_self_profile_context(
            self.build_search_request_from_args(args),
            criteria,
            records,
        )

    def build_search_run(self, criteria, records, results):
        strict_results = [result for result in results if result.get("match_tier", "strict") == "strict"]
        compatible_results = [
            result for result in results if result.get("match_tier", "strict") == "compatible"
        ]
        return {
            "criteria": criteria,
            "records": records,
            "records_count": len(records),
            "results": results,
            "strict_results": strict_results,
            "compatible_results": compatible_results,
            "fallback_results": None,
            "diagnostics": None,
        }

    def populate_no_match_details(self, search_run, args):
        if search_run["results"]:
            return search_run

        search_run["fallback_results"] = self.runtime.build_fallback_candidates(
            search_run["records"],
            search_run["criteria"],
            limit=min(args.limit, 3),
        )
        search_run["diagnostics"] = self.runtime.build_no_match_diagnostics(
            search_run["records"],
            search_run["criteria"],
        )
        return search_run

    def prepare_search_request_context(self, request):
        criteria = self.runtime.normalize_request_criteria(request.get("criteria"))
        sources = self.resolve_request_sources(request)
        records = []
        self_id = self.runtime.as_int(request.get("self_id"))
        include_ids = [self_id] if self_id is not None else []
        moderation_dsn = request.get("moderation_dsn")
        include_blocked = bool(request.get("include_moderation_blocked"))
        self_record_ref = None
        for source in sources:
            source_records = self.runtime.load_source(
                source,
                table_name=request.get("table_name"),
                criteria=criteria,
                include_ids=include_ids,
            )
            moderated_records = self.runtime.overlay_records_with_moderation(
                source_records,
                moderation_dsn=moderation_dsn,
                include_blocked=include_blocked,
            )
            if self_id is not None:
                self_visible = False
                for record in moderated_records:
                    if self.runtime.as_int(record.get("id")) == self_id:
                        self_visible = True
                        self_record_ref = record
                        break
                if not self_visible:
                    for record in source_records:
                        if self.runtime.as_int(record.get("id")) == self_id:
                            self_record_ref = record
                            moderated_records.append(record)
                            break
            records.extend(moderated_records)
            source_records.clear()
            moderated_records.clear()
        self.apply_request_self_profile_context(request, criteria, records)
        if self_id is not None and self_record_ref is not None and "exclude_record_refs" not in criteria:
            criteria["exclude_record_refs"] = {self.runtime.record_ref(self_record_ref)}
        return criteria, records

    def prepare_search_context(self, args):
        return self.prepare_search_request_context(self.build_search_request_from_args(args))

    def resolve_request_self_profile(self, request, criteria, sources):
        self_id = self.runtime.as_int(request.get("self_id"))
        profile_input = request.get("self_profile")
        if self_id is None and not profile_input:
            return None
        normalized_input = self.runtime.normalize_self_profile_input(profile_input)
        if normalized_input:
            normalized_input_id = self.runtime.as_int(normalized_input.get("id"))
            source_file = str(normalized_input.get("source_file") or "").strip()
            if self_id is None or normalized_input_id == self_id or source_file:
                self_profile = self.runtime.build_self_profile(
                    [],
                    self_id=self_id,
                    profile_input=normalized_input,
                )
                if self_profile:
                    criteria["self_profile"] = self_profile
                    if self_id is not None:
                        criteria.setdefault("exclude_record_refs", set()).add(self.runtime.record_ref(self_profile))
                    return self_profile

        self_records = []
        include_ids = [self_id] if self_id is not None else []
        moderation_dsn = request.get("moderation_dsn")
        include_blocked = bool(request.get("include_moderation_blocked"))
        for source in sources:
            source_records = self.runtime.load_source(
                source,
                table_name=request.get("table_name"),
                criteria={},
                include_ids=include_ids,
                include_ids_mode="only",
            )
            moderated_records = self.runtime.overlay_records_with_moderation(
                source_records,
                moderation_dsn=moderation_dsn,
                include_blocked=include_blocked,
            )
            if self_id is not None and not any(self.runtime.as_int(record.get("id")) == self_id for record in moderated_records):
                for record in source_records:
                    if self.runtime.as_int(record.get("id")) == self_id:
                        moderated_records.append(record)
                        break
            self_records.extend(moderated_records)

        self_profile = self.runtime.build_self_profile(
            self_records,
            self_id=self_id,
            profile_input=normalized_input,
        )
        if self_profile:
            criteria["self_profile"] = self_profile
            if self_id is not None:
                criteria.setdefault("exclude_record_refs", set()).add(self.runtime.record_ref(self_profile))
        return self_profile

    def execute_search_request(self, request):
        """执行搜索请求。

        性能优化版本：
        - 使用并行候选评估（大批量）
        - 流式批处理减少内存峰值
        - 及时清理临时字段释放内存
        """
        rule_resolution = request.get("rule_resolution") if isinstance(request, dict) else None
        normalized_request = self.build_search_request(
            sources=request.get("sources") if isinstance(request, dict) else None,
            source=request.get("source") if isinstance(request, dict) else None,
            table_name=request.get("table_name") if isinstance(request, dict) else None,
            photos_table_name=request.get("photos_table_name") if isinstance(request, dict) else None,
            persona_source=request.get("persona_source") if isinstance(request, dict) else None,
            criteria=request.get("criteria") if isinstance(request, dict) else None,
            self_profile=request.get("self_profile") if isinstance(request, dict) else None,
            self_id=request.get("self_id") if isinstance(request, dict) else None,
            requester_id=request.get("requester_id") if isinstance(request, dict) else None,
            limit=request.get("limit", 10) if isinstance(request, dict) else 10,
            photo_preview_count=request.get("photo_preview_count", 0) if isinstance(request, dict) else 0,
            moderation_dsn=request.get("moderation_dsn") if isinstance(request, dict) else None,
            include_moderation_blocked=request.get("include_moderation_blocked", False) if isinstance(request, dict) else False,
        )
        criteria = self.runtime.normalize_request_criteria(normalized_request.get("criteria"))
        sources = self.resolve_request_sources(normalized_request)
        persona_source = normalized_request.get("persona_source")
        requester_id = normalized_request.get("requester_id")
        if persona_source and requester_id is not None:
            appearance_preference = self.runtime.load_user_appearance_preference(
                source_dsn=persona_source,
                user_key=str(requester_id),
            )
            if appearance_preference:
                criteria["appearance_preference"] = appearance_preference
        self.resolve_request_self_profile(normalized_request, criteria, sources)
        records = []
        results = []
        scanned_count = 0
        retain_records = True
        append_result = results.append
        evaluate_candidate = self.runtime.evaluate_candidate
        moderation_dsn = normalized_request.get("moderation_dsn")
        include_blocked = bool(normalized_request.get("include_moderation_blocked"))
        from match_domain.search_rule_context import search_rule_context

        # 内存优化：限制 records 最大累积数量，避免无匹配时内存爆炸
        max_retained_records = 1000  # 仅保留最近 1000 条用于诊断

        with search_rule_context(rule_resolution=rule_resolution):
            for source in sources:
                for source_batch in self.iter_source_record_batches(
                    source,
                    table_name=normalized_request.get("table_name"),
                    criteria=criteria,
                ):
                    moderated_batch = self.runtime.overlay_records_with_moderation(
                        source_batch,
                        moderation_dsn=moderation_dsn,
                        include_blocked=include_blocked,
                    )
                    self.runtime.attach_photo_features(
                        moderated_batch,
                        persona_source=persona_source,
                    )
                    scanned_count += len(moderated_batch)
                    matched_in_batch = False
                    for record in moderated_batch:
                        evaluated = evaluate_candidate(record, criteria)
                        if evaluated:
                            # 内存优化：清理 record 中的临时缓存字段
                            record.pop("_combined_text_cached", None)
                            record.pop("_combined_text_needs_build", None)
                            if record.get("combined_text") is None:
                                record.pop("combined_text", None)
                            record.pop("_diversity_signature", None)
                            record.pop("_diversity_max_overlap", None)
                            record.pop("_display_cache", None)
                            append_result(evaluated)
                            matched_in_batch = True
                    if retain_records:
                        if matched_in_batch:
                            records.clear()
                            retain_records = False
                        else:
                            records.extend(moderated_batch)
                            # 内存优化：限制累积数量
                            if len(records) > max_retained_records:
                                records = records[-max_retained_records:]
        results.sort(key=self.runtime.result_sort_key, reverse=True)
        results = self.runtime.select_diverse_results(results, normalized_request["limit"])
        self.runtime.attach_photo_previews(
            results,
            normalized_request["photo_preview_count"],
            photos_table_name=normalized_request["photos_table_name"],
        )
        if results:
            # Match results do not use the full scanned record pool after ranking.
            search_run = self.build_search_run(criteria, records, results)
            search_run["records_count"] = scanned_count
            search_run["records"] = []
        else:
            search_run = self.build_search_run(criteria, records, results)
            search_run["records_count"] = scanned_count
        return self.populate_no_match_details(
            search_run,
            argparse.Namespace(limit=normalized_request["limit"]),
        )


    def execute_search(self, args):
        return self.execute_search_request(self.build_search_request_from_args(args))

    def json_safe(self, value):
        return json_safe(
            value,
            datetime_formatter=self.runtime.format_datetime,
            stringify_mapping_keys=True,
            sort_sets=True,
        )

    def prepare_result_display_cache(self, result):
        cache = result.get("_display_cache")
        if isinstance(cache, dict):
            return cache
        profile = result.get("profile") or {}
        verification_items = self.runtime.build_verification_items(profile)
        trust_summary = self.runtime.build_trust_summary(profile, verification_items=verification_items)
        cache = {
            "profile": profile,
            "verification_items": verification_items,
            "trust_summary": trust_summary,
            "activity_dt": self.runtime.effective_activity_datetime(profile),
            "activity_info": self.runtime.activity_score_info(profile),
            "json_safe_profile": self.json_safe(profile),
        }
        result["_display_cache"] = cache
        return cache

    def build_structured_result_payload(self, result, include_source=False):
        display_cache = self.prepare_result_display_cache(result)
        profile = display_cache["profile"]
        verification_items = display_cache["verification_items"]
        trust_summary = display_cache["trust_summary"]
        activity_dt = display_cache["activity_dt"]
        payload = {
            "id": result.get("id"),
            "name": result.get("name") or "未命名",
            "score": result.get("score"),
            "fit_score": result.get("fit_score"),
            "confidence_score": result.get("confidence_score"),
            "risk_score": result.get("risk_score"),
            "photo_bonus_breakdown": dict(result.get("photo_bonus_breakdown") or {}),
            "match_tier": result.get("match_tier", "strict"),
            "compatibility_flags": list(result.get("compatibility_flags") or []),
            "verified_level": profile.get("verified_level") or "none",
            "verified_label": trust_summary.get("verified_label"),
            "photo_verification_level": trust_summary.get("photo_verification_level"),
            "photo_verification_label": trust_summary.get("photo_verification_label"),
            "photo_count": self.runtime.as_int(profile.get("photo_count")),
            "last_active_at": self.json_safe(activity_dt),
            "activity_label": display_cache["activity_info"][1],
            "verification_items": verification_items,
            "trust_summary": trust_summary,
            "caution_items": list(trust_summary.get("caution_items") or []),
            "trust_actions": list(trust_summary.get("trust_actions") or []),
            "matched_on": list(result.get("matched_on") or []),
            "reciprocal_on": list(result.get("reciprocal_on") or []),
            "missing_fields": list(result.get("missing_fields") or []),
            "self_profile_gaps": list(result.get("self_profile_gaps") or []),
            "risk_flags": list(result.get("risk_flags") or []),
            "match_evidence": list(result.get("match_evidence") or []),
            "follow_up_questions": list(result.get("follow_up_questions") or []),
            "photo_preview": list(result.get("photo_preview") or []),
            "appearance_summary": profile.get("appearance_summary"),
            "fallback_reason": result.get("fallback_reason"),
            "profile": display_cache["json_safe_profile"],
        }
        if include_source and result.get("source_file"):
            payload["source"] = self.runtime.redact_source_ref(result["source_file"])
        return payload

    def build_pool_summary(self, search_run):
        diagnostics = search_run.get("diagnostics") or {}
        scanned_count = search_run.get("records_count")
        if scanned_count is None:
            scanned_count = len(search_run.get("records") or [])
        strict_results = search_run.get("strict_results")
        compatible_results = search_run.get("compatible_results")
        if strict_results is None or compatible_results is None:
            strict_results = [
                result for result in (search_run.get("results") or [])
                if result.get("match_tier", "strict") == "strict"
            ]
            compatible_results = [
                result for result in (search_run.get("results") or [])
                if result.get("match_tier", "strict") == "compatible"
            ]
        return {
            "scanned_count": scanned_count,
            "passed_count": len(search_run.get("results") or []),
            "strict_count": len(strict_results or []),
            "compatible_count": len(compatible_results or []),
            "usable_count": diagnostics.get("usable_count", scanned_count),
        }

    def build_structured_search_response(self, search_run, include_source=False, include_text=False):
        strict_results = search_run.get("strict_results")
        compatible_results = search_run.get("compatible_results")
        if strict_results is None or compatible_results is None:
            strict_results = [
                result for result in (search_run.get("results") or [])
                if result.get("match_tier", "strict") == "strict"
            ]
            compatible_results = [
                result for result in (search_run.get("results") or [])
                if result.get("match_tier", "strict") == "compatible"
            ]
        response = {
            "has_match": bool(search_run.get("results")),
            "result_count": len(search_run.get("results") or []),
            "pool_summary": self.build_pool_summary(search_run),
            "results": [
                self.build_structured_result_payload(result, include_source=include_source)
                for result in search_run.get("results") or []
            ],
            "strict_results": [
                self.build_structured_result_payload(result, include_source=include_source)
                for result in strict_results or []
            ],
            "compatible_results": [
                self.build_structured_result_payload(result, include_source=include_source)
                for result in compatible_results or []
            ],
            "fallback_results": [
                self.build_structured_result_payload(result, include_source=include_source)
                for result in search_run.get("fallback_results") or []
            ],
            "diagnostics": self.json_safe(search_run.get("diagnostics")),
        }
        if include_text:
            response["text"] = self.render_search_output(search_run, include_source=include_source)
        return response

    def render_search_json(self, search_run, include_source=False, include_text=False):
        return json.dumps(
            self.build_structured_search_response(
                search_run,
                include_source=include_source,
                include_text=include_text,
            ),
            ensure_ascii=False,
            indent=2,
            sort_keys=False,
        )

    def render_search_output(self, search_run, include_source=False):
        if search_run["results"]:
            strict_results = search_run.get("strict_results")
            compatible_results = search_run.get("compatible_results")
            if strict_results is None or compatible_results is None:
                strict_results = [
                    result for result in (search_run.get("results") or [])
                    if result.get("match_tier", "strict") == "strict"
                ]
                compatible_results = [
                    result for result in (search_run.get("results") or [])
                    if result.get("match_tier", "strict") == "compatible"
                ]

            if strict_results and compatible_results:
                return "\n".join(
                    [
                        "Strict matches:",
                        self.format_text(strict_results, include_source=include_source),
                        "",
                        "Compatible matches:",
                        self.format_text(compatible_results, include_source=include_source),
                    ]
                )
            if compatible_results and not strict_results:
                return "\n".join(
                    [
                        "Compatible matches:",
                        self.format_text(compatible_results, include_source=include_source),
                    ]
                )
            return self.format_text(strict_results or search_run["results"], include_source=include_source)
        return self.runtime.format_no_match_text(
            search_run["diagnostics"],
            fallback_results=search_run["fallback_results"],
        )
