"""AI一次性处理：摘要文本合并 + 向量存储

核心思想：只让AI判断一次，结果同时用于：
1. 摘要文本合并（保存合并后的文本）
2. 向量存储（生成合并后的向量）

优势：
- 节省成本：LLM调用从2次变成1次（节省50%）
- 节省时间：处理时间从1秒变成0.5秒（节省50%）
- 逻辑一致：两个阶段用同一个判断结果
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime
from typing import Any

_logger = logging.getLogger(__name__)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 核心函数：AI一次性处理
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


async def ai_merge_and_vectorize(
    user_id: int,
    vector_type: str,
    new_text: str,
    historical_text: str | None,
    conversation_id: str,
    conversation_time: datetime | None = None,
) -> dict[str, Any]:
    """
    AI一次性处理：摘要文本合并 + 向量存储

    只让AI判断一次，结果同时用于：
    1. 摘要文本合并（保存合并后的文本）
    2. 向量存储（生成合并后的向量）

    Args:
        user_id: 用户ID
        vector_type: 向量类型（personality_traits等）
        new_text: 新提炼的文本
        historical_text: 历史文本（如果没有历史，传None）
        conversation_id: 对话ID
        conversation_time: 对话时间（用于判断短期/长期变化）

    Returns:
        {
            "final_text": "最终文本（合并或覆盖后）",
            "ai_decision": {
                "relation_type": "补充/冲突/细化",
                "confidence": "high/medium/low",
                "action": "merge/replace",
                "merged_text": "合并后的文本（如果merge）",
                "reason": "判断理由",
            },
            "text_saved": True,  # 摘要文本已保存
            "vector_saved": True, # 向量已存储
        }
    """

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Step 1：如果没有历史数据，直接保存（首次记录）
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    if not historical_text:
        _logger.info(
            f"首次记录: user_id={user_id}, vector_type={vector_type}, "
            f"text={new_text}"
        )

        # 直接保存摘要文本
        await save_summary_text(
            user_id=user_id,
            vector_type=vector_type,
            summary_text=new_text,
            conversation_id=conversation_id,
        )

        # 生成向量并存储
        from match_domain.embedding_service import EmbeddingService
        from match_domain.vector_store_lite import VectorStoreLite

        embedding_service = EmbeddingService(model_name="text-embedding-v3")
        vector_store = VectorStoreLite()

        try:
            final_vector = await embedding_service.generate_embedding(new_text)

            result = vector_store.save_vector_with_version(
                user_id=user_id,
                vector_type=vector_type,
                embedding=final_vector,
                raw_text=new_text,
                conversation_id=conversation_id,
            )

            return {
                "final_text": new_text,
                "ai_decision": None,  # 无需AI判断
                "text_saved": True,
                "vector_saved": result.get("success", False),
            }
        finally:
            # ⚠️ 重要：主动关闭连接，避免 "Task exception was never retrieved" 错误
            await embedding_service.aclose()
            vector_store.close()

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Step 2：AI判断语义关系（只判断一次）
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    ai_decision = await _ai_judge_semantic_relation(
        historical_text=historical_text,
        new_text=new_text,
        vector_type=vector_type,
        conversation_time=conversation_time,
    )

    _logger.info(
        f"AI判断完成: {historical_text} → {new_text}\n"
        f"关系类型: {ai_decision['relation_type']}\n"
        f"AI决定: {ai_decision['action']}\n"
        f"判断理由: {ai_decision['reason']}"
    )

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Step 3：根据AI判断，确定最终文本
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    if ai_decision["action"] == "merge":
        # AI决定合并
        final_text = ai_decision["merged_text"]
    else:
        # AI决定覆盖
        final_text = new_text

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Step 4：保存摘要文本（阶段1：摘要文本合并）
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    await save_summary_text(
        user_id=user_id,
        vector_type=vector_type,
        summary_text=final_text,
        conversation_id=conversation_id,
        vector_status='pending',  # ← 新增：标记为待处理
    )

    _logger.info(f"摘要文本已保存: {final_text}")

    # Step 5：生成向量并存储（阶段2：向量存储）
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    embedding_service = None
    vector_store = None

    try:
        from match_domain.embedding_service import EmbeddingService
        from match_domain.vector_store_lite import VectorStoreLite

        embedding_service = EmbeddingService(model_name="text-embedding-v3")
        vector_store = VectorStoreLite()

        final_vector = await embedding_service.generate_embedding(final_text)

        result = vector_store.save_vector_with_version(
            user_id=user_id,
            vector_type=vector_type,
            embedding=final_vector,
            raw_text=final_text,
            conversation_id=conversation_id,
        )

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 新增：根据向量库写入结果更新状态
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

        if result.get("success"):
            # 成功：更新状态为 'done'
            await update_vector_status(
                user_id=user_id,
                vector_type=vector_type,
                status='done',
            )
            _logger.info(
                f"向量已存储: {vector_type}, version={result.get('version')}, "
                f"status=done"
            )
        else:
            # 失败：更新状态为 'failed'
            await update_vector_status(
                user_id=user_id,
                vector_type=vector_type,
                status='failed',
                error_message=result.get('error'),
            )
            _logger.error(
                f"向量存储失败: {vector_type}, error={result.get('error')}, "
                f"status=failed"
            )

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # Step 6：返回结果
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

        return {
            "final_text": final_text,
            "ai_decision": ai_decision,
            "text_saved": True,
            "vector_saved": result.get("success", False),
            "vector_status": 'done' if result.get("success") else 'failed',
        }

    except Exception as exc:
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 新增：异常时标记状态为 'failed'
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

        await update_vector_status(
            user_id=user_id,
            vector_type=vector_type,
            status='failed',
            error_message=str(exc)[:200],
        )

        _logger.error(f"向量存储异常: {exc}")

        return {
            "final_text": final_text,
            "ai_decision": ai_decision,
            "text_saved": True,
            "vector_saved": False,
            "vector_status": 'failed',
            "error": str(exc)[:200],
        }

    finally:
        # ⚠️ 重要：主动关闭连接，避免 "Task exception was never retrieved" 错误
        if embedding_service:
            await embedding_service.aclose()
        if vector_store:
            vector_store.close()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# AI判断函数
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


async def _ai_judge_semantic_relation(
    historical_text: str,
    new_text: str,
    vector_type: str,
    conversation_time: datetime | None = None,
) -> dict[str, Any]:
    """
    AI判断新旧内容的语义关系

    判断维度：
    1. 语义相似度（cosine similarity）
    2. 逻辑关系（补充/冲突/细化）
    3. 时间因素（短期补充 vs 镆期变化）

    Args:
        historical_text: 历史版本文本
        new_text: 新版本文本
        vector_type: 向量类型
        conversation_time: 对话时间

    Returns:
        {
            "relation_type": "补充/冲突/细化",
            "confidence": "high/medium/low",
            "action": "merge/replace",
            "merged_text": "合并后的文本（如果merge）",
            "reason": "判断理由",
        }
    """

    # 构建AI判断Prompt
    prompt = _build_semantic_judge_prompt(
        historical_text=historical_text,
        new_text=new_text,
        vector_type=vector_type,
        conversation_time=conversation_time,
    )

    # 调用LLM
    try:
        ai_response = await _call_llm_for_json(prompt)

        # 验证返回格式
        required_fields = ["relation_type", "confidence", "action", "reason"]
        if not all(field in ai_response for field in required_fields):
            raise ValueError(f"AI返回格式错误，缺少必要字段")

        # 如果action是merge，检查merged_text
        if ai_response["action"] == "merge" and "merged_text" not in ai_response:
            raise ValueError("AI决定merge但未提供merged_text")

        return ai_response

    except Exception as exc:
        _logger.error(f"AI判断失败: {exc}")

        # Fallback机制
        return _fallback_decision(historical_text, new_text)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Prompt构建
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def _build_semantic_judge_prompt(
    historical_text: str,
    new_text: str,
    vector_type: str,
    conversation_time: datetime | None = None,
) -> str:
    """
    构建AI判断Prompt

    设计原则：
    - 提供完整上下文
    - 明确判断维度
    - 要求输出判断理由
    - 严格JSON格式输出

    安全改进：
    - 转义 historical_text 和 new_text 中的花括号
    - 防止 f-string 解析错误（当字符串包含 JSON 格式时）
    """

    # 转义花括号，防止 f-string 解析错误
    historical_text_safe = historical_text.replace("{", "{{").replace("}", "}}")
    new_text_safe = new_text.replace("{", "{{").replace("}", "}}")

    # 时间因素描述
    time_description = "未知时间"
    if conversation_time:
        days_gap = (datetime.now() - conversation_time).days
        if days_gap <= 1:
            time_description = "短期变化（同一天内）：倾向于补充"
        elif days_gap <= 7:
            time_description = "短期内变化（一周内）：可能是补充"
        elif days_gap <= 30:
            time_description = "中期变化（一个月内）：可能是补充或变化"
        else:
            time_description = "长期变化（超过一个月）：可能是真实变化"

    return f"""你是一个画像分析专家，擅长分析用户特征的语义关系。

