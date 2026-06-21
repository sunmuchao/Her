"""会话结束处理器：LLM提炼摘要 + 存储摘要文本。

任务2核心实现：
- 异步后台提炼
- 只存摘要文本（向量化后续迭代）
- 触发时机：新建会话、30分钟无活动、会话销毁

核心函数：
1. process_session_end() - 主流程入口（异步）
2. load_session_messages_from_db() - 从数据库加载聊天记录
3. generate_structured_summary() - LLM提炼结构化摘要
4. save_session_summary_text() - 存储摘要文本到数据库
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import re
from datetime import datetime
from typing import Any

_logger = logging.getLogger(__name__)

from match_domain.collected_profile import COLLECTED_PERSONA_FIELDS


SUMMARY_FIELD_KEYS = frozenset({
    "personality_traits",
    "values",
    "partner_expectation",
    "life_attitude",
    "emotional_needs",
    "negative_preferences",
})

STRUCTURED_QUANTIFIABLE_FIELDS = frozenset({
    "age",
    "age_min",
    "age_max",
    "height",
    "height_min",
    "height_max",
    "mbti_type",
    "personality_type",
    "marital_status",
    "has_children",
    "children_count",
    "children_living_with_self",
    "smoking",
    "drinking",
    "city",
    "cities",
    "education",
    "income",
    "income_min",
    "income_max",
    "gender",
    "relationship_goal",
})

PERSONA_ALLOWED_SUMMARY_FIELDS = frozenset({
    "mbti_type",
    "marital_status",
    "has_children",
    "smoking",
    "drinking",
    "relationship_goal",
    "education",
})

ABSTRACT_SUMMARY_TERMS = (
    "合拍",
    "真诚",
    "稳定",
    "靠谱",
    "成熟",
    "三观一致",
    "共同话题",
    "被理解",
    "情绪价值",
    "舒服",
    "合适",
    "有感觉",
    "好相处",
    "安全感",
)

GENERIC_SUMMARY_PATTERNS = (
    re.compile(r"^希望.*合拍$"),
    re.compile(r"^需要.*合拍$"),
    re.compile(r"^希望.*真诚.*沟通$"),
    re.compile(r"^希望.*真诚.*稳定$"),
    re.compile(r"^需要.*稳定.*关系$"),
    re.compile(r"^需要.*安全感$"),
    re.compile(r"^希望.*共同话题$"),
    re.compile(r"^希望.*被理解$"),
    re.compile(r"^需要.*情绪价值$"),
)

COMMON_CONCRETE_SIGNALS = (
    "情绪稳定",
    "温和",
    "不强势",
    "慢热",
    "主动表达",
    "边界感",
    "愿意沟通",
    "有事直说",
    "不冷处理",
    "会回应",
    "不敷衍",
    "认真推进",
    "不暧昧",
    "长期投入",
    "关系明确",
    "工作别太忙",
    "别太卷",
    "生活规律",
    "作息规律",
    "下班后有时间",
    "同城",
    "异地",
    "婚史",
    "孩子",
    "消费观",
    "行业",
    "职业稳定",
    "互联网行业",
)

FIELD_SPECIFIC_SIGNALS: dict[str, tuple[str, ...]] = {
    "partner_expectation": COMMON_CONCRETE_SIGNALS + (
        "年龄",
        "未婚",
        "半年内结婚",
        "结婚导向",
        "沟通",
        "陪伴",
    ),
    "emotional_needs": (
        "回应",
        "陪伴",
        "沟通",
        "不冷处理",
        "有时间",
        "正面沟通",
        "关系明确",
    ),
    "life_attitude": (
        "作息规律",
        "生活规律",
        "稳定",
        "别太卷",
        "低消耗",
        "安静",
        "做饭",
        "秩序",
    ),
}

VALID_MBTI_TYPES = frozenset({
    "INTJ",
    "INTP",
    "ENTJ",
    "ENTP",
    "INFJ",
    "INFP",
    "ENFJ",
    "ENFP",
    "ISTJ",
    "ISFJ",
    "ESTJ",
    "ESFJ",
    "ISTP",
    "ISFP",
    "ESTP",
    "ESFP",
})


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 核心函数：会话结束处理流程
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


async def process_session_end(
    session_id: str,
    requester_id: int,
    profile_id: int,
    conversation_type: str = "discovery",
    *,
    dsn: str | None = None,
    llm_base_url: str | None = None,
    llm_api_key: str | None = None,
    llm_model: str | None = None,
    processed_at: datetime | None = None,  # ✅ 新增：上次处理时间，用于增量处理
    storage: Any | None = None,  # ✅ 新增：storage对象（用于后续更新processed_at）
    vectorize_summaries: bool = True,
    clear_working_criteria_after_processing: bool = True,
) -> dict[str, Any]:
    """会话结束时的处理流程（异步后台提炼，支持增量处理）

    关键设计：
    - 只传 session_id，不传内存对象（避免时序漏洞）
    - 从数据库重新加载聊天记录（解决内存对象销毁问题）
    - 异步处理（不阻塞主流程）
    - ✅ 增量处理：传入 processed_at，只加载新增内容

    Args:
        session_id: 会话ID（用于加载聊天记录）
        requester_id: 用户ID
        profile_id: 画像ID
        conversation_type: 对话类型（discovery/chat/assessment）

        dsn: 数据库连接字符串（可选，默认从环境变量读取）
        llm_base_url: LLM API地址（可选，默认从环境变量读取）
        llm_api_key: LLM API密钥（可选，默认从环境变量读取）
        llm_model: LLM模型名称（可选，默认从环境变量读取）
        processed_at: 上次处理时间（可选，用于增量处理）
        storage: storage对象（可选，用于后续更新processed_at）
        vectorize_summaries: 是否为不可量化摘要生成向量
        clear_working_criteria_after_processing: 是否在处理后清空 working_criteria

    Returns:
        处理结果，包含：
        - success: 是否成功
        - summary_data: 提炼的摘要数据
        - saved_keys: 已保存的字段列表
        - error: 错误信息（如果失败）
    """
    _logger.info(
        f"开始处理会话结束: session_id={session_id}, requester_id={requester_id}, "
        f"profile_id={profile_id}, conversation_type={conversation_type}, "
        f"processed_at={processed_at}"
    )

    try:
        # Step 1：从数据库加载聊天记录（增量加载）
        messages = await load_session_messages_from_db(
            session_id,
            dsn=dsn,
            processed_at=processed_at,  # ✅ 新增：传入 processed_at
        )
        if not messages:
            _logger.warning(f"会话 {session_id} 没有新增聊天记录，跳过处理")
            return {
                "success": False,
                "error": "no_new_messages",
                "message": "会话没有新增聊天记录",
            }

        _logger.info(f"加载了 {len(messages)} 条聊天记录")

        # Step 2：LLM提炼结构化摘要
        summary_data = await generate_structured_summary(
            messages,
            requester_id=requester_id,
            llm_base_url=llm_base_url,
            llm_api_key=llm_api_key,
            llm_model=llm_model,
        )

        if not summary_data:
            _logger.warning(f"LLM提炼摘要失败: session_id={session_id}")
            return {
                "success": False,
                "error": "llm_failed",
                "message": "LLM提炼摘要失败",
            }

        _logger.info(f"LLM提炼摘要成功: {summary_data}")

        # Step 3：分流判断（V2修正版）
        # 分流：分离可量化字段和不可量化字段
        quantifiable_data, non_quantifiable_data = split_by_quantifiability(summary_data)

        _logger.info(
            f"分流完成: quantifiable_fields={list(quantifiable_data.keys())}, "
            f"non_quantifiable_fields={list(non_quantifiable_data.keys())}"
        )

        # Step 4：处理可量化字段：写入画像表
        if quantifiable_data:
            persona_result = await save_quantifiable_to_persona_tables(
                user_key=str(requester_id),
                profile_id=profile_id,
                session_id=session_id,
                quantifiable_data=quantifiable_data,
                dsn=dsn,
            )
            _logger.info(f"可量化字段写入画像表: persona_result={persona_result}")
        else:
            persona_result = {"success": True, "message": "no_quantifiable_fields"}
            _logger.info("没有可量化字段需要写入画像表")

        # Step 5：处理不可量化字段：写入摘要表+向量库
        if non_quantifiable_data:
            valid_summary_data, rejected_summary_quality = filter_valid_summary_data(non_quantifiable_data)
            if rejected_summary_quality:
                _logger.info(
                    f"摘要质检拒绝字段: "
                    f"{', '.join(f'{k}={v}' for k, v in rejected_summary_quality.items())}"
                )

            if not valid_summary_data:
                saved_keys = []
                vectorized_keys = []
                _logger.info("不可量化字段全部被摘要质检拦截，跳过摘要表和向量库写入")
            else:
                # 存储摘要文本到数据库
                saved_keys = await save_session_summary_text(
                    session_id=session_id,
                    requester_id=requester_id,
                    profile_id=profile_id,
                    conversation_type=conversation_type,
                    summary_data=valid_summary_data,
                    dsn=dsn,
                )
                _logger.info(f"不可量化字段摘要存储成功: saved_keys={saved_keys}")

                # 向量化存储
                if vectorize_summaries:
                    vectorized_keys = await save_vectors_for_summary(
                        session_id=session_id,
                        requester_id=requester_id,
                        summary_data=valid_summary_data,
                    )
                    _logger.info(f"不可量化字段向量化存储成功: vectorized_keys={vectorized_keys}")
                else:
                    vectorized_keys = []
                    _logger.info("已跳过不可量化字段向量化存储")
        else:
            saved_keys = []
            vectorized_keys = []
            _logger.info("没有不可量化字段需要写入摘要表和向量库")

        # Step 6：清空 working_criteria（会话结束后清理临时搜索条件）
        if clear_working_criteria_after_processing:
            await clear_working_criteria(session_id, dsn=dsn)
            _logger.info(f"working_criteria 已清空: session_id={session_id}")
        else:
            _logger.info(f"跳过清空 working_criteria: session_id={session_id}")

        return {
            "success": True,
            "summary_data": summary_data,
            "quantifiable_data": quantifiable_data,
            "non_quantifiable_data": non_quantifiable_data,
            "persona_result": persona_result,
            "saved_keys": saved_keys,
            "vectorized_keys": vectorized_keys,
            "message_count": len(messages),
        }

    except Exception as exc:
        _logger.error(f"会话结束处理失败: session_id={session_id}, error={exc}")
        return {
            "success": False,
            "error": "exception",
            "message": str(exc)[:200],
        }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Step 1：从数据库加载聊天记录
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


async def load_session_messages_from_db(
    session_id: str,
    *,
    dsn: str | None = None,
    processed_at: datetime | None = None,  # ✅ 新增：上次处理的时间，用于增量加载
) -> list[dict[str, Any]]:
    """从数据库加载聊天记录（支持增量加载）

    关键设计：
    - 只传 session_id，不传内存对象（避免时序漏洞）
    - 从 discovery_agent_session_memory_items 表加载
    - 返回格式化的消息列表
    - ✅ 增量加载：如果传入 processed_at，只加载 created_at > processed_at 的消息

    Args:
        session_id: 会话ID
        dsn: 数据库连接字符串（可选，默认从环境变量读取）
        processed_at: 上次处理的时间（可选，用于增量加载）

    Returns:
        消息列表，格式：[{"role": "user/assistant", "content": "..."}]
    """
    resolved_dsn = dsn or os.environ.get("PARTNER_DISCOVERY_DB") or ""

    if not resolved_dsn:
        _logger.warning("没有配置 PARTNER_DISCOVERY_DB，无法加载聊天记录")
        return []

    def _load_sync() -> list[dict[str, Any]]:
        from external_systems.partner_discovery_system.discovery_system.storage import connect_db, json_loads

        conn = connect_db(resolved_dsn)
        try:
            # ✅ 增量加载：如果传入 processed_at，只加载 created_at > processed_at 的消息
            if processed_at is not None:
                rows = conn.execute(
                    """
                    SELECT item_json, created_at
                    FROM discovery_agent_session_memory_items
                    WHERE session_id = ? AND created_at > ?
                    ORDER BY item_id ASC
                    """,
                    (session_id, processed_at),
                ).fetchall()
                _logger.info(
                    f"增量加载聊天记录: session_id={session_id}, "
                    f"processed_at={processed_at}, loaded_count={len(rows)}"
                )
            else:
                # 全量加载：processed_at 为空，加载所有消息
                rows = conn.execute(
                    """
                    SELECT item_json
                    FROM discovery_agent_session_memory_items
                    WHERE session_id = ?
                    ORDER BY item_id ASC
                    """,
                    (session_id,),
                ).fetchall()
                _logger.info(
                    f"全量加载聊天记录: session_id={session_id}, "
                    f"loaded_count={len(rows)}"
                )

            messages: list[dict[str, Any]] = []
            for row in rows:
                item = json_loads(str(row.get("item_json") or "null"), None)
                if isinstance(item, dict):
                    messages.append(item)

            return messages

        finally:
            conn.close()

    # 异步执行（避免阻塞）
    return await asyncio.to_thread(_load_sync)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Step 2：LLM提炼结构化摘要
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


async def generate_structured_summary(
    messages: list[dict[str, Any]],
    *,
    requester_id: int,
    llm_base_url: str | None = None,
    llm_api_key: str | None = None,
    llm_model: str | None = None,
) -> dict[str, str]:
    """LLM提炼结构化摘要

    关键设计：
    - 输入是聊天记录（不是实时 patch）
    - 输出是结构化的字典（每个字段对应一个摘要维度）
    - 使用 JSON 格式输出（确保结构化）

    Args:
        messages: 聊天记录列表
        requester_id: 用户ID（用于日志）

        llm_base_url: LLM API地址（可选）
        llm_api_key: LLM API密钥（可选）
        llm_model: LLM模型名称（可选）

    Returns:
        结构化摘要字典，格式：
        {
            "personality_traits": "性格温柔、内向",
            "values": "重视家庭、重视事业",
            "partner_expectation": "希望找个能理解工作忙碌的人",
            "life_attitude": "追求稳定、重视生活质量",
            "emotional_needs": "需要理解和支持"
        }
    """
    # 格式化聊天记录
    formatted_messages = _format_messages_for_llm(messages)

    # 构造 Prompt
    prompt = _build_summary_prompt(formatted_messages)

    # 调用 LLM
    try:
        summary_json = await _call_llm_for_json(
            prompt,
            llm_base_url=llm_base_url,
            llm_api_key=llm_api_key,
            llm_model=llm_model,
        )

        # 验证返回格式
        if not isinstance(summary_json, dict):
            _logger.warning(f"LLM返回格式错误: {summary_json}")
            return {}

        # 清理空字符串（可选）
        cleaned_summary = {
            key: str(value).strip()
            for key, value in summary_json.items()
            if str(value or "").strip()
        }

        return cleaned_summary

    except Exception as exc:
        _logger.error(f"LLM调用失败: requester_id={requester_id}, error={exc}")
        return {}


def _format_messages_for_llm(messages: list[dict[str, Any]]) -> str:
    """格式化聊天记录给LLM看

    Args:
        messages: 原始消息列表

    Returns:
        格式化的对话文本
    """
    formatted = []
    for msg in messages:
        role = str(msg.get("role") or "unknown").strip()
        content = str(msg.get("content") or "").strip()

        # 只保留有内容的消息
        if content:
            role_label = "用户" if role == "user" else "AI助手"
            formatted.append(f"{role_label}: {content}")

    return "\n".join(formatted)


def _build_summary_prompt(formatted_messages: str) -> str:
    """构造LLM提炼摘要的Prompt

    Args:
        formatted_messages: 格式化的对话文本

    Returns:
        LLM Prompt
    """
    return f"""请根据以下对话内容，提炼用户的所有结构化特征。

