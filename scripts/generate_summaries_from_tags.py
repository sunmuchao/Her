#!/usr/bin/env python3
"""基于性格标签生成摘要和向量数据

用途：
  为无锡女性候选人生成性格摘要和向量数据
  不需要聊天记录，直接基于profiles表中的性格标签生成

执行方式：
  python scripts/generate_summaries_from_tags.py [--batch-size 5]

参数说明：
  --batch-size: 每批处理的用户数量（默认5）

注意事项：
  1. 需要配置 HER_PERSONA_DB 或 PERSONA_MEMORY_MYSQL_SOURCE（数据库连接）
  2. 需要配置 OPENAI_API_KEY 或 DASHSCOPE_API_KEY（Embedding API Key）
  3. 需要配置 HER_DISCOVERY_AGENT_API_KEY（LLM API Key，用于生成摘要）
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

# 确保 her repo 在 sys.path 中
repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

# 加载环境变量
try:
    from dotenv import load_dotenv
    load_dotenv(repo_root / ".env")
except ImportError:
    pass

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
_logger = logging.getLogger(__name__)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Step 1: 从数据库读取性格标签
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


async def load_personality_tags(profile_ids: list[int]) -> dict[int, dict[str, Any]]:
    """从数据库读取性格标签"""

    from persona_memory_sync.persona_memory_lib import mysql_connect, release_persona_connection
    from outer_system_mysql_schema import quote_mysql_ident

    source = os.environ.get("PERSONA_MEMORY_MYSQL_SOURCE") or os.environ.get("HER_PERSONA_DB") or ""
    if not source:
        _logger.error("请设置环境变量 PERSONA_MEMORY_MYSQL_SOURCE 或 HER_PERSONA_DB")
        return {}

    conn = mysql_connect(source, use_pool=True, timeout=10.0)

    personality_tags_map: dict[int, dict[str, Any]] = {}

    try:
        with conn.cursor() as cursor:
            placeholders = ", ".join(["%s"] * len(profile_ids))
            sql = f"""
                SELECT id, name, age, city, job, education, relationship_goal,
                       public_personality, public_values, life_routine,
                       communication_style, {quote_mysql_ident('values')}, notes
                FROM {quote_mysql_ident("profiles")}
                WHERE id IN ({placeholders})
            """
            cursor.execute(sql, tuple(profile_ids))
            profiles = cursor.fetchall() or []

            for profile in profiles:
                profile_id = profile.get("id")
                if profile_id:
                    personality_tags_map[profile_id] = {
                        "name": profile.get("name", ""),
                        "age": profile.get("age", 28),
                        "city": profile.get("city", ""),
                        "job": profile.get("job", ""),
                        "education": profile.get("education", ""),
                        "relationship_goal": profile.get("relationship_goal", ""),
                        "public_personality": profile.get("public_personality", ""),
                        "public_values": profile.get("public_values", ""),
                        "life_routine": profile.get("life_routine", ""),
                        "communication_style": profile.get("communication_style", ""),
                        "values": profile.get("values", ""),
                        "notes": profile.get("notes", ""),
                    }

            _logger.info(f"【加载完成】读取了 {len(personality_tags_map)} 个用户的性格标签")

    finally:
        release_persona_connection(source, conn)

    return personality_tags_map


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Step 2: 用LLM生成性格摘要
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


async def generate_summary_with_llm(
    profile_id: int,
    personality_tags: dict[str, Any],
    vector_type: str,
) -> str:
    """用LLM生成性格摘要"""

    from openai import AsyncOpenAI

    # 读取API配置
    api_key = os.environ.get("HER_DISCOVERY_AGENT_API_KEY") or os.environ.get("DASHSCOPE_API_KEY") or ""
    base_url = os.environ.get("HER_DISCOVERY_AGENT_BASE_URL") or "https://dashscope.aliyuncs.com/compatible-mode/v1"
    model = os.environ.get("HER_DISCOVERY_AGENT_MODEL") or "qwen-plus"

    if not api_key:
        _logger.warning(f"【跳过LLM生成】profile_id={profile_id} vector_type={vector_type} - 缺少API Key")
        # Fallback：直接拼接标签
        return generate_fallback_summary(profile_id, personality_tags, vector_type)

    client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    # 构建prompt
    prompt = build_summary_generation_prompt(profile_id, personality_tags, vector_type)

    try:
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "你是一位专业的性格分析师，擅长从性格标签生成简洁、准确的性格摘要。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=200,
        )

        summary_text = response.choices[0].message.content.strip() if response.choices else ""
        _logger.info(f"【LLM生成成功】profile_id={profile_id} vector_type={vector_type}")

        return summary_text

    except Exception as exc:
        _logger.warning(f"【LLM生成失败】profile_id={profile_id} vector_type={vector_type} error={exc}")
        # Fallback：直接拼接标签
        return generate_fallback_summary(profile_id, personality_tags, vector_type)

    finally:
        await client.close()


def build_summary_generation_prompt(
    profile_id: int,
    personality_tags: dict[str, Any],
    vector_type: str,
) -> str:
    """构建摘要生成prompt"""

    name = personality_tags.get("name", "")
    age = personality_tags.get("age", 28)
    job = personality_tags.get("job", "")
    education = personality_tags.get("education", "")
    public_personality = personality_tags.get("public_personality", "")
    public_values = personality_tags.get("public_values", "")
    life_routine = personality_tags.get("life_routine", "")
    communication_style = personality_tags.get("communication_style", "")
    values = personality_tags.get("values", "")
    notes = personality_tags.get("notes", "")

    # 根据vector_type定制prompt
    vector_type_prompts = {
        "personality_traits": f"""
