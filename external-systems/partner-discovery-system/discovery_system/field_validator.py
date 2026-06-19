"""候选人卡片字段验证工具

功能说明：
- 验证候选人卡片字段是否符合规范
- 检查必须字段、类型、格式
- 返回错误列表（空列表表示验证通过）

使用方式：
from .field_validator import validate_candidate_card, validate_view_model

errors = validate_candidate_card(card)
if errors:
    _logger.warning(f"候选人卡片验证失败: errors={errors}")
"""

from __future__ import annotations

import logging
from typing import Any

_logger = logging.getLogger(__name__)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 候选人卡片验证
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def validate_candidate_card(card: dict[str, Any]) -> list[str]:
    """验证候选人卡片字段

    验证内容：
    1. 必须字段是否存在
    2. 字段类型是否正确
    3. 字段格式是否符合规范

    Args:
        card: 候选人卡片字典

    Returns:
        错误列表（空列表表示验证通过）

    示例：
        errors = validate_candidate_card(card)
        if errors:
            _logger.warning(f"验证失败: errors={errors}")
    """
    errors: list[str] = []

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 1. 必须字段验证
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    required_fields = ["card_id", "profile_id", "title", "subtitle"]
    for field in required_fields:
        if field not in card:
            errors.append(f"缺少必须字段: {field}")
        elif card.get(field) is None:
            errors.append(f"必须字段为空: {field}")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 2. 类型验证
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    # profile_id 必须是整数
    if "profile_id" in card and card.get("profile_id") is not None:
        if not isinstance(card["profile_id"], int):
            errors.append(f"profile_id 类型错误: 期望 int, 实际 {type(card['profile_id']).__name__}")

    # match_score 必须是数字（0-1）
    if "match_score" in card and card.get("match_score") is not None:
        if not isinstance(card["match_score"], (int, float)):
            errors.append(f"match_score 类型错误: 期望 float, 实际 {type(card['match_score']).__name__}")
        elif not (0 <= card["match_score"] <= 1):
            errors.append(f"match_score 范围错误: 期望 0-1, 实际 {card['match_score']}")

    # title 必须是字符串
    if "title" in card and card.get("title") is not None:
        if not isinstance(card["title"], str):
            errors.append(f"title 类型错误: 期望 str, 实际 {type(card['title']).__name__}")

    # subtitle 必须是字符串
    if "subtitle" in card and card.get("subtitle") is not None:
        if not isinstance(card["subtitle"], str):
            errors.append(f"subtitle 类型错误: 期望 str, 实际 {type(card['subtitle']).__name__}")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 3. 可选字段类型验证
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    # personality_match_context 必须是字典
    if "personality_match_context" in card and card.get("personality_match_context") is not None:
        if not isinstance(card["personality_match_context"], dict):
            errors.append(
                f"personality_match_context 类型错误: 期望 dict, "
                f"实际 {type(card['personality_match_context']).__name__}"
            )

    # personality_reasons 必须是列表
    if "personality_reasons" in card and card.get("personality_reasons") is not None:
        if not isinstance(card["personality_reasons"], list):
            errors.append(
                f"personality_reasons 类型错误: 期望 list, "
                f"实际 {type(card['personality_reasons']).__name__}"
            )
        # 验证列表元素类型
        for idx, item in enumerate(card.get("personality_reasons") or []):
            if not isinstance(item, str):
                errors.append(f"personality_reasons[{idx}] 类型错误: 期望 str, 实际 {type(item).__name__}")

    # trust_badges 必须是列表
    if "trust_badges" in card and card.get("trust_badges") is not None:
        if not isinstance(card["trust_badges"], list):
            errors.append(
                f"trust_badges 类型错误: 期望 list, "
                f"实际 {type(card['trust_badges']).__name__}"
            )

    # match_highlights 必须是列表
    if "match_highlights" in card and card.get("match_highlights") is not None:
        if not isinstance(card["match_highlights"], list):
            errors.append(
                f"match_highlights 类型错误: 期望 list, "
                f"实际 {type(card['match_highlights']).__name__}"
            )

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 4. 格式验证
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    # card_id 格式验证（应为 "candidate-{profile_id}"）
    if "card_id" in card and card.get("card_id") is not None:
        card_id = str(card.get("card_id"))
        if not card_id.startswith("candidate-"):
            errors.append(f"card_id 格式错误: 应为 'candidate-{profile_id}', 实际 '{card_id}'")

    return errors


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 视图模型验证
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def validate_view_model(view: dict[str, Any]) -> list[str]:
    """验证整个视图模型

    验证内容：
    1. timeline 字段是否存在
    2. timeline 中的每个项目是否有效
    3. 候选人卡片是否符合规范

    Args:
        view: 视图模型字典

    Returns:
        错误列表（空列表表示验证通过）
    """
    errors: list[str] = []

    # timeline 必须存在且是列表
    if "timeline" not in view:
        errors.append("缺少必须字段: timeline")
        return errors

    if not isinstance(view.get("timeline"), list):
        errors.append(f"timeline 类型错误: 期望 list, 实际 {type(view.get('timeline')).__name__}")
        return errors

    # 验证 timeline 中的每个项目
    timeline = view.get("timeline") or []
    for idx, item in enumerate(timeline):
        if not isinstance(item, dict):
            errors.append(f"timeline[{idx}] 类型错误: 期望 dict, 实际 {type(item).__name__}")
            continue

        item_type = item.get("item_type")

        # 验证 item_type 字段
        if not item_type:
            errors.append(f"timeline[{idx}] 缺少 item_type 字段")
            continue

        # 如果是候选人卡片，验证卡片字段
        if item_type == "candidate_card" or item_type == "result_group":
            # result_group 包含 cards 字段
            if item_type == "result_group":
                cards = item.get("cards") or []
                if not isinstance(cards, list):
                    errors.append(f"timeline[{idx}].cards 类型错误: 期望 list")
                    continue

                # 验证每个卡片
                for card_idx, card in enumerate(cards):
                    card_errors = validate_candidate_card(card)
                    for err in card_errors:
                        errors.append(f"timeline[{idx}].cards[{card_idx}]: {err}")

            # candidate_card 直接是卡片
            elif item_type == "candidate_card":
                card_errors = validate_candidate_card(item)
                for err in card_errors:
                    errors.append(f"timeline[{idx}]: {err}")

    return errors


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 辅助函数
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def log_validation_errors(errors: list[str], *, context: str = "") -> None:
    """记录验证错误到日志

    Args:
        errors: 错误列表
        context: 上下文信息（如 "构建候选人卡片"）

    示例：
        errors = validate_candidate_card(card)
        if errors:
            log_validation_errors(errors, context=f"构建候选人卡片: profile_id={profile_id}")
    """
    if not errors:
        return

    error_msg = "; ".join(errors)
    context_msg = f" [{context}]" if context else ""
    _logger.warning(f"字段验证失败{context_msg}: {error_msg}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 导出
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


__all__ = [
    "validate_candidate_card",
    "validate_view_model",
    "log_validation_errors",
]