对话内容：
{formatted_messages}

要求：
1. 提炼性格特质（personality_traits）：如"性格温柔、内向"
2. 提炼价值观（values）：如"重视家庭、重视事业"
3. 提炼择偶期望（partner_expectation）：如"希望找个能理解工作忙碌的人"
4. 提炼生活态度（life_attitude）：如"追求稳定、重视生活质量"
5. 提炼情感需求（emotional_needs）：如"需要理解和支持"
6. 提炼可量化字段（如果用户明确表达）：
   - mbti_type：如"INTJ"、"INFJ"
   - smoking：如"不抽烟"、"抽烟"
   - drinking：如"不喝酒"、"偶尔喝酒"
   - marital_status：如"未婚"、"已婚"
   - has_children：如"没有孩子"、"有孩子"
   - city：如"北京"、"上海"
   - education：如"硕士"、"本科"
   - age：如"28"
   - height：如"170"
   - income：如"年薪20万"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【重要改进：支持负面特征提炼】
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

7. 提炼负面偏好（negative_preferences）：
   - 如果用户明确表达了"不喜欢"、"不要"、"不希望"某种特质，提炼为负面特征
   - 例："不要绿茶的女生" → "不喜欢绿茶、虚伪的人"
   - 例："不想找拜金的人" → "不喜欢拜金、物质的人"
   - 例："不希望对方抽烟" → "不喜欢抽烟的人"
   - 例："不要强势的" → "不喜欢强势、霸道的人"
   - 如果用户没有明确表达负面偏好，输出空字符串 ""

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