用户{name}（{age}岁，{job}）的性格特质：
- 公开性格标签：{public_personality}
- 沟通风格：{communication_style}
- 个人备注：{notes}

请生成一句简洁的性格摘要（不超过50字），描述这个人的核心性格特点。
示例格式："性格温和、情绪稳定，善于沟通，注重相处舒服"
""",
        "values": f"""
用户{name}（{age}岁，{job}）的价值观：
- 公开价值观：{public_values}
- 核心价值观：{values}
- 生活态度：{life_routine}

请生成一句简洁的价值观摘要（不超过50字），描述这个人最看重的价值。
示例格式："重视三观正、消费观正常，务实，看重相处舒服"
""",
        "life_attitude": f"""
用户{name}（{age}岁，{job}）的生活态度：
- 生活规律：{life_routine}
- 沟通风格：{communication_style}
- 个人备注：{notes}

请生成一句简洁的生活态度摘要（不超过50字），描述这个人的生活方式和态度。
示例格式："作息规律，周末会出门走走，看重沟通顺畅"
""",
        "partner_expectation": f"""
用户{name}（{age}岁，{job}）的择偶期望：
- 关系目标：{personality_tags.get('relationship_goal', '')}
- 年龄：{age}
- 职业：{job}
- 学历：{education}

请生成一句简洁的择偶期望摘要（不超过50字），描述这个人希望找什么样的伴侣。
示例格式："希望找个三观一致、相处舒服的人，认真恋爱导向"
""",
        "partner_personality_preference": f"""
用户{name}（{age}岁，{job}）对伴侣的性格偏好：
- 公开性格：{public_personality}
- 沟通风格：{communication_style}

请生成一句简洁的性格偏好摘要（不超过50字），描述这个人希望伴侣有什么性格特点。
示例格式："希望对方性格温和、情绪稳定，善于沟通"
""",
        "partner_relationship_pacing": f"""
用户{name}（{age}岁，{job}）对关系推进节奏的偏好：
- 关系目标：{personality_tags.get('relationship_goal', '')}
- 生活规律：{life_routine}

请生成一句简洁的关系节奏摘要（不超过50字），描述这个人希望关系如何推进。
示例格式："倾向于认真恋爱，节奏明确，不暧昧"
""",
        "partner_lifestyle_preference": f"""
用户{name}（{age}岁，{job}）对伴侣生活方式的偏好：
- 生活规律：{life_routine}
- 沟通风格：{communication_style}