请分析以下新旧数据的关系：

【历史版本】："{historical_text_safe}"
【新版本】："{new_text_safe}"
【时间因素】：{time_description}

请判断它们的关系类型：

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

【三种关系类型】：

1. **补充关系**：
   - 新内容补充旧内容，两者语义兼容
   - 例："内向" → "喜欢安静"（内向的人通常喜欢安静）
   - 处理：合并 → "内向、喜欢安静"

2. **冲突关系**：
   - 新内容与旧内容矛盾，语义相反
   - 例："喜欢热闹" → "喜欢安静"（长期变化，真实变化）
   - 处理：覆盖 → 只保留"喜欢安静"

3. **细化关系**：
   - 新内容更具体，包含旧内容
   - 例："温柔" → "温柔、能理解工作"（后者包含前者）
   - 处理：合并 → "温柔、能理解工作"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

【判断规则】：
1. 优先考虑语义相似度和逻辑关系
2. 时间因素作为辅助判断（短期倾向于补充，长期可能是真实变化）
3. 如果不确定，优先选择"补充"（保留信息）
4. 如果明确冲突，选择"冲突"（覆盖旧版本）

【输出格式】：
{{
    "relation_type": "补充/冲突/细化",
    "confidence": "high/medium/low",
    "action": "merge/replace",
    "merged_text": "合并后的文本（如果action=merge，必须提供）",
    "reason": "判断理由（一句话，简洁明了）"
}}