⚠️ 重要规则：
- 如果该维度用户没有提及，输出空字符串 ""（不要猜测）
- 如果用户明确表达了，使用简洁、客观、具体的语言
- 每个字段长度不超过 50 字
- 不要添加对话中没有的信息
- 可量化字段必须是用户明确表达的（不要猜测）
- 正面特征：提炼用户表达"喜欢"、"希望"、"想要"的特质
- 负面特征：提炼用户表达"不喜欢"、"不要"、"不希望"的特质（客观提炼，不要回避）
- 摘要会进入向量库用于匹配召回，必须保留具体偏好，不要写泛泛结论
- 不要输出“性格合拍”“真诚沟通”“稳定关系”“有共同话题”“被理解”“情绪价值”这种空话，除非后面紧跟具体展开
- 如果只能总结出空泛词，没有具体条件、行为、节奏或限制，请输出空字符串 ""
- partner_expectation 必须优先保留具体对象特征、现实条件、关系推进节奏、工作生活节奏、城市/距离限制
- emotional_needs 必须写具体需要，比如“有回应”“不冷处理”“下班后有时间陪伴”，不要只写“需要安全感”
- life_attitude 必须写具体生活方式，比如“生活规律”“不喜欢太卷”“作息稳定”，不要只写“热爱生活”

