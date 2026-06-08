"""读取测评原始数据，不做适配判断。

核心原则：
- 只搬运原始数据
- 不计算适配分
- 不生成匹配原因
- 不判断重要性

AI 自己读取原始数据，自己判断适配性。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from functools import lru_cache
from typing import Any


@dataclass
class PersonalityTraitsContext:
    """原始测评数据（不含任何判断结论）"""

    # MBTI 原始数据
    mbti: dict[str, Any] | None = None
    # {"type_code": "ESTJ", "scores": {"ei": 64.6, "sn": 50, "tf": 75, "jp": 75}, ...}

    # 依恋风格原始数据
    attachment: dict[str, Any] | None = None
    # {"type_code": "secure", "anxiety": 25, "avoidance": 25, ...}

    # 大五人格原始数据
    big_five: dict[str, Any] | None = None
    # {"scores": {"openness": 37.5, "neuroticism": 55, ...}, ...}

    # 价值观原始数据
    values: dict[str, Any] | None = None
    # {"value_type": "成就驱动型", "top_values": ["财务自由", ...], ...}

    # 爱情三元原始数据
    sternberg: dict[str, Any] | None = None
    # {"scores": {"intimacy": 25, "passion": 25, "commitment": 25}, ...}

    # 数据可用性（只判断有还是没有，不做重要性判断）
    availability: dict[str, bool] = field(default_factory=dict)
    # {"has_mbti": True, "has_attachment": True, ...}

    # 元数据
    meta: dict[str, Any] = field(default_factory=dict)
    # {"profile_id": int, "generated_at": datetime, ...}

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式（供 JSON 序列化）"""
        return {
            "mbti": self.mbti,
            "attachment": self.attachment,
            "big_five": self.big_five,
            "values": self.values,
            "sternberg": self.sternberg,
            "availability": self.availability,
            "meta": self.meta,
        }


def _parse_traits_json(traits_json: Any) -> dict[str, Any] | None:
    """解析 self_personality_traits_json 字段"""
    if traits_json is None:
        return None
    if isinstance(traits_json, dict):
        return traits_json
    if isinstance(traits_json, str):
        try:
            return json.loads(traits_json)
        except json.JSONDecodeError:
            return None
    return None


def _calc_completeness(traits: dict[str, Any]) -> float:
    """计算数据完整度（0-1）"""
    if not traits:
        return 0.0
    available_count = sum(
        1
        for key in ("mbti", "attachment", "big_five", "values", "sternberg")
        if traits.get(key) is not None
    )
    return available_count / 5.0


def build_traits_context_from_persona_row(
    persona_row: dict[str, Any] | None,
    profile_id: int | None = None,
) -> PersonalityTraitsContext:
    """从 persona_row 构建 PersonalityTraitsContext

    Args:
        persona_row: 从 user_personas 表加载的数据行
        profile_id: 可选的 profile_id（用于 meta）

    Returns:
        PersonalityTraitsContext（原始数据，不含判断结论）
    """
    if not persona_row:
        return PersonalityTraitsContext(
            availability={
                "has_mbti": False,
                "has_attachment": False,
                "has_big_five": False,
                "has_values": False,
                "has_sternberg": False,
                "overall_completeness": 0.0,
            },
            meta={"profile_id": profile_id, "generated_at": datetime.now().isoformat()},
        )

    # 提取 self_personality_traits_json
    traits_json = persona_row.get("self_personality_traits_json")
    traits = _parse_traits_json(traits_json)

    if not traits:
        return PersonalityTraitsContext(
            availability={
                "has_mbti": False,
                "has_attachment": False,
                "has_big_five": False,
                "has_values": False,
                "has_sternberg": False,
                "overall_completeness": 0.0,
            },
            meta={
                "profile_id": profile_id or persona_row.get("profile_id"),
                "generated_at": datetime.now().isoformat(),
                "source": "user_personas.self_personality_traits_json",
                "raw_exists": True,
                "parse_failed": True,
            },
        )

    # 构建可用性
    availability = {
        "has_mbti": traits.get("mbti") is not None,
        "has_attachment": traits.get("attachment") is not None,
        "has_big_five": traits.get("big_five") is not None,
        "has_values": traits.get("values") is not None,
        "has_sternberg": traits.get("sternberg") is not None,
        "overall_completeness": _calc_completeness(traits),
    }

    return PersonalityTraitsContext(
        mbti=traits.get("mbti"),
        attachment=traits.get("attachment"),
        big_five=traits.get("big_five"),
        values=traits.get("values"),
        sternberg=traits.get("sternberg"),
        availability=availability,
        meta={
            "profile_id": profile_id or persona_row.get("profile_id"),
            "generated_at": datetime.now().isoformat(),
            "source": "user_personas.self_personality_traits_json",
        },
    )