请严格按照JSON格式输出，不要输出任何其他内容。
"""


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# LLM调用
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


async def _call_llm_for_json(prompt: str) -> dict[str, Any]:
    """
    调用LLM并返回JSON格式结果

    配置：
    - 使用环境变量 HER_DISCOVERY_AGENT_MODEL / HER_CHAT_AGENT_MODEL（和 session_end_processor 保持一致）
    - fallback 使用 qwen-plus（存在的模型）
    - temperature: 0.3（低温度，提高稳定性）
    """

    try:
        from her_env import env_first
        from openai import AsyncOpenAI

        base_url = env_first(
            "HER_DISCOVERY_AGENT_BASE_URL",
            "HER_CHAT_AGENT_BASE_URL",
            "DASHSCOPE_BASE_URL",
            default="https://dashscope.aliyuncs.com/compatible-mode/v1",
        )
        api_key = env_first(
            "HER_DISCOVERY_AGENT_API_KEY",
            "HER_CHAT_AGENT_API_KEY",
            "DASHSCOPE_API_KEY",
            "OPENAI_API_KEY",
            default="",
        )
        model = env_first(
            "HER_DISCOVERY_AGENT_MODEL",
            "HER_CHAT_AGENT_MODEL",
            default="qwen-plus",  # ✅ fallback使用存在的模型
        )

        client = AsyncOpenAI(
            base_url=base_url,
            api_key=api_key,
        )

        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=500,
        )

        content = response.choices[0].message.content

        # 解析JSON
        return json.loads(content)

    except Exception as exc:
        _logger.error(f"LLM调用失败: {exc}")
        raise


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Fallback机制
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def _fallback_decision(
    historical_text: str,
    new_text: str,
) -> dict[str, Any]:
    """
    Fallback决策：AI判断失败时的默认规则

    保守策略：简单拼接合并（保留信息）
    """

    _logger.warning(
        f"AI判断失败，使用fallback决策: "
        f"historical={historical_text}, new={new_text}"
    )

    # 保守策略：简单拼接合并
    merged_text = f"{historical_text}、{new_text}"

    return {
        "relation_type": "补充（fallback）",
        "confidence": "low",
        "action": "merge",
        "merged_text": merged_text,
        "reason": "AI判断失败，fallback保守合并",
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 辅助函数：摘要文本保存与查询
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


async def save_summary_text(
    user_id: int,
    vector_type: str,
    summary_text: str,
    conversation_id: str,
    vector_status: str = 'pending',  # ← 新增参数：支持自定义 vector_status
) -> None:
    """
    保存摘要文本到数据库

    改进：支持自定义 vector_status，用于失败处理

    Args:
        user_id: 用户ID
        vector_type: 向量类型（personality_traits等）
        summary_text: 摘要文本
        conversation_id: 对话ID
        vector_status: 向量化状态（pending/done/failed/retrying）
    """

    def _save_sync():
        from persona_memory_sync.persona_memory_lib import (
            mysql_connect,
            release_persona_connection,
            quote_mysql_ident,
        )

        dsn = os.environ.get("PERSONA_MEMORY_MYSQL_SOURCE", "")
        if not dsn:
            _logger.warning("没有配置 PERSONA_MEMORY_MYSQL_SOURCE，无法保存摘要文本")
            return

        conn = mysql_connect(dsn, use_pool=True, timeout=10.0)
        try:
            with conn.cursor() as cursor:
                # 先删除旧记录
                cursor.execute(
                    f"""
                    DELETE FROM {quote_mysql_ident("conversation_summaries")}
                    WHERE requester_id = %s AND summary_key = %s
                    """,
                    (user_id, vector_type),
                )

                # 插入新记录（支持自定义 vector_status）
                cursor.execute(
                    f"""
                    INSERT INTO {quote_mysql_ident("conversation_summaries")}
                    (conversation_id, conversation_type, requester_id, profile_id,
                     summary_key, summary_text, vector_status, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
                    """,
                    (conversation_id, 'discovery', user_id, user_id, vector_type, summary_text, vector_status),
                )

            conn.commit()
            _logger.info(
                f"摘要文本保存成功: user_id={user_id}, key={vector_type}, "
                f"text={summary_text}, status={vector_status}"
            )

        finally:
            release_persona_connection(dsn, conn)

    # 异步执行
    await asyncio.to_thread(_save_sync)


async def load_historical_summary(
    user_id: int,
    vector_type: str,
) -> str | None:
    """
    查询历史摘要文本

    从 conversation_summaries 表查询最新记录
    """

    def _load_sync():
        from persona_memory_sync.persona_memory_lib import (
            mysql_connect,
            release_persona_connection,
            quote_mysql_ident,
        )

        dsn = os.environ.get("PERSONA_MEMORY_MYSQL_SOURCE", "")
        if not dsn:
            return None

        conn = mysql_connect(dsn, use_pool=True, timeout=10.0)
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT summary_text
                    FROM {quote_mysql_ident("conversation_summaries")}
                    WHERE requester_id = %s AND summary_key = %s
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    (user_id, vector_type),
                )
                row = cursor.fetchone()
                return row.get("summary_text") if row else None

        finally:
            release_persona_connection(dsn, conn)

    # 异步执行
    return await asyncio.to_thread(_load_sync)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 新增：状态更新函数（用于失败处理）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


async def update_vector_status(
    user_id: int,
    vector_type: str,
    status: str,
    error_message: str | None = None,
    retry_count: int | None = None,
) -> None:
    """
    更新 vector_status 状态（用于失败处理和重试）

    Args:
        user_id: 用户ID
        vector_type: 向量类型
        status: 新状态（pending/done/failed/retrying）
        error_message: 错误信息（可选）
        retry_count: 重试次数（可选）
    """

    def _update_sync():
        from persona_memory_sync.persona_memory_lib import (
            mysql_connect,
            release_persona_connection,
            quote_mysql_ident,
        )

        dsn = os.environ.get("PERSONA_MEMORY_MYSQL_SOURCE", "")
        if not dsn:
            _logger.warning("没有配置 PERSONA_MEMORY_MYSQL_SOURCE，无法更新状态")
            return

        conn = mysql_connect(dsn, use_pool=True, timeout=10.0)
        try:
            with conn.cursor() as cursor:
                # 构建更新字段
                update_fields = ["vector_status = %s", "updated_at = NOW()"]
                params = [status]

                if error_message:
                    update_fields.append("error_message = %s")
                    params.append(error_message)

                if retry_count is not None:
                    update_fields.append("retry_count = %s")
                    params.append(retry_count)

                # 执行更新
                cursor.execute(
                    f"""
                    UPDATE {quote_mysql_ident("conversation_summaries")}
                    SET {', '.join(update_fields)}
                    WHERE requester_id = %s AND summary_key = %s
                    """,
                    params + [user_id, vector_type],
                )

            conn.commit()
            _logger.info(
                f"状态更新成功: user_id={user_id}, key={vector_type}, "
                f"status={status}, error={error_message}, retry_count={retry_count}"
            )

        except Exception as exc:
            _logger.error(f"状态更新失败: {exc}")
            # 不抛出异常，避免影响主流程

        finally:
            release_persona_connection(dsn, conn)

    await asyncio.to_thread(_update_sync)


async def query_failed_vector_records(
    dsn: str | None = None,
    max_retry_count: int = 3,
) -> list[dict[str, Any]]:
    """
    查询 vector_status='failed' 且 retry_count < max_retry_count 的记录

    Args:
        dsn: 数据库连接字符串
        max_retry_count: 最大重试次数

    Returns:
        失败记录列表
    """

    def _query_sync():
        from persona_memory_sync.persona_memory_lib import (
            mysql_connect,
            release_persona_connection,
            quote_mysql_ident,
        )

        resolved_dsn = dsn or os.environ.get("PERSONA_MEMORY_MYSQL_SOURCE", "")
        if not resolved_dsn:
            return []

        conn = mysql_connect(resolved_dsn, use_pool=True, timeout=10.0)
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT requester_id, profile_id, summary_key, summary_text,
                           conversation_id, retry_count, error_message
                    FROM {quote_mysql_ident("conversation_summaries")}
                    WHERE vector_status = 'failed' AND retry_count < %s
                    ORDER BY created_at DESC
                    LIMIT 50
                    """,
                    (max_retry_count,),
                )

                rows = cursor.fetchall()
                return list(rows) if rows else []

        finally:
            release_persona_connection(resolved_dsn, conn)

    return await asyncio.to_thread(_query_sync)