输出格式（JSON）：
{{
    "personality_traits": "性格温柔、内向",
    "values": "重视家庭、重视事业",
    "partner_expectation": "希望找个能理解工作忙碌的人",
    "life_attitude": "追求稳定、重视生活质量",
    "emotional_needs": "需要理解和支持",
    "negative_preferences": "不喜欢绿茶、虚伪的人",
    "mbti_type": "INTJ",
    "smoking": "不抽烟",
    "drinking": "偶尔喝酒",
    "marital_status": "未婚",
    "city": "北京",
    "education": "硕士"
}}

请严格按照JSON格式输出，不要输出任何其他内容。"""


async def _call_llm_for_json(
    prompt: str,
    *,
    llm_base_url: str | None = None,
    llm_api_key: str | None = None,
    llm_model: str | None = None,
) -> dict[str, Any]:
    """调用LLM并返回JSON格式结果

    Args:
        prompt: LLM Prompt
        llm_base_url: LLM API地址
        llm_api_key: LLM API密钥
        llm_model: LLM模型名称

    Returns:
        JSON解析后的字典
    """
    from her_env import env_first
    from openai import AsyncOpenAI

    # 解析配置
    resolved_base_url = llm_base_url or env_first(
        "HER_DISCOVERY_AGENT_BASE_URL",
        "HER_CHAT_AGENT_BASE_URL",
        "DASHSCOPE_BASE_URL",
        default="https://dashscope.aliyuncs.com/compatible-mode/v1",
    )
    resolved_api_key = llm_api_key or env_first(
        "HER_DISCOVERY_AGENT_API_KEY",
        "HER_CHAT_AGENT_API_KEY",
        "DASHSCOPE_API_KEY",
        "OPENAI_API_KEY",
    )
    resolved_model = llm_model or env_first(
        "HER_DISCOVERY_AGENT_MODEL",
        "HER_CHAT_AGENT_MODEL",
        default="qwen-plus",  # ✅ fallback使用存在的模型
    )

    if not resolved_api_key:
        raise ValueError("没有配置 LLM API Key")

    client = AsyncOpenAI(
        base_url=resolved_base_url,
        api_key=resolved_api_key,
        timeout=60.0,  # 摘要生成超时60秒
    )

    # 调用LLM
    response = await client.chat.completions.create(
        model=resolved_model,
        messages=[
            {"role": "system", "content": "你是一个专业的画像分析助手，擅长从对话中提炼用户特征。"},
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,  # 低温度，提高稳定性
        max_tokens=500,
    )

    # 解析返回内容
    content = response.choices[0].message.content or ""
    content = content.strip()

    # 尝试解析JSON
    try:
        # 如果返回内容包含 ```json 标记，提取JSON部分
        if "```json" in content:
            json_start = content.find("```json") + 7
            json_end = content.find("```", json_start)
            content = content[json_start:json_end].strip()
        elif "```" in content:
            json_start = content.find("```") + 3
            json_end = content.find("```", json_start)
            content = content[json_start:json_end].strip()

        return json.loads(content)

    except json.JSONDecodeError as exc:
        _logger.error(f"JSON解析失败: content={content}, error={exc}")
        raise ValueError(f"LLM返回内容不是有效的JSON: {content[:200]}") from exc


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Step 3：存储摘要文本到数据库
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


async def save_session_summary_text(
    session_id: str,
    requester_id: int,
    profile_id: int,
    conversation_type: str,
    summary_data: dict[str, str],
    *,
    dsn: str | None = None,
) -> list[str]:
    """存储摘要文本到数据库

    关键设计：
    - 每个字段单独存储一条记录
    - 使用 conversation_summaries 表
    - 字段名：summary_key，字段值：summary_text

    Args:
        session_id: 会话ID
        requester_id: 用户ID
        profile_id: 画像ID
        conversation_type: 对话类型
        summary_data: 摘要数据字典
        dsn: 数据库连接字符串

    Returns:
        已保存的字段列表
    """
    resolved_dsn = dsn or os.environ.get("HER_PERSONA_DB") or os.environ.get("PARTNER_DISCOVERY_DB") or ""

    if not resolved_dsn:
        _logger.warning("没有配置数据库连接，无法存储摘要")
        return []

    filtered_summary_data: dict[str, str] = {}
    skipped_invalid_keys: list[str] = []
    for summary_key, summary_text in summary_data.items():
        quality = validate_summary_text(summary_key, summary_text)
        if quality != "valid":
            skipped_invalid_keys.append(summary_key)
            _logger.info(
                f"摘要质检未通过，跳过写入: key={summary_key}, quality={quality}, text={summary_text}"
            )
            continue
        filtered_summary_data[summary_key] = summary_text

    if skipped_invalid_keys:
        _logger.info(f"摘要质检跳过字段: {skipped_invalid_keys}")

    if not filtered_summary_data:
        return []

    def _save_sync() -> list[str]:
        from external_systems.partner_discovery_system.discovery_system.storage import connect_db

        conn = connect_db(resolved_dsn)
        try:
            saved_keys: list[str] = []

            for summary_key, summary_text in filtered_summary_data.items():
                if not str(summary_text or "").strip():
                    continue

                # 使用 REPLACE 语法（MySQL不支持 INSERT OR REPLACE）
                # 先删除旧记录，再插入新记录
                conn.execute(
                    """
                    DELETE FROM conversation_summaries
                    WHERE conversation_id = ? AND summary_key = ?
                    """,
                    (session_id, summary_key),
                )

                conn.execute(
                    """
                    INSERT INTO conversation_summaries
                    (conversation_id, conversation_type, requester_id, profile_id,
                     summary_key, summary_text, vector_status, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, 'pending', NOW())
                    """,
                    (session_id, conversation_type, requester_id, profile_id, summary_key, summary_text),
                )

                saved_keys.append(summary_key)

            conn.commit()
            return saved_keys

        finally:
            conn.close()

    # 异步执行（避免阻塞）
    return await asyncio.to_thread(_save_sync)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 辅助函数：异步任务触发
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def trigger_session_end_processing(
    session_id: str,
    requester_id: int,
    profile_id: int,
    conversation_type: str = "discovery",
    *,
    dsn: str | None = None,
    llm_base_url: str | None = None,
    llm_api_key: str | None = None,
    llm_model: str | None = None,
    processed_at: datetime | None = None,  # ✅ 新增：上次处理时间，用于增量处理
    storage: Any | None = None,  # ✅ 新增：storage对象，用于更新processed_at
) -> threading.Thread | None:
    """触发会话结束处理（后台线程异步任务）

    使用场景：
    1. 新建会话时（处理上一个会话）
    2. 切换会话时（处理切换前的会话）
    3. 30分钟无活动时
    4. 会话销毁时

    设计方案：
    - 使用独立线程运行异步任务
    - daemon=True：守护线程，不阻塞主进程退出
    - asyncio.run()：在新线程中创建临时事件循环
    - 真正的后台处理，不阻塞主流程
    - ✅ 支持增量处理：传入 processed_at，只处理新增内容
    - ✅ 处理完成后更新 processed_at

    Args:
        session_id: 会话ID
        requester_id: 用户ID
        profile_id: 画像ID
        conversation_type: 对话类型

        dsn: 数据库连接字符串
        llm_base_url: LLM API地址
        llm_api_key: LLM API密钥
        llm_model: LLM模型名称
        processed_at: 上次处理时间（用于增量处理）
        storage: storage对象（用于更新processed_at）

    Returns:
        threading.Thread 对象（可用于追踪任务状态）
    """
    import threading

    try:
        # 定义线程执行函数
        def run_async_in_thread() -> None:
            """在线程中运行异步任务"""
            try:
                result = asyncio.run(
                    process_session_end(
                        session_id,
                        requester_id,
                        profile_id,
                        conversation_type,
                        dsn=dsn,
                        llm_base_url=llm_base_url,
                        llm_api_key=llm_api_key,
                        llm_model=llm_model,
                        processed_at=processed_at,  # ✅ 新增：传入 processed_at
                        storage=storage,  # ✅ 新增：传入 storage
                    )
                )

                # ✅ 新增：处理完成后更新 processed_at
                if result.get("success") and storage:
                    session = storage.get_session(session_id)
                    if session:
                        # 更新 processed_at 为会话的 updated_at
                        session.processed_at = session.updated_at
                        storage.save_session(session)
                        _logger.info(
                            f"更新 processed_at: session_id={session_id}, "
                            f"processed_at={session.processed_at}"
                        )

            except Exception as exc:
                _logger.error(
                    f"线程中执行会话结束处理失败: session_id={session_id}, error={exc}",
                    exc_info=True,
                )

        # 创建守护线程（后台运行，不阻塞主进程退出）
        thread = threading.Thread(
            target=run_async_in_thread,
            name=f"session_end_{session_id}",
            daemon=True,  # 守护线程：主进程退出时自动结束
        )

        # 启动线程
        thread.start()

        _logger.info(
            f"触发会话结束处理（线程模式）: session_id={session_id}, thread={thread.name}, "
            f"processed_at={processed_at}"
        )

        return thread

    except Exception as exc:
        _logger.error(
            f"触发会话结束处理失败: session_id={session_id}, error={exc}",
            exc_info=True,
        )
        return None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 辅助函数：查询历史摘要（用于增量合并）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


async def load_latest_summary_for_user(
    requester_id: int,
    summary_key: str,
    *,
    dsn: str | None = None,
) -> str | None:
    """查询用户某个字段的历史摘要（最新一条）

    用于增量合并：如果本次对话没有提及某字段，保留历史数据。

    Args:
        requester_id: 用户ID
        summary_key: 字段名（如 personality_traits）
        dsn: 数据库连接字符串

    Returns:
        历史摘要文本（如果存在），否则返回 None
    """
    resolved_dsn = dsn or os.environ.get("HER_PERSONA_DB") or os.environ.get("PARTNER_DISCOVERY_DB") or ""

    if not resolved_dsn:
        return None

    def _load_sync() -> str | None:
        from external_systems.partner_discovery_system.discovery_system.storage import connect_db

        conn = connect_db(resolved_dsn)
        try:
            row = conn.execute(
                """
                SELECT summary_text
                FROM conversation_summaries
                WHERE requester_id = ? AND summary_key = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (requester_id, summary_key),
            ).fetchone()

            if row:
                return str(row.get("summary_text") or "").strip()

            return None

        finally:
            conn.close()

    # 异步执行
    return await asyncio.to_thread(_load_sync)


