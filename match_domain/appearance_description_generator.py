"""AI appearance description generator using system GPT agent."""

from __future__ import annotations

import json
import logging
from typing import Any

_logger = logging.getLogger(__name__)

# 全局OpenAI客户端（复用系统配置）
_openai_client = None


def _get_openai_client():
    """
    获取OpenAI客户端（复用系统的百炼API配置）
    """
    global _openai_client
    if _openai_client is None:
        try:
            from openai import OpenAI  # 使用同步客户端（简化调用）
            from her_env import env_first

            # 从环境变量读取配置（与系统agent_runtime一致）
            base_url = env_first(
                "OPENAI_BASE_URL",
                "BAILIAN_BASE_URL",
                "HER_DISCOVERY_AGENT_BASE_URL",
                default="https://dashscope.aliyuncs.com/compatible-mode/v1",
            )

            api_key = env_first(
                "OPENAI_API_KEY",
                "BAILIAN_API_KEY",
                "HER_DISCOVERY_AGENT_API_KEY",
                default="",
            )

            if not api_key or not base_url:
                _logger.warning("缺少API配置，外貌描述功能将不可用")
                return None

            _openai_client = OpenAI(
                base_url=base_url,
                api_key=api_key,
                timeout=60.0,  # 外貌描述timeout较短
            )

            _logger.info(f"✅ 外貌描述AI客户端已创建: base_url={base_url}")

        except Exception as e:
            _logger.error(f"创建OpenAI客户端失败: {e}")
            return None

    return _openai_client


def generate_appearance_description(photo_url: str) -> dict[str, Any]:
    """
    使用系统GPT agent生成口语化的外貌描述

    Args:
        photo_url: 照片URL

    Returns:
        dict: 包含appearance_summary、appearance_keywords等信息
    """
    try:
        client = _get_openai_client()
        if client is None:
            return {
                "appearance_summary": "",
                "appearance_keywords": [],
                "appearance_style_type": "neutral",
                "dominant_features": [],
                "error": "GPT agent未配置",
                "success": False,
            }

        # 使用系统的默认模型（qwen3.6-plus）
        from her_env import env_first
        model = env_first(
            "HER_DISCOVERY_AGENT_MODEL",
            "HER_CHAT_AGENT_MODEL",
            default="qwen3.6-plus",
        )

        # 构造prompt（外貌描述任务）
        prompt = f"""
你是一个专业的外貌描述助手。请用自然、口语化的语言描述这张照片中人物的外貌。

照片URL: {photo_url}

描述要求：
1. 描述要自然、友好，避免过于技术化
2. 度控制在50-100字
3. 突出1-3个最显著的特征
4. 符合中文口语表达习惯
5. 提取3-5个关键词标签

请直接返回JSON格式（不要包含其他解释）：
{{"appearance_summary": "<自然口语描述>", "appearance_keywords": ["关键词1", "关键词2", "关键词3"], "appearance_style_type": "<youthful/mature/neutral>", "dominant_features": ["特征1", "特征2"]}}

外貌风格类型说明：
- youthful: 幼态、年轻、可爱
- mature: 成熟、稳重、知性
- neutral: 中性、无明显风格倾向
"""

        # 调用GPT agent（同步调用）
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": photo_url}},
                    ],
                }
            ],
            max_tokens=300,
            temperature=0.7,  # 外貌描述需要一定创造性
        )

        # 解析JSON结果
        result_text = response.choices[0].message.content.strip()

        # 提取JSON部分
        json_start = result_text.find("{")
        json_end = result_text.rfind("}") + 1

        if json_start >= 0 and json_end > json_start:
            json_str = result_text[json_start:json_end]
            result = json.loads(json_str)

            appearance_summary = str(result.get("appearance_summary", "")).strip()
            appearance_keywords = list(result.get("appearance_keywords", []))
            appearance_style_type = str(result.get("appearance_style_type", "neutral")).strip()
            dominant_features = list(result.get("dominant_features", []))

            _logger.info(
                f"✅ 外貌描述完成: summary={appearance_summary[:50]}, keywords={appearance_keywords[:3]}"
            )

            return {
                "appearance_summary": appearance_summary,
                "appearance_keywords": appearance_keywords,
                "appearance_style_type": appearance_style_type,
                "dominant_features": dominant_features,
                "model": model,
                "success": True,
            }
        else:
            _logger.error(f"无法解析AI返回结果: {result_text}")
            return {
                "appearance_summary": "",
                "appearance_keywords": [],
                "appearance_style_type": "neutral",
                "dominant_features": [],
                "error": "无法解析AI返回结果",
                "success": False,
            }

    except Exception as e:
        _logger.error(f"外貌描述生成失败: {e}")
        return {
            "appearance_summary": "",
            "appearance_keywords": [],
            "appearance_style_type": "neutral",
            "dominant_features": [],
            "error": str(e),
            "success": False,
        }


__all__ = ["generate_appearance_description"]