async def retry_vector_write(record: dict[str, Any]) -> bool:
    """
    重试向量写入

    Args:
        record: 失败记录（包含 requester_id, summary_key, summary_text 等）

    Returns:
        是否成功
    """
    try:
        user_id = record.get("requester_id")
        vector_type = record.get("summary_key")
        summary_text = record.get("summary_text")
        conversation_id = record.get("conversation_id")
        retry_count = record.get("retry_count", 0)

        _logger.info(
            f"重试向量写入: user_id={user_id}, key={vector_type}, "
            f"retry_count={retry_count}"
        )

        # 更新状态为 'retrying'
        await update_vector_status(
            user_id=user_id,
            vector_type=vector_type,
            status='retrying',
            retry_count=retry_count + 1,
        )

        # 重新生成向量并存储
        from match_domain.embedding_service import EmbeddingService
        from match_domain.vector_store_lite import VectorStoreLite

        embedding_service = EmbeddingService(model_name="text-embedding-v3")
        vector_store = VectorStoreLite()

        try:
            final_vector = await embedding_service.generate_embedding(summary_text)

            result = vector_store.save_vector_with_version(
                user_id=user_id,
                vector_type=vector_type,
                embedding=final_vector,
                raw_text=summary_text,
                conversation_id=conversation_id,
            )

            if result.get("success"):
                # 成功：更新状态为 'done'
                await update_vector_status(
                    user_id=user_id,
                    vector_type=vector_type,
                    status='done',
                    error_message=None,
                )
                _logger.info(
                    f"重试成功: user_id={user_id}, key={vector_type}, "
                    f"version={result.get('version')}"
                )
                return True
            else:
                # 失败：更新状态为 'failed'
                await update_vector_status(
                    user_id=user_id,
                    vector_type=vector_type,
                    status='failed',
                    error_message=result.get('error'),
                    retry_count=retry_count + 1,
                )
                _logger.error(
                    f"重试失败: user_id={user_id}, key={vector_type}, "
                    f"error={result.get('error')}"
                )
                return False

        finally:
            # ⚠️ 重要：主动关闭连接，避免 "Task exception was never retrieved" 错误
            await embedding_service.aclose()
            vector_store.close()

    except Exception as exc:
        _logger.error(f"重试异常: {exc}")
        # 更新状态为 'failed'
        await update_vector_status(
            user_id=user_id,
            vector_type=vector_type,
            status='failed',
            error_message=str(exc)[:200],
            retry_count=retry_count + 1,
        )
        return False


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 批量处理函数（合并LLM调用，节省成本）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