async def merge_with_existing_profile(
    new_summary: dict[str, str],
    requester_id: int,
    *,
    dsn: str | None = None,
) -> dict[str, str]:
    """增量合并：新摘要 + 历史数据

    合并规则：
    - 新数据非空 → 用新数据
    - 新数据为空 → 用历史数据（如果存在）

    Args:
        new_summary: 本次提炼的摘要
        requester_id: 用户ID
        dsn: 数据库连接字符串

    Returns:
        合并后的摘要数据
    """
    merged: dict[str, str] = {}

    for key in ["personality_traits", "values", "partner_expectation", "life_attitude", "emotional_needs"]:
        new_value = str(new_summary.get(key) or "").strip()

        if new_value:
            # 新数据非空，用新数据
            merged[key] = new_value
        else:
            # 新数据为空，查询历史数据
            historical = await load_latest_summary_for_user(requester_id, key, dsn=dsn)
            if historical:
                merged[key] = historical

    return merged


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Step 4：向量化存储（新增）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


async def save_vectors_for_summary(
    session_id: str,
    requester_id: int,
    summary_data: dict[str, str],
    *,
    embedding_model: str | None = None,
    embedding_api_key: str | None = None,
    embedding_base_url: str | None = None,
) -> list[str]:
    """将摘要数据向量化并存储到 Milvus（批量处理，节省LLM成本）

    改造核心（成本优化）：
    - 合并LLM调用：从每个字段单独调用 → 一次性批量判断所有字段
    - LLM调用次数：从6次 → 2次（节省66%成本）
    - 批量生成向量：使用generate_embeddings批量接口（节省embedding API调用）

    Args:
        session_id: 会话ID
        requester_id: 用户ID
        summary_data: 摘要数据字典（如 {"personality_traits": "性格温柔", "values": "重视家庭"}）

        embedding_model: Embedding 模型名称（可选，已废弃）
        embedding_api_key: Embedding API密钥（可选，已废弃）
        embedding_base_url: Embedding API地址（可选，已废弃）

    Returns:
        成功向量化的字段列表
    """
    from match_domain.ai_merge_handler import ai_batch_merge_and_vectorize

    try:
        # 批量处理所有字段（一次性LLM判断 + 批量向量生成）
        results = await ai_batch_merge_and_vectorize(
            user_id=requester_id,
            all_summary_data=summary_data,
            conversation_id=session_id,
        )

        # 提取成功向量化的字段
        vectorized_keys = [
            key for key, result in results.items()
            if result.get("vector_saved")
        ]

        # 记录处理结果
        for key, result in results.items():
            ai_decision = result.get("ai_decision")
            if ai_decision:
                _logger.info(
                    f"AI判断处理完成: key={key}\n"
                    f"历史文本: {ai_decision.get('historical_text')}\n"
                    f"新文本: {ai_decision.get('new_text')}\n"
                    f"最终文本: {result['final_text']}\n"
                    f"AI判断: {ai_decision['relation_type']}\n"
                    f"AI决定: {ai_decision['action']}\n"
                    f"判断理由: {ai_decision['reason']}"
                )
            else:
                _logger.info(
                    f"首次记录完成: key={key}, "
                    f"text={result['final_text']}"
                )

        if not vectorized_keys:
            _logger.warning(f"所有字段向量化失败: requester_id={requester_id}")

        return vectorized_keys

    except Exception as exc:
        # 修复：使用 repr() 包装异常，避免 JSON 字符串中的花括号被 f-string 解析
        _logger.error(f"批量处理失败: requester_id={requester_id}, error={repr(exc)}")
        return []


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Step 5：清空 working_criteria（会话结束后清理临时搜索条件）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