请生成一句简洁的生活方式偏好摘要（不超过50字），描述这个人希望伴侣有什么生活方式。
示例格式："希望对方作息规律，周末会出门走走，看重生活质量"
""",
        "emotional_needs": f"""
用户{name}（{age}岁，{job}）的情感需求：
- 公开性格：{public_personality}
- 沟通风格：{communication_style}
- 个人备注：{notes}

请生成一句简洁的情感需求摘要（不超过50字），描述这个人在关系中需要什么。
示例格式："需要理解和支持，看重沟通顺畅和相处舒服"
""",
    }

    return vector_type_prompts.get(vector_type, f"请为{vector_type}生成摘要")


def generate_fallback_summary(
    profile_id: int,
    personality_tags: dict[str, Any],
    vector_type: str,
) -> str:
    """Fallback：直接拼接标签生成摘要"""

    public_personality = personality_tags.get("public_personality", "")
    public_values = personality_tags.get("public_values", "")
    life_routine = personality_tags.get("life_routine", "")
    communication_style = personality_tags.get("communication_style", "")

    # 根据vector_type拼接标签
    fallback_summaries = {
        "personality_traits": f"{public_personality}，{communication_style}" if public_personality else communication_style,
        "values": public_values or "三观正、务实",
        "life_attitude": life_routine or "作息规律",
        "partner_expectation": "希望找个三观一致的人",
        "partner_personality_preference": public_personality or "性格温和",
        "partner_relationship_pacing": "认真恋爱",
        "partner_lifestyle_preference": life_routine or "作息规律",
        "emotional_needs": "需要理解和支持",
    }

    return fallback_summaries.get(vector_type, "")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Step 3: 写入数据库（conversation_summaries表）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


async def save_summary_to_db(
    profile_id: int,
    vector_type: str,
    summary_text: str,
) -> bool:
    """写入摘要到数据库"""

    from match_domain.ai_merge_handler import save_summary_text

    try:
        # 使用 conversation_id="synthetic_{profile_id}" 标记这是合成数据
        await save_summary_text(
            user_id=profile_id,
            vector_type=vector_type,
            summary_text=summary_text,
            conversation_id=f"synthetic_{profile_id}",
            vector_status='done',  # 标记为已完成（因为马上要写向量）
        )

        _logger.info(f"【写入数据库成功】profile_id={profile_id} vector_type={vector_type}")
        return True

    except Exception as exc:
        _logger.error(f"【写入数据库失败】profile_id={profile_id} vector_type={vector_type} error={exc}")
        return False


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Step 4: 转向量 + 写入向量库
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


async def save_vector_to_store(
    profile_id: int,
    vector_type: str,
    summary_text: str,
) -> bool:
    """转向量并写入向量库"""

    from match_domain.embedding_service import EmbeddingService
    from match_domain.vector_store_lite import VectorStoreLite

    try:
        # 初始化服务
        embedding_service = EmbeddingService()
        vector_store = VectorStoreLite()

        # 转向量（使用正确的方法名）
        embedding = await embedding_service.generate_embedding(summary_text)

        # 写入向量库
        result = vector_store.save_vector_with_version(
            user_id=profile_id,
            vector_type=vector_type,
            embedding=embedding,
            raw_text=summary_text,
            conversation_id=f"synthetic_{profile_id}",
        )

        # 关闭连接
        await embedding_service.aclose()
        vector_store.close()

        if result.get("success"):
            _logger.info(f"【写入向量库成功】profile_id={profile_id} vector_type={vector_type}")
            return True
        else:
            _logger.error(f"【写入向量库失败】profile_id={profile_id} vector_type={vector_type} error={result.get('error')}")
            return False

    except Exception as exc:
        _logger.error(f"【向量处理失败】profile_id={profile_id} vector_type={vector_type} error={exc}")
        return False


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 主流程：批量处理
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


async def process_batch(
    profile_ids: list[int],
    vector_types: list[str],
) -> dict[str, Any]:
    """批量处理一批用户"""

    _logger.info(f"【开始批次】处理 {len(profile_ids)} 个用户")

    # Step 1: 加载性格标签
    personality_tags_map = await load_personality_tags(profile_ids)

    if not personality_tags_map:
        _logger.warning("【批次失败】没有加载到性格标签")
        return {"success_count": 0, "error_count": 0}

    # Step 2-4: 为每个用户生成摘要、写入数据库、写入向量库
    success_count = 0
    error_count = 0

    for profile_id, personality_tags in personality_tags_map.items():
        _logger.info(f"【处理用户】profile_id={profile_id} name={personality_tags.get('name')}")

        for vector_type in vector_types:
            try:
                # Step 2: 生成摘要
                summary_text = await generate_summary_with_llm(profile_id, personality_tags, vector_type)

                if not summary_text:
                    _logger.warning(f"【跳过】profile_id={profile_id} vector_type={vector_type} - 没有生成摘要")
                    error_count += 1
                    continue

                # Step 3: 写入数据库
                db_success = await save_summary_to_db(profile_id, vector_type, summary_text)

                # Step 4: 写入向量库
                vector_success = await save_vector_to_store(profile_id, vector_type, summary_text)

                if db_success and vector_success:
                    success_count += 1
                else:
                    error_count += 1

            except Exception as exc:
                _logger.error(f"【处理失败】profile_id={profile_id} vector_type={vector_type} error={exc}")
                error_count += 1

    _logger.info(f"【批次完成】成功 {success_count}，失败 {error_count}")

    return {"success_count": success_count, "error_count": error_count}


async def main():
    """主流程"""

    # 解析参数
    parser = argparse.ArgumentParser(description="基于性格标签生成摘要和向量数据")
    parser.add_argument("--batch-size", type=int, default=5, help="每批处理的用户数量")
    args = parser.parse_args()

    _logger.info("=" * 80)
    _logger.info("【开始】基于性格标签生成摘要和向量数据")
    _logger.info("=" * 80)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 获取无锡女性候选人列表
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    from persona_memory_sync.persona_memory_lib import mysql_connect, release_persona_connection
    from outer_system_mysql_schema import quote_mysql_ident

    source = os.environ.get("PERSONA_MEMORY_MYSQL_SOURCE") or os.environ.get("HER_PERSONA_DB") or ""
    if not source:
        _logger.error("请设置环境变量 PERSONA_MEMORY_MYSQL_SOURCE 或 HER_PERSONA_DB")
        return

    conn = mysql_connect(source, use_pool=True, timeout=10.0)

    profile_ids = []

    try:
        with conn.cursor() as cursor:
            # 从日志中获取正确的候选人profile_id（去掉relationship_goal过滤）
            cursor.execute(
                f"""
                SELECT id
                FROM {quote_mysql_ident("profiles")}
                WHERE id IN (6092, 2379, 6566, 1045, 8867)
                ORDER BY id ASC
                """
            )
            rows = cursor.fetchall() or []
            profile_ids = [row.get("id") for row in rows if row.get("id")]

    finally:
        release_persona_connection(source, conn)

    if not profile_ids:
        _logger.warning("【结束】没有找到候选人")
        return

    _logger.info(f"【候选人列表】找到 {len(profile_ids)} 个用户: {profile_ids}")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 批量处理
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    vector_types = [
        "personality_traits",
        "values",
        "life_attitude",
        "partner_expectation",
        "partner_personality_preference",
        "partner_relationship_pacing",
        "partner_lifestyle_preference",
        "emotional_needs",
    ]

    batch_size = args.batch_size
    total_success = 0
    total_error = 0

    # 分批处理
    for i in range(0, len(profile_ids), batch_size):
        batch_ids = profile_ids[i : i + batch_size]
        result = await process_batch(batch_ids, vector_types)
        total_success += result.get("success_count", 0)
        total_error += result.get("error_count", 0)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 总结
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    _logger.info("=" * 80)
    _logger.info("【完成】")
    _logger.info(f"  - 处理用户数: {len(profile_ids)}")
    _logger.info(f"  - 成功生成摘要: {total_success}")
    _logger.info(f"  - 失败: {total_error}")
    _logger.info("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())