async def load_all_historical_summaries(
    user_id: int,
    vector_types: list[str],
) -> dict[str, str | None]:
    """
    一次性查询所有历史摘要

    Args:
        user_id: 用户ID
        vector_types: 向量类型列表（如 ["personality_traits", "values"]）

    Returns:
        {"personality_traits": "历史文本", "values": None, ...}
    """

    def _load_sync():
        from persona_memory_sync.persona_memory_lib import (
            mysql_connect,
            release_persona_connection,
            quote_mysql_ident,
        )

        dsn = os.environ.get("PERSONA_MEMORY_MYSQL_SOURCE", "")
        if not dsn:
            return {}

        conn = mysql_connect(dsn, use_pool=True, timeout=10.0)
        try:
            with conn.cursor() as cursor:
                # 一次性查询所有向量类型的历史摘要
                cursor.execute(
                    f"""
                    SELECT summary_key, summary_text
                    FROM {quote_mysql_ident("conversation_summaries")}
                    WHERE requester_id = %s AND summary_key IN %s
                    ORDER BY created_at DESC
                    """,
                    (user_id, tuple(vector_types)),
                )

                # 每个向量类型取最新的一条
                result = {}
                for row in cursor.fetchall():
                    key = row.get("summary_key")
                    if key and key not in result:  # 只取第一条（最新的）
                        result[key] = row.get("summary_text")

                # 补充缺失的向量类型（返回None）
                for vt in vector_types:
                    if vt not in result:
                        result[vt] = None

                return result

        finally:
            release_persona_connection(dsn, conn)

    # 异步执行
    return await asyncio.to_thread(_load_sync)


