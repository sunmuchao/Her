"""Trust and verification helpers for partner search results."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable


@dataclass(frozen=True)
class SearchTrustRuntime:
    as_int: Callable[[Any], int | None]
    as_lower: Callable[[Any], str]
    as_text: Callable[[Any], str]
    normalize_bool: Callable[[Any], bool | None]
    verified_rank: Callable[[Any], int]
    effective_activity_datetime: Callable[[dict[str, Any]], datetime | None]
    effective_has_children: Callable[[dict[str, Any]], bool | None]
    parse_income_range_to_wan: Callable[[Any], tuple[int | None, int | None]]
    unique_ordered: Callable[[list[Any]], list[Any]]


def activity_score_info(runtime: SearchTrustRuntime, record: dict[str, Any]) -> tuple[int, str | None, datetime | None]:
    active_at = runtime.effective_activity_datetime(record)
    if active_at is None:
        return (0, None, None)

    now = datetime.now()
    age = now - active_at
    if age <= timedelta(days=7):
        return (12, "7天内活跃", active_at)
    if age <= timedelta(days=30):
        return (8, "30天内活跃", active_at)
    if age <= timedelta(days=90):
        return (4, "90天内活跃", active_at)
    return (0, "90天前活跃", active_at)


def verified_score_info(runtime: SearchTrustRuntime, record: dict[str, Any]) -> tuple[int, str, int]:
    level = record.get("verified_level") or "none"
    rank = runtime.verified_rank(level)
    return (rank * 2, verified_level_label(runtime, level), rank)


def verified_level_label(runtime: SearchTrustRuntime, value: Any) -> str:
    labels = {
        0: "未认证",
        1: "基础认证",
        2: "照片认证",
        3: "实名认证",
        4: "线下核验",
    }
    return labels.get(runtime.verified_rank(value), "未认证")


def photo_verification_level(runtime: SearchTrustRuntime, profile: dict[str, Any] | None) -> str:
    profile = profile or {}
    explicit = runtime.as_lower(
        profile.get("photo_verification_level") or profile.get("photo_verified_level")
    )
    if explicit in {
        "none",
        "uploaded",
        "human_verified",
        "live_video_verified",
        "offline_verified",
    }:
        return explicit
    if runtime.normalize_bool(profile.get("live_video_verified")) is True:
        return "live_video_verified"
    verified_rank_value = runtime.verified_rank(profile.get("verified_level"))
    photo_count = runtime.as_int(profile.get("photo_count"))
    has_photo = bool(profile.get("avatar_url")) or (photo_count is not None and photo_count > 0)
    if verified_rank_value >= 4:
        return "offline_verified"
    if verified_rank_value >= 2:
        return "human_verified"
    if has_photo:
        return "uploaded"
    return "none"


def photo_verification_level_label(runtime: SearchTrustRuntime, value: Any) -> str:
    labels = {
        "none": "未上传照片",
        "uploaded": "普通上传照片",
        "human_verified": "真人照片认证",
        "live_video_verified": "真人认证",
        "offline_verified": "线下核验照片",
    }
    return labels.get(runtime.as_lower(value), "普通上传照片")


def normalize_field_verification_status(
    runtime: SearchTrustRuntime,
    value: Any,
    fallback: str = "self_reported",
) -> str:
    lowered = runtime.as_lower(value)
    if lowered in {
        "verified",
        "approved",
        "passed",
        "platform_verified",
        "human_verified",
        "live_video_verified",
        "offline_verified",
    }:
        return "verified"
    if lowered in {
        "needs_review",
        "inconsistent",
        "mismatch",
        "suspicious",
        "rejected",
        "expired",
        "disputed",
    }:
        return "needs_review"
    if lowered in {"pending", "submitted", "under_review", "resubmission_required"}:
        return "pending"
    if lowered in {"missing", "not_provided", "none"}:
        return "missing"
    if lowered in {"self_reported", "declared", "user_filled"}:
        return "self_reported"
    return fallback


def profile_field_verification_raw_status(
    runtime: SearchTrustRuntime,
    profile: dict[str, Any],
    field_key: str,
) -> str:
    return runtime.as_lower(
        profile.get(f"{field_key}_verification_status")
        or profile.get(f"{field_key}_verified_status")
        or profile.get(f"{field_key}_auth_status")
    )


def profile_field_verification_status(
    runtime: SearchTrustRuntime,
    profile: dict[str, Any],
    field_key: str,
    fallback: str = "self_reported",
) -> str:
    return normalize_field_verification_status(
        runtime,
        profile_field_verification_raw_status(runtime, profile, field_key),
        fallback=fallback,
    )


def format_income_range_text(runtime: SearchTrustRuntime, record: dict[str, Any]) -> str | None:
    income_range = runtime.as_text(record.get("income_range"))
    if income_range:
        return income_range

    income_min = runtime.as_int(record.get("income_min_wan"))
    income_max = runtime.as_int(record.get("income_max_wan"))
    if income_min is None and income_max is None:
        return None
    if income_min is None:
        return f"{income_max}万/年"
    if income_max is None:
        return f"{income_min}万/年"
    if income_min == income_max:
        return f"{income_min}万/年"
    return f"{income_min}-{income_max}万/年"


def build_profile_consistency_flags(
    runtime: SearchTrustRuntime,
    profile: dict[str, Any] | None,
) -> list[str]:
    profile = profile or {}
    flags: list[str] = []
    review_status = runtime.as_lower(profile.get("profile_review_status"))
    if review_status in {"needs_review", "inconsistent", "limited_exposure"}:
        flags.append("资料存在待复核或不一致信号")

    income_max = runtime.as_int(profile.get("income_max_wan"))
    if income_max is None:
        _, income_max = runtime.parse_income_range_to_wan(profile.get("income_range"))
    job_text = runtime.as_text(profile.get("job"))
    if income_max is not None and income_max >= 80 and job_text:
        if any(keyword in job_text for keyword in ("助理", "文员", "行政", "客服", "店员", "实习")):
            flags.append("收入声明与职业类型存在明显落差")

    for field_key, label in (
        ("job_change_count_30d", "职业"),
        ("city_change_count_30d", "城市"),
        ("income_change_count_30d", "收入"),
    ):
        change_count = runtime.as_int(profile.get(field_key))
        if change_count is not None and change_count >= 2:
            flags.append(f"{label}近30天修改较频繁")
    return list(runtime.unique_ordered(flags))


def _append_profile_item(
    runtime: SearchTrustRuntime,
    items: list[dict[str, Any]],
    profile: dict[str, Any],
    key: str,
    label: str,
    value: Any,
    *,
    missing_summary: str,
    verified_template: str,
    self_reported_template: str,
) -> None:
    if value is None or value == "":
        items.append(
            {
                "key": key,
                "label": label,
                "status": "missing",
                "source": "not_provided",
                "summary": missing_summary,
            }
        )
        return

    status = profile_field_verification_status(runtime, profile, key, fallback="self_reported")
    raw_status = profile_field_verification_raw_status(runtime, profile, key)
    source = "profile_self_reported"
    if status == "verified":
        source = "platform_verification"
        summary = verified_template.format(value=value)
    elif raw_status == "resubmission_required":
        source = "review_pending"
        summary = f"{value}（材料需补充后重新提交）"
    elif raw_status == "expired":
        source = "review_pending"
        summary = f"{value}（认证已过期，需重新提交）"
    elif raw_status == "disputed":
        source = "risk_review"
        summary = f"{value}（认证结果存在争议，复核中）"
    elif raw_status == "rejected":
        source = "risk_review"
        summary = f"{value}（材料未通过，建议重新提交）"
    elif status == "pending":
        source = "review_pending"
        summary = f"{value}（认证审核中）"
    elif status == "needs_review":
        source = "risk_review"
        summary = f"{value}（存在不一致信号，建议复核）"
    else:
        summary = self_reported_template.format(value=value)
    items.append(
        {
            "key": key,
            "label": label,
            "status": status,
            "raw_status": raw_status or status,
            "source": source,
            "summary": summary,
        }
    )


def build_verification_items(
    runtime: SearchTrustRuntime,
    profile: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    profile = profile or {}
    items: list[dict[str, Any]] = []
    verified_level = profile.get("verified_level") or "none"
    verified_rank_value = runtime.verified_rank(verified_level)
    photo_count = runtime.as_int(profile.get("photo_count"))
    has_photo = bool(profile.get("avatar_url")) or (photo_count is not None and photo_count > 0)
    photo_level = photo_verification_level(runtime, profile)

    photo_suffix = f"（{photo_count}张）" if photo_count is not None and photo_count > 0 else ""
    if photo_level == "offline_verified":
        items.append(
            {
                "key": "photo",
                "label": "照片",
                "status": "verified",
                "source": "platform_verification",
                "summary": f"已线下核验照片{photo_suffix}",
            }
        )
    elif photo_level == "live_video_verified":
        items.append(
            {
                "key": "photo",
                "label": "照片",
                "status": "verified",
                "source": "platform_verification",
                "summary": f"已活体自拍视频认证{photo_suffix}",
            }
        )
    elif photo_level == "human_verified":
        items.append(
            {
                "key": "photo",
                "label": "照片",
                "status": "verified",
                "source": "platform_verification",
                "summary": f"已真人照片认证{photo_suffix}",
            }
        )
    elif has_photo or photo_level == "uploaded":
        uploaded_summary = (
            f"已上传{photo_count}张照片" if photo_count is not None and photo_count > 0 else "已上传照片"
        )
        items.append(
            {
                "key": "photo",
                "label": "照片",
                "status": "self_reported",
                "source": "profile_self_reported",
                "summary": uploaded_summary + "（未真人认证）",
            }
        )
    else:
        items.append(
            {
                "key": "photo",
                "label": "照片",
                "status": "missing",
                "source": "not_provided",
                "summary": "未上传照片",
            }
        )

    if verified_rank_value >= 4:
        identity_summary = "已线下核验"
        identity_status = "verified"
    elif verified_rank_value >= 3:
        identity_summary = "已实名认证"
        identity_status = "verified"
    elif verified_rank_value >= 1:
        identity_summary = "已基础认证"
        identity_status = "verified"
    else:
        identity_summary = "未实名"
        identity_status = "missing"
    items.append(
        {
            "key": "identity",
            "label": "身份",
            "status": identity_status,
            "source": "platform_verification" if verified_rank_value >= 1 else "not_provided",
            "summary": identity_summary,
        }
    )

    if verified_rank_value >= 4:
        items.append(
            {
                "key": "offline_check",
                "label": "线下核验",
                "status": "verified",
                "source": "platform_verification",
                "summary": "已完成线下核验",
            }
        )
    elif photo_level == "live_video_verified":
        items.append(
            {
                "key": "offline_check",
                "label": "真人视频核验",
                "status": "verified",
                "source": "platform_verification",
                "summary": "已完成活体自拍视频核验",
            }
        )

    age = runtime.as_int(profile.get("age"))
    age_status = (
        "verified"
        if verified_rank_value >= 3
        else profile_field_verification_status(runtime, profile, "age", fallback="self_reported")
    )
    if age is not None:
        items.append(
            {
                "key": "age",
                "label": "年龄",
                "status": age_status,
                "source": "platform_verification" if age_status == "verified" else "profile_self_reported",
                "summary": f"{age}岁（{'实名层级' if age_status == 'verified' else '资料填写'}）",
            }
        )
    else:
        items.append(
            {
                "key": "age",
                "label": "年龄",
                "status": "missing",
                "source": "not_provided",
                "summary": "年龄未填写",
            }
        )

    _append_profile_item(
        runtime,
        items,
        profile,
        "city",
        "城市",
        runtime.as_text(profile.get("city")),
        missing_summary="城市未填写",
        verified_template="{value}（已核验）",
        self_reported_template="{value}（资料填写）",
    )
    _append_profile_item(
        runtime,
        items,
        profile,
        "education",
        "学历",
        runtime.as_text(profile.get("education")),
        missing_summary="学历未填写",
        verified_template="{value}（已认证）",
        self_reported_template="{value}（未单独认证）",
    )
    _append_profile_item(
        runtime,
        items,
        profile,
        "job",
        "职业",
        runtime.as_text(profile.get("job")),
        missing_summary="职业未填写",
        verified_template="{value}（已认证）",
        self_reported_template="{value}（未单独认证）",
    )
    _append_profile_item(
        runtime,
        items,
        profile,
        "income",
        "收入",
        format_income_range_text(runtime, profile),
        missing_summary="收入未填写",
        verified_template="{value}（已认证区间）",
        self_reported_template="{value}（未单独认证）",
    )
    _append_profile_item(
        runtime,
        items,
        profile,
        "marital_status",
        "婚况",
        runtime.as_text(profile.get("marital_status")),
        missing_summary="婚况未填写",
        verified_template="{value}（已核验）",
        self_reported_template="{value}（资料填写）",
    )

    has_children = runtime.effective_has_children(profile)
    if has_children is None:
        items.append(
            {
                "key": "children",
                "label": "子女情况",
                "status": "missing",
                "source": "not_provided",
                "summary": "子女情况未填写",
            }
        )
    else:
        child_label = "有孩子" if has_children else "无孩子"
        child_count = runtime.as_int(profile.get("children_count"))
        if has_children and child_count:
            child_label = f"有{child_count}个孩子"
        children_status = profile_field_verification_status(
            runtime,
            profile,
            "children",
            fallback="self_reported",
        )
        items.append(
            {
                "key": "children",
                "label": "子女情况",
                "status": children_status,
                "source": "platform_verification" if children_status == "verified" else "profile_self_reported",
                "summary": f"{child_label}（{'已核验' if children_status == 'verified' else '资料填写'}）",
            }
        )

    _append_profile_item(
        runtime,
        items,
        profile,
        "relationship_goal",
        "结婚意向",
        runtime.as_text(profile.get("relationship_goal")),
        missing_summary="结婚意向未填写",
        verified_template="{value}（已核验）",
        self_reported_template="{value}（资料填写）",
    )
    return items


def build_trust_caution_items(
    runtime: SearchTrustRuntime,
    profile: dict[str, Any] | None,
    verification_items: list[dict[str, Any]] | None = None,
) -> list[str]:
    profile = profile or {}
    verification_items = verification_items or build_verification_items(runtime, profile)
    caution_items: list[str] = []
    photo_item = next((item for item in verification_items if item.get("key") == "photo"), None)
    if photo_item and photo_item.get("status") == "self_reported":
        caution_items.append("照片仅为普通上传，建议先视频核验再深入沟通")
    if any(
        item.get("status") == "needs_review"
        for item in verification_items
        if item.get("key") in {"education", "job", "income", "marital_status", "children"}
    ):
        caution_items.append("部分高决策字段存在不一致信号，建议补充核验")
    if any(
        item.get("raw_status") == "expired"
        for item in verification_items
        if item.get("key") in {"education", "job", "income"}
    ):
        caution_items.append("部分高决策字段认证已过期，建议重新提交最新材料")
    if any(
        item.get("raw_status") == "disputed"
        for item in verification_items
        if item.get("key") in {"education", "job", "income"}
    ):
        caution_items.append("部分高决策字段正在争议复核中，建议暂不把其视为已核验信息")
    if (
        profile_field_verification_status(runtime, profile, "income", fallback="self_reported")
        == "self_reported"
        and format_income_range_text(runtime, profile)
    ):
        caution_items.append("收入仍为自填信息，建议仅将其视为参考")
    caution_items.extend(profile.get("moderation_caution_items") or [])
    caution_items.extend(build_profile_consistency_flags(runtime, profile))
    return list(runtime.unique_ordered(caution_items))


def build_trust_actions(
    runtime: SearchTrustRuntime,
    profile: dict[str, Any] | None,
    verification_items: list[dict[str, Any]] | None = None,
    caution_items: list[str] | None = None,
) -> list[str]:
    verification_items = verification_items or build_verification_items(runtime, profile)
    caution_items = caution_items or build_trust_caution_items(
        runtime,
        profile,
        verification_items=verification_items,
    )
    actions: list[str] = []
    photo_item = next((item for item in verification_items if item.get("key") == "photo"), None)
    if photo_item and photo_item.get("status") != "verified":
        actions.append("建议先视频核验真人状态")
    if any(
        item.get("key") in {"income", "job", "education"}
        and item.get("status") in {"self_reported", "needs_review"}
        for item in verification_items
    ):
        actions.append("建议先确认职业、学历和收入区间是否真实")
    if any(
        item.get("raw_status") in {"expired", "resubmission_required", "rejected", "disputed"}
        for item in verification_items
        if item.get("key") in {"education", "job", "income"}
    ):
        actions.append("若继续沟通前要做高决策判断，建议等待对方补件或复核完成")
    if caution_items:
        actions.append("在转到站外或涉及金钱前，先完成平台内核验")
    return list(runtime.unique_ordered(actions))


def build_trust_summary(
    runtime: SearchTrustRuntime,
    profile: dict[str, Any] | None,
    verification_items: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    profile = profile or {}
    verification_items = verification_items or build_verification_items(runtime, profile)
    verified_labels = [item["label"] for item in verification_items if item["status"] == "verified"]
    self_reported_labels = [
        item["label"]
        for item in verification_items
        if item["status"] in {"self_reported", "pending"}
        and item["key"]
        in {"education", "job", "income", "marital_status", "children", "relationship_goal"}
    ]
    missing_labels = [
        item["label"]
        for item in verification_items
        if item["status"] == "missing"
        and item["key"] in {"marital_status", "children", "income", "education", "job", "relationship_goal"}
    ]
    caution_labels = [
        item["label"]
        for item in verification_items
        if item["status"] == "needs_review"
        and item["key"]
        in {"education", "job", "income", "marital_status", "children", "relationship_goal"}
    ]

    badges: list[str] = []
    verified_rank_value = runtime.verified_rank(profile.get("verified_level"))
    photo_level = photo_verification_level(runtime, profile)
    if photo_level == "offline_verified":
        badges.append("照片已线下核验")
    elif photo_level == "live_video_verified":
        badges.append("照片已真人认证核验")
    elif photo_level == "human_verified":
        badges.append("照片已真人认证")
    if verified_rank_value >= 3:
        badges.append("已实名认证")
    elif verified_rank_value >= 1:
        badges.append("已基础认证")
    if verified_rank_value >= 4 and photo_level != "offline_verified":
        badges.append("已线下核验")
    activity_label = activity_score_info(runtime, profile)[1]
    if activity_label:
        badges.append(activity_label)

    headline_parts: list[str] = []
    if badges:
        headline_parts.append("；".join(runtime.unique_ordered(badges[:3])))
    else:
        headline_parts.append("认证信息有限")

    if caution_labels:
        headline_parts.append(
            "以下字段存在待复核信号：" + "、".join(runtime.unique_ordered(caution_labels)[:3])
        )
    if self_reported_labels:
        headline_parts.append(
            "其余关键信息以资料填写为主：" + "、".join(runtime.unique_ordered(self_reported_labels)[:4])
        )
    elif not caution_labels and missing_labels:
        headline_parts.append(
            "仍有资料待补充：" + "、".join(runtime.unique_ordered(missing_labels)[:3])
        )

    caution_items = build_trust_caution_items(
        runtime,
        profile,
        verification_items=verification_items,
    )
    return {
        "headline": "；".join(headline_parts),
        "verified_level": profile.get("verified_level") or "none",
        "verified_label": verified_level_label(runtime, profile.get("verified_level")),
        "photo_verification_level": photo_level,
        "photo_verification_label": photo_verification_level_label(runtime, photo_level),
        "badges": list(runtime.unique_ordered(badges)),
        "verified_items": list(runtime.unique_ordered(verified_labels)),
        "self_reported_items": list(runtime.unique_ordered(self_reported_labels)),
        "missing_items": list(runtime.unique_ordered(missing_labels)),
        "caution_items": caution_items,
        "trust_actions": build_trust_actions(
            runtime,
            profile,
            verification_items=verification_items,
            caution_items=caution_items,
        ),
    }


__all__ = [
    "SearchTrustRuntime",
    "activity_score_info",
    "build_profile_consistency_flags",
    "build_trust_actions",
    "build_trust_caution_items",
    "build_trust_summary",
    "build_verification_items",
    "format_income_range_text",
    "normalize_field_verification_status",
    "photo_verification_level",
    "photo_verification_level_label",
    "profile_field_verification_raw_status",
    "profile_field_verification_status",
    "verified_level_label",
    "verified_score_info",
]
