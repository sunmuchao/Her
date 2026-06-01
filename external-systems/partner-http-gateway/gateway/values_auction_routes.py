"""
价值观拍卖会 REST API 路由

实现单人拍卖和双人拍卖的API端点。
"""

from __future__ import annotations

from typing import Any, Protocol

from assessment.values_auction_service import (
    start_values_auction,
    get_traits_list,
    submit_auction_bids,
    generate_ai_interpretation,
    get_last_result,
    start_values_auction_together,
    submit_auction_bids_together,
    check_dual_auction_status,
    reuse_last_result_together,
)

from .collected_routes import _default_profile_source
from .http_helpers import _json_safe, _parse_json_body, _query_dict, _read_body


class ValuesAuctionGateway(Protocol):
    _discovery: Any

    def _resolve_end_user_principal(self, environ: dict[str, Any], *, require_profile: bool = False) -> Any: ...


def _resolve_user_key(gateway: ValuesAuctionGateway, environ: dict[str, Any], body: dict[str, Any] | None = None) -> str:
    """解析用户key"""
    resolved = gateway._resolve_end_user_principal(environ, require_profile=True)
    bound_user_key = str(resolved.profile_id).strip() if resolved is not None and resolved.profile_id is not None else ""
    supplied = str((body or {}).get("user_key") or _query_dict(environ).get("user_key") or "").strip()
    if bound_user_key:
        if supplied and supplied != bound_user_key:
            raise ValueError("user_key does not match current actor")
        return bound_user_key
    if not supplied:
        raise ValueError("user_key is required")
    return supplied


# ============================================================
# 单人拍卖 API
# ============================================================