async def ai_batch_merge_and_vectorize(
    user_id: int,
    all_summary_data: dict[str, str],
    conversation_id: str,
    conversation_time: datetime | None = None,
) -> dict[str, Any]:
    """
    批量处理所有字段（合并LLM调用，节省成本）

    改造核心：
    - 一次性查询所有历史摘要
    - 一次性LLM判断所有字段的语义关系
    - 批量生成向量（使用generate_embeddings批量接口）
    - 批量存储向量

    Args:
        user_id: 用户ID
        all_summary_data: {"personality_traits": "温柔", "values": "家庭", ...}
        conversation_id: 对话ID
        conversation_time: 对话时间

    Returns:
        {
            "personality_traits": {"final_text": "...", "vector_saved": True},
            "values": {"final_text": "...", "vector_saved": True},
            ...
        }
    """

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Step 1：过滤有效的向量类型
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    valid_vector_types = [
        "personality_traits",
        "values",
        "partner_expectation",
        "life_attitude",
        "emotional_needs",
    ]

    # 过滤：只处理有效类型 + 文本不为空
    filtered_data = {
        key: text
        for key, text in all_summary_data.items()
        if key in valid_vector_types and str(text or "").strip()
    }

    if not filtered_data:
        _logger.info(f"没有需要处理的字段: user_id={user_id}")
        return {}

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Step 2：一次性查询所有历史摘要
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    historical_texts = await load_all_historical_summaries(
        user_id=user_id,
        vector_types=list(filtered_data.keys()),
    )

    _logger.info(
        f"批量查询历史摘要完成: user_id={user_id}\n"
        f"查询字段: {list(filtered_data.keys())}\n"
        f"历史数据: {historical_texts}"
    )

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Step 3：分离首次记录和需要判断的字段
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    # 首次记录（历史为None）
    first_time_keys = [
        key for key in filtered_data
        if not historical_texts.get(key)
    ]

    # 需要AI判断的字段（有历史）
    need_judge_keys = [
        key for key in filtered_data
        if historical_texts.get(key)
    ]

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Step 4：处理首次记录（直接保存，无需AI判断）
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    results = {}

    if first_time_keys:
        _logger.info(f"首次记录字段: {first_time_keys}")

        # 批量保存摘要文本
        for key in first_time_keys:
            await save_summary_text(
                user_id=user_id,
                vector_type=key,
                summary_text=filtered_data[key],
                conversation_id=conversation_id,
            )
            results[key] = {
                "final_text": filtered_data[key],
                "ai_decision": None,
                "text_saved": True,
            }

        # 批量生成向量
        from match_domain.embedding_service import EmbeddingService
        from match_domain.vector_store_lite import VectorStoreLite

        embedding_service = EmbeddingService(model_name="text-embedding-v3")
        vector_store = VectorStoreLite()

        try:
            # 批量生成向量（一次API调用）
            first_time_texts = [filtered_data[key] for key in first_time_keys]
            first_time_vectors = await embedding_service.generate_embeddings(first_time_texts)

            # 批量存储向量
            for key, text, vector in zip(first_time_keys, first_time_texts, first_time_vectors):
                result = vector_store.save_vector_with_version(
                    user_id=user_id,
                    vector_type=key,
                    embedding=vector,
                    raw_text=text,
                    conversation_id=conversation_id,
                )
                results[key]["vector_saved"] = result.get("success", False)

        finally:
            # ⚠️ 重要：主动关闭连接，避免 "Task exception was never retrieved" 错误
            await embedding_service.aclose()
            vector_store.close()

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Step 5：批量AI判断（一次性处理所有需要判断的字段）
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    if need_judge_keys:
        _logger.info(f"需要AI判断的字段: {need_judge_keys}")

        # 构建批量判断Prompt
        batch_prompt = _build_batch_semantic_judge_prompt(
            all_historical_texts={key: historical_texts[key] for key in need_judge_keys},
            all_new_texts={key: filtered_data[key] for key in need_judge_keys},
            conversation_time=conversation_time,
        )

        # 调用LLM（一次调用判断所有字段）
        try:
            batch_ai_decisions = await _call_llm_for_json(batch_prompt)

            # 验证返回格式
            if not isinstance(batch_ai_decisions, dict):
                raise ValueError("AI返回格式错误，应为字典")

            # 检查每个字段的返回格式
            for key in need_judge_keys:
                if key not in batch_ai_decisions:
                    raise ValueError(f"AI返回缺少字段: {key}")

                decision = batch_ai_decisions[key]
                required_fields = ["relation_type", "confidence", "action", "reason"]
                if not all(field in decision for field in required_fields):
                    raise ValueError(f"字段 {key} 缺少必要字段")

                if decision["action"] == "merge" and "merged_text" not in decision:
                    raise ValueError(f"字段 {key} 决定merge但未提供merged_text")

            _logger.info(
                f"批量AI判断完成: {need_judge_keys}\n"
                f"判断结果: {batch_ai_decisions}"
            )

        except Exception as exc:
            _logger.error(f"批量AI判断失败: {exc}")

            # Fallback：逐个字段使用fallback决策
            batch_ai_decisions = {}
            for key in need_judge_keys:
                batch_ai_decisions[key] = _fallback_decision(
                    historical_texts[key],
                    filtered_data[key],
                )

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # Step 6：根据AI判断，确定最终文本
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

        # 收集所有最终文本
        final_texts = {}
        for key in need_judge_keys:
            decision = batch_ai_decisions[key]

            if decision["action"] == "merge":
                final_texts[key] = decision["merged_text"]
            else:
                final_texts[key] = filtered_data[key]

            results[key] = {
                "final_text": final_texts[key],
                "ai_decision": decision,
                "text_saved": True,
            }

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # Step 7：批量保存摘要文本
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

        for key in need_judge_keys:
            await save_summary_text(
                user_id=user_id,
                vector_type=key,
                summary_text=final_texts[key],
                conversation_id=conversation_id,
                vector_status='pending',
            )

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # Step 8：批量生成向量并存储
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

        # 批量生成向量（一次API调用）
        from match_domain.embedding_service import EmbeddingService
        from match_domain.vector_store_lite import VectorStoreLite

        embedding_service = EmbeddingService(model_name="text-embedding-v3")
        vector_store = VectorStoreLite()

        try:
            need_judge_texts = [final_texts[key] for key in need_judge_keys]
            need_judge_vectors = await embedding_service.generate_embeddings(need_judge_texts)

            # 批量存储向量
            for key, text, vector in zip(need_judge_keys, need_judge_texts, need_judge_vectors):
                result = vector_store.save_vector_with_version(
                    user_id=user_id,
                    vector_type=key,
                    embedding=vector,
                    raw_text=text,
                    conversation_id=conversation_id,
                )
                results[key]["vector_saved"] = result.get("success", False)

                # 更新向量状态
                if result.get("success"):
                    await update_vector_status(
                        user_id=user_id,
                        vector_type=key,
                        status='done',
                        error_message=None,
                    )
                else:
                    await update_vector_status(
                        user_id=user_id,
                        vector_type=key,
                        status='failed',
                        error_message=result.get('error'),
                    )

        finally:
            # ⚠️ 重要：主动关闭连接，避免 "Task exception was never retrieved" 错误
            await embedding_service.aclose()
            vector_store.close()

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Step 9：返回批量处理结果
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    _logger.info(
        f"批量处理完成: user_id={user_id}\n"
        f"处理字段: {list(results.keys())}\n"
        f"成功向量化的字段: {[k for k, v in results.items() if v.get('vector_saved')]}"
    )

    return results