async def clear_working_criteria(
    session_id: str,
    *,
    dsn: str | None = None,
) -> bool:
    """清空 session 的 working_criteria（临时搜索条件）

    关键设计：
    - 会话结束后清空临时搜索条件（防止下次对话使用旧条件）
    - 只清空 working_criteria，不影响其他 session 状态
    - 从数据库重新加载 session（避免内存对象销毁问题）

    Args:
        session_id: 会话ID
        dsn: 数据库连接字符串（可选，默认从环境变量读取）

    Returns:
        是否成功清空

    设计原理：
    - working_criteria 的生命周期：本轮对话内有效
    - 会话结束后，working_criteria 应清空
    - 下次对话重新收集搜索条件
    """
    resolved_dsn = dsn or os.environ.get("PARTNER_DISCOVERY_DB") or ""

    if not resolved_dsn:
        _logger.warning("没有配置 PARTNER_DISCOVERY_DB，无法清空 working_criteria")
        return False

    def _clear_sync() -> bool:
        from external_systems.partner_discovery_system.discovery_system.storage import connect_db, json_loads, json_dumps

        conn = connect_db(resolved_dsn)
        try:
            # 查询当前 session 状态
            # 修复：使用正确的字段名 state_json（而非 session_state）
            row = conn.execute(
                """
                SELECT state_json
                FROM discovery_agent_sessions
                WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()

            if not row:
                _logger.warning(f"session {session_id} 不存在，无法清空 working_criteria")
                return False

            # 解析当前状态
            # 修复：使用正确的字段名 state_json（而非 session_state）
            current_state = json_loads(str(row.get("state_json") or "null"), None)
            if not isinstance(current_state, dict):
                current_state = {}

            # 检查是否有 working_criteria
            if "working_criteria" not in current_state:
                _logger.info(f"session {session_id} 没有 working_criteria，无需清空")
                return True

            # 清空 working_criteria
            current_state["working_criteria"] = {}

            # 更新数据库
            # 修复：使用正确的字段名 state_json（而非 session_state）
            conn.execute(
                """
                UPDATE discovery_agent_sessions
                SET state_json = ?
                WHERE session_id = ?
                """,
                (json_dumps(current_state), session_id),
            )

            conn.commit()

            _logger.info(f"working_criteria 已清空: session_id={session_id}")
            return True

        except Exception as exc:
            _logger.error(f"清空 working_criteria 失败: session_id={session_id}, error={exc}")
            conn.rollback()
            return False

        finally:
            conn.close()

    # 异步执行（避免阻塞）
    return await asyncio.to_thread(_clear_sync)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 新增：分流函数（V2修正版）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def split_by_quantifiability(summary_data: dict[str, str]) -> tuple[dict[str, str], dict[str, str]]:
    """分流：分离可量化字段和不可量化字段

    V2修正版关键设计：
    - 可量化字段（INTJ、不抽烟）→ 写入画像表（user_personas + user_persona_observations）
    - 不可量化字段（性格温柔）→ 写入摘要表+向量库（conversation_summaries + Milvus）
    - profiles 表不支持会话后写入（只允许用户手动编辑）

    Args:
        summary_data: LLM提炼的结构化摘要

    Returns:
        (quantifiable_data, non_quantifiable_data)
        - quantifiable_data: 可量化字段（写画像表）
        - non_quantifiable_data: 不可量化字段（写摘要+向量库）

    例子：
        输入：{
            mbti_type: "INTJ",
            smoking: false,
            personality_traits: "性格温柔"
        }

        输出：
        quantifiable_data = {
            mbti_type: "INTJ",
            smoking: false
        }

        non_quantifiable_data = {
            personality_traits: "性格温柔"
        }
    """
    quantifiable_data: dict[str, str] = {}
    non_quantifiable_data: dict[str, str] = {}

    for key, value in summary_data.items():
        if not str(value or "").strip():
            continue

        if key in SUMMARY_FIELD_KEYS:
            non_quantifiable_data[key] = value
            continue

        if key in STRUCTURED_QUANTIFIABLE_FIELDS:
            quantifiable_data[key] = value
        else:
            # 兜底策略：未知字段默认不进入摘要表，避免脏数据污染 conversation_summaries
            quantifiable_data[key] = value

    _logger.info(
        f"分流完成: quantifiable_fields={list(quantifiable_data.keys())}, "
        f"non_quantifiable_fields={list(non_quantifiable_data.keys())}"
    )

    return quantifiable_data, non_quantifiable_data


def _contains_any_marker(text: str, markers: tuple[str, ...]) -> bool:
    return any(marker in text for marker in markers)


def validate_summary_text(field_name: str, text: str) -> str:
    """校验摘要文本质量。

    返回：
    - valid: 可以写入 conversation_summaries / 向量库
    - weak: 信息量不足，默认不写入
    - invalid: 明确禁止写入
    """
    normalized_field = str(field_name or "").strip()
    normalized_text = str(text or "").strip()
    if not normalized_text:
        return "invalid"

    if normalized_field in STRUCTURED_QUANTIFIABLE_FIELDS:
        return "invalid"

    if normalized_field not in SUMMARY_FIELD_KEYS:
        return "invalid"

    if any(pattern.match(normalized_text) for pattern in GENERIC_SUMMARY_PATTERNS):
        return "invalid"

    has_abstract = _contains_any_marker(normalized_text, ABSTRACT_SUMMARY_TERMS)
    common_concrete = _contains_any_marker(normalized_text, COMMON_CONCRETE_SIGNALS)
    field_specific_concrete = _contains_any_marker(
        normalized_text,
        FIELD_SPECIFIC_SIGNALS.get(normalized_field, ()),
    )
    has_concrete = common_concrete or field_specific_concrete

    if has_abstract and not has_concrete:
        return "invalid"

    if not has_concrete:
        return "weak"

    return "valid"


def filter_valid_summary_data(summary_data: dict[str, str]) -> tuple[dict[str, str], dict[str, str]]:
    """过滤并返回可落库摘要，以及被跳过字段的质量结果。"""
    filtered: dict[str, str] = {}
    rejected: dict[str, str] = {}
    for summary_key, summary_text in summary_data.items():
        quality = validate_summary_text(summary_key, summary_text)
        if quality == "valid":
            filtered[summary_key] = summary_text
        else:
            rejected[summary_key] = quality
    return filtered, rejected


def normalize_quantifiable_patch(quantifiable_data: dict[str, str]) -> dict[str, Any]:
    """把会话提炼出的结构化字段映射到 user_personas 可接受字段。

    规则：
    - 只映射 user_personas 体系中已有合法落点的字段
    - age/city/income/height 这类无 persona 落点的结构化字段直接丢弃
    - 不允许写 profiles
    """
    normalized: dict[str, Any] = {}

    mbti_type = str(quantifiable_data.get("mbti_type") or "").strip().upper()
    if mbti_type in VALID_MBTI_TYPES:
        normalized["self_personality_traits_json"] = json.dumps(
            {"mbti": {"type_code": mbti_type}},
            ensure_ascii=False,
            sort_keys=True,
        )

    # 仅保留 persona 表中已有真实落点的字段；其余结构化字段直接丢弃。
    allowed = {
        key: value
        for key, value in normalized.items()
        if key in COLLECTED_PERSONA_FIELDS or key == "self_personality_traits_json"
    }
    return allowed


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 新增：可量化字段写入函数（V2修正版）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


async def save_quantifiable_to_persona_tables(
    user_key: str,
    profile_id: int,
    session_id: str,
    quantifiable_data: dict[str, str],
    *,
    dsn: str | None = None,
) -> dict[str, Any]:
    """将可量化字段写入画像表

    V2修正版关键设计：
    - 写入位置：user_persona_observations + user_personas
    - ❌ profiles 表不支持会话后写入（只允许用户手动编辑）
    - 只写入可量化字段（INTJ、不抽烟等）
    - 不写入不可量化字段（性格温柔等主观描述）
    - 每条记录带session_id（支持溯源）

    Args:
        user_key: 用户标识
        profile_id: 画像ID
        session_id: 会话ID（用于溯源）
        quantifiable_data: 可量化字段数据
        dsn: 数据库连接字符串

    Returns:
        画像写入结果
    """
    try:
        from persona_memory_sync.persona_memory_lib import apply_persona_patch
    except ImportError:
        _logger.error("导入 apply_persona_patch 失败，无法写入画像")
        return {"success": False, "error": "import_failed"}

    resolved_dsn = dsn or os.environ.get("HER_PERSONA_DB") or os.environ.get("PARTNER_DISCOVERY_DB") or ""

    if not resolved_dsn:
        _logger.warning("没有配置数据库连接，无法写入画像")
        return {"success": False, "error": "dsn_not_configured"}

    normalized_patch = normalize_quantifiable_patch(quantifiable_data)
    if not normalized_patch:
        _logger.info("没有可映射的结构化字段可写入 user_personas")
        return {
            "success": True,
            "user_key": user_key,
            "applied_fields": [],
            "skipped_fields": [],
            "synced_profile": False,
            "message": "no_mappable_quantifiable_fields",
        }

    def _save_sync() -> dict[str, Any]:
        """同步写入画像表"""
        try:
            # 构造 evidence_text（记录溯源）
            evidence_text = f"会话结束后LLM提炼（session_id={session_id})"

            # 调用 apply_persona_patch 统一写入
            result = apply_persona_patch(
                source=resolved_dsn,
                user_key=user_key,
                source_type="explicit_confirmation",
                source_channel="discovery_session_end",  # 来源标识
                normalized_patch=normalized_patch,
                confidence_score=85,  # 会结束后LLM提炼的置信度
                evidence_text=evidence_text,
                conversation_ref=session_id,  # 溯源ID
                apply_scope="persona_only",
                sync_profile=False,
            )

            _logger.info(
                f"可量化字段写入成功: user_key={user_key}, "
                f"applied_fields={result.get('applied_fields', [])}"
            )

            return {
                "success": True,
                "user_key": user_key,
                "applied_fields": result.get("applied_fields", []),
                "skipped_fields": result.get("skipped_fields", []),
                "synced_profile": False,
            }

        except Exception as exc:
            _logger.error(f"可量化字段写入失败: user_key={user_key}, error={exc}")
            return {"success": False, "error": str(exc)[:200]}

    # 异步执行（避免阻塞）
    return await asyncio.to_thread(_save_sync)


__all__ = [
    "process_session_end",
    "load_session_messages_from_db",
    "generate_structured_summary",
    "save_session_summary_text",
    "trigger_session_end_processing",
    "load_latest_summary_for_user",
    "merge_with_existing_profile",
    "save_vectors_for_summary",
    "clear_working_criteria",
    "split_by_quantifiability",  # 新增导出
    "save_quantifiable_to_persona_tables",  # 新增导出
]