def rest_values_auction_start(gateway: ValuesAuctionGateway, environ: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    """
    开始价值观拍卖（单人模式）

    POST /v1/values-auction/start
    Body: {"user_key": "xxx"}

    Returns:
        介绍卡片
    """
    body = _parse_json_body(_read_body(environ))
    user_key = _resolve_user_key(gateway, environ, body)
    source = _default_profile_source()
    if not source:
        return 503, {"error": {"code": "source_not_configured", "message": "数据源未配置"}}

    return 200, _json_safe(start_values_auction(source=source, user_key=user_key))


def rest_values_auction_traits(gateway: ValuesAuctionGateway, environ: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    """
    获取特质列表

    POST /v1/values-auction/traits
    Body: {"assessment_id": "xxx"}

    Returns:
        特质列表卡片
    """
    body = _parse_json_body(_read_body(environ))
    assessment_id = str(body.get("assessment_id") or "").strip()
    if not assessment_id:
        raise ValueError("assessment_id is required")

    return 200, _json_safe(get_traits_list(assessment_id=assessment_id))


def rest_values_auction_submit(gateway: ValuesAuctionGateway, environ: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    """
    提交竞拍结果（单人模式）

    POST /v1/values-auction/submit
    Body: {
        "assessment_id": "xxx",
        "user_key": "xxx",
        "bids": [
            {"trait_id": "loyalty", "chips": 5},
            {"trait_id": "humor", "chips": 2},
            ...
        ]
    }

    Returns:
        结果卡片
    """
    body = _parse_json_body(_read_body(environ))
    assessment_id = str(body.get("assessment_id") or "").strip()
    if not assessment_id:
        raise ValueError("assessment_id is required")

    user_key = _resolve_user_key(gateway, environ, body)

    bids = body.get("bids", [])
    if not bids:
        raise ValueError("bids is required")

    source = _default_profile_source()
    if not source:
        return 503, {"error": {"code": "source_not_configured", "message": "数据源未配置"}}

    return 200, _json_safe(
        submit_auction_bids(
            source=source,
            assessment_id=assessment_id,
            user_key=user_key,
            bids=bids,
        )
    )


def rest_values_auction_interpretation(gateway: ValuesAuctionGateway, environ: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    """
    获取AI解读

    POST /v1/values-auction/interpretation
    Body: {"assessment_id": "xxx", "user_key": "xxx"}

    Returns:
        AI解读卡片
    """
    body = _parse_json_body(_read_body(environ))
    assessment_id = str(body.get("assessment_id") or "").strip()
    if not assessment_id:
        raise ValueError("assessment_id is required")

    user_key = _resolve_user_key(gateway, environ, body)

    source = _default_profile_source()
    if not source:
        return 503, {"error": {"code": "source_not_configured", "message": "数据源未配置"}}

    return 200, _json_safe(
        generate_ai_interpretation(
            source=source,
            assessment_id=assessment_id,
            user_key=user_key,
        )
    )


def rest_values_auction_history(gateway: ValuesAuctionGateway, environ: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    """
    获取历史记录（复用机制）

    GET /v1/values-auction/history?user_key=xxx

    Returns:
        上次拍卖结果，或 null
    """
    user_key = _resolve_user_key(gateway, environ, None)
    source = _default_profile_source()
    if not source:
        return 503, {"error": {"code": "source_not_configured", "message": "数据源未配置"}}

    result = get_last_result(source=source, user_key=user_key)
    if result:
        return 200, _json_safe({
            "card_type": "values_auction_history",
            "result_data": {
                "value_type": result.get("value_type", ""),
                "top3": result.get("top3", []),
                "assessed_at": result.get("assessed_at", ""),
            },
        })
    else:
        return 200, _json_safe({
            "card_type": "values_auction_history",
            "result_data": None,
        })


# ============================================================
# 双人拍卖 API
# ============================================================

def rest_values_auction_start_together(gateway: ValuesAuctionGateway, environ: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    """
    开始双人价值观拍卖

    POST /v1/values-auction/start-together
    Body: {"user_key": "xxx", "partner_key": "xxx"}

    Returns:
        特质列表卡片 + 复用选项（如果用户做过）
    """
    body = _parse_json_body(_read_body(environ))
    user_key = _resolve_user_key(gateway, environ, body)
    partner_key = str(body.get("partner_key") or "").strip()
    if not partner_key:
        raise ValueError("partner_key is required")

    source = _default_profile_source()
    if not source:
        return 503, {"error": {"code": "source_not_configured", "message": "数据源未配置"}}

    return 200, _json_safe(
        start_values_auction_together(
            source=source,
            user_key=user_key,
            partner_key=partner_key,
        )
    )


def rest_values_auction_submit_together(gateway: ValuesAuctionGateway, environ: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    """
    提交双人拍卖结果（锁定）

    POST /v1/values-auction/submit-together
    Body: {
        "session_id": "xxx",
        "user_key": "xxx",
        "bids": [...]
    }

    Returns:
        等待卡片 或 匹配分析卡片
    """
    body = _parse_json_body(_read_body(environ))
    session_id = str(body.get("session_id") or "").strip()
    if not session_id:
        raise ValueError("session_id is required")

    user_key = _resolve_user_key(gateway, environ, body)

    bids = body.get("bids", [])
    if not bids:
        raise ValueError("bids is required")

    source = _default_profile_source()
    if not source:
        return 503, {"error": {"code": "source_not_configured", "message": "数据源未配置"}}

    return 200, _json_safe(
        submit_auction_bids_together(
            source=source,
            session_id=session_id,
            user_key=user_key,
            bids=bids,
        )
    )


def rest_values_auction_check_status(gateway: ValuesAuctionGateway, environ: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    """
    检查双人拍卖状态（轮询）

    POST /v1/values-auction/check-status
    Body: {"session_id": "xxx", "user_key": "xxx"}

    Returns:
        matching分析 或 等待状态
    """
    body = _parse_json_body(_read_body(environ))
    session_id = str(body.get("session_id") or "").strip()
    if not session_id:
        raise ValueError("session_id is required")

    user_key = _resolve_user_key(gateway, environ, body)

    source = _default_profile_source()
    if not source:
        return 503, {"error": {"code": "source_not_configured", "message": "数据源未配置"}}

    return 200, _json_safe(
        check_dual_auction_status(
            source=source,
            session_id=session_id,
            user_key=user_key,
        )
    )


def rest_values_auction_reuse_together(gateway: ValuesAuctionGateway, environ: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    """
    复用上次结果（双人模式）

    POST /v1/values-auction/reuse-together
    Body: {"session_id": "xxx", "user_key": "xxx"}

    Returns:
        等待卡片 或 匹配分析卡片
    """
    body = _parse_json_body(_read_body(environ))
    session_id = str(body.get("session_id") or "").strip()
    if not session_id:
        raise ValueError("session_id is required")

    user_key = _resolve_user_key(gateway, environ, body)

    source = _default_profile_source()
    if not source:
        return 503, {"error": {"code": "source_not_configured", "message": "数据源未配置"}}

    return 200, _json_safe(
        reuse_last_result_together(
            source=source,
            session_id=session_id,
            user_key=user_key,
        )
    )


# ============================================================
# 路由注册（供 main.py 使用）
# ============================================================

VALUES_AUCTION_ROUTES = {
    # 单人拍卖
    "/v1/values-auction/start": ("POST", rest_values_auction_start),
    "/v1/values-auction/traits": ("POST", rest_values_auction_traits),
    "/v1/values-auction/submit": ("POST", rest_values_auction_submit),
    "/v1/values-auction/interpretation": ("POST", rest_values_auction_interpretation),
    "/v1/values-auction/history": ("GET", rest_values_auction_history),
    # 双人拍卖
    "/v1/values-auction/start-together": ("POST", rest_values_auction_start_together),
    "/v1/values-auction/submit-together": ("POST", rest_values_auction_submit_together),
    "/v1/values-auction/check-status": ("POST", rest_values_auction_check_status),
    "/v1/values-auction/reuse-together": ("POST", rest_values_auction_reuse_together),
}


def dispatch_values_auction_rest(
    gateway: ValuesAuctionGateway,
    environ: dict[str, Any],
    method: str,
    path: str,
) -> tuple[int, dict[str, Any]] | None:
    """价值观拍卖路由分发"""
    # 单人拍卖
    if path == "/v1/values-auction/start" and method == "POST":
        return rest_values_auction_start(gateway, environ)
    if path == "/v1/values-auction/traits" and method == "POST":
        return rest_values_auction_traits(gateway, environ)
    if path == "/v1/values-auction/submit" and method == "POST":
        return rest_values_auction_submit(gateway, environ)
    if path == "/v1/values-auction/interpretation" and method == "POST":
        return rest_values_auction_interpretation(gateway, environ)
    if path == "/v1/values-auction/history" and method == "GET":
        return rest_values_auction_history(gateway, environ)

    # 双人拍卖
    if path == "/v1/values-auction/start-together" and method == "POST":
        return rest_values_auction_start_together(gateway, environ)
    if path == "/v1/values-auction/submit-together" and method == "POST":
        return rest_values_auction_submit_together(gateway, environ)
    if path == "/v1/values-auction/check-status" and method == "POST":
        return rest_values_auction_check_status(gateway, environ)
    if path == "/v1/values-auction/reuse-together" and method == "POST":
        return rest_values_auction_reuse_together(gateway, environ)

    return None