def _build_batch_semantic_judge_prompt(
    all_historical_texts: dict[str, str],
    all_new_texts: dict[str, str],
    conversation_time: datetime | None = None,
) -> str:
    """
    构建批量AI判断Prompt（一次性判断所有字段）

    Args:
        all_historical_texts: {"personality_traits": "历史文本", ...}
        all_new_texts: {"personality_traits": "新文本", ...}
        conversation_time: 对话时间

    Returns:
        Prompt字符串

    安全改进：
    - 转义 historical 和 new 文本中的花括号
    - 防止 f-string 解析错误（当字符串包含 JSON 格式时）
    """

    # 时间因素描述
    time_description = "未知时间"
    if conversation_time:
        days_gap = (datetime.now() - conversation_time).days
        if days_gap <= 1:
            time_description = "短期变化（同一天内）：倾向于补充"
        elif days_gap <= 7:
            time_description = "短期内变化（一周内）：可能是补充"
        elif days_gap <= 30:
            time_description = "中期变化（一个月内）：可能是补充或变化"
        else:
            time_description = "长期变化（超过一个月）：可能是真实变化"

    # 构建字段列表（转义花括号，防止 f-string 解析错误）
    fields_text = ""
    for key in all_historical_texts.keys():
        historical = all_historical_texts[key].replace("{", "{{").replace("}", "}}")
        new = all_new_texts[key].replace("{", "{{").replace("}", "}}")
        fields_text += f"""
【{key}】：
- 历史版本："{historical}"
- 新版本："{new}"

"""

    return f"""你是一个画像分析专家，擅长分析用户特征的语义关系。

请分析以下所有字段的新旧数据关系：

{fields_text}
【时间因素】：{time_description}

请为每个字段判断关系类型：

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

【三种关系类型】：

1. **补充关系**：
   - 新内容补充旧内容，两者语义兼容
   - 例："内向" → "喜欢安静"（内向的人通常喜欢安静）
   - 处理：合并 → "内向、喜欢安静"

2. **冲突关系**：
   - 新内容与旧内容矛盾，语义相反
   - 例："喜欢热闹" → "喜欢安静"（长期变化，真实变化）
   - 处理：覆盖 → 只保留"喜欢安静"

3. **细化关系**：
   - 新内容更具体，包含旧内容
   - 例："温柔" → "温柔、能理解工作"（后者包含前者）
   - 处理：合并 → "温柔、能理解工作"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

【判断规则】：
1. 优先考虑语义相似度和逻辑关系
2. 时间因素作为辅助判断（短期倾向于补充，长期可能是真实变化）
3. 如果不确定，优先选择"补充"（保留信息）
4. 如果明确冲突，选择"冲突"（覆盖旧版本）

【输出格式】：
请返回一个JSON对象，包含所有字段的判断结果。每个字段的格式如下：

- relation_type: "补充"、"冲突"或"细化"
- confidence: "high"、"medium"或"low"
- action: "merge"或"replace"
- merged_text: 如果action是"merge"，必须提供合并后的文本
- reason: 判断理由（一句话）

示例：
{{
    "personality_traits": {{
        "relation_type": "补充",
        "confidence": "high",
        "action": "merge",
        "merged_text": "温柔、内向",
        "reason": "两者语义兼容，可合并"
    }},
    "values": {{
        "relation_type": "冲突",
        "confidence": "medium",
        "action": "replace",
        "reason": "长期变化，真实变化"
    }}
}}

请严格按照JSON格式输出，不要输出任何其他内容。
"""


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 导出
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

__all__ = [
    "ai_merge_and_vectorize",
    "ai_batch_merge_and_vectorize",
    "load_all_historical_summaries",
    "load_historical_summary",
    "_ai_judge_semantic_relation",
    "_build_semantic_judge_prompt",
    "_build_batch_semantic_judge_prompt",
    "_fallback_decision",
    "save_summary_text",
    "load_historical_summary",
]