def load_traits_for_profile(
    source: str,
    profile_id: int,
) -> PersonalityTraitsContext:
    """加载单个用户的测评原始数据

    Args:
        source: 数据源 DSN
        profile_id: 用户 profile_id

    Returns:
        PersonalityTraitsContext（原始数据）
    """
    from match_domain.persona_loader import load_persona_by_profile_id

    persona_row = load_persona_by_profile_id(source=source, profile_id=profile_id)
    return build_traits_context_from_persona_row(persona_row, profile_id=profile_id)


def load_traits_for_profiles(
    source: str,
    profile_ids: list[int],
) -> dict[int, PersonalityTraitsContext]:
    """批量加载多个用户的测评原始数据

    Args:
        source: 数据源 DSN
        profile_ids: profile_id 列表

    Returns:
        {profile_id: PersonalityTraitsContext} 字典
    """
    from match_domain.persona_loader import load_personas_by_profile_ids

    if not profile_ids:
        return {}

    persona_rows = load_personas_by_profile_ids(source=source, profile_ids=profile_ids)

    result: dict[int, PersonalityTraitsContext] = {}
    for profile_id in profile_ids:
        persona_row = persona_rows.get(profile_id)
        result[profile_id] = build_traits_context_from_persona_row(persona_row, profile_id=profile_id)

    return result


# === 性能优化：Traits 缓存 ===
# 缓存最近的100个用户的traits，减少重复数据库查询
_TRAITS_CACHE_MAX_SIZE = 100


@lru_cache(maxsize=_TRAITS_CACHE_MAX_SIZE)
def _cached_load_persona_for_discovery(
    source: str,
    profile_id: int | None,
    requester_id: int | None,
) -> dict[str, Any] | None:
    """缓存层：避免重复查询同一用户的 persona 数据"""
    from match_domain.persona_loader import load_persona_for_discovery

    return load_persona_for_discovery(
        source=source,
        profile_id=profile_id,
        requester_id=requester_id,
    )


def load_traits_for_discovery(
    source: str,
    profile_id: int | None = None,
    requester_id: int | None = None,
) -> PersonalityTraitsContext:
    """加载测评数据（兼容 discovery_system 的调用方式）

    Args:
        source: 数据源 DSN
        profile_id: profile_id
        requester_id: requester_id（备用）

    Returns:
        PersonalityTraitsContext（原始数据）
    """
    # 性能优化：使用缓存层避免重复查询
    persona_row = _cached_load_persona_for_discovery(
        source=source,
        profile_id=profile_id,
        requester_id=requester_id,
    )
    return build_traits_context_from_persona_row(
        persona_row,
        profile_id=profile_id,
    )


def clear_traits_cache() -> None:
    """清除 traits 缓存（用于测试或强制刷新）"""
    _cached_load_persona_for_discovery.cache_clear()


__all__ = [
    "PersonalityTraitsContext",
    "build_traits_context_from_persona_row",
    "load_traits_for_discovery",
    "load_traits_for_profile",
    "load_traits_for_profiles",
    "clear_traits_cache",  # 性能优化：缓存清理接口
]