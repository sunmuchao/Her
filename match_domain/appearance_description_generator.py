"""AI appearance description generator using system GPT agent."""

from __future__ import annotations

import base64
import json
import logging
import requests
from typing import Any

_logger = logging.getLogger(__name__)

# 全局OpenAI客户端（复用系统配置）
_openai_client = None


def _download_photo_as_base64(photo_url: str) -> str:
    """
    从MinIO下载照片并转换为base64格式

    Args:
        photo_url: MinIO内部URL（如http://minio:9000/her-media/...）

    Returns:
        str: base64数据URL（如data:image/jpeg;base64,...）

    Raises:
        ValueError: 照片下载失败
    """
    try:
        _logger.info(f"[appearance_description_generator] 开始下载照片: {photo_url}")

        # 从Docker内部URL下载（gateway-public容器可访问minio）
        response = requests.get(photo_url, timeout=15)
        if response.status_code != 200:
            raise ValueError(f"照片下载失败: HTTP {response.status_code}")

        # 检测照片格式（从Content-Type或URL扩展名）
        content_type = response.headers.get('Content-Type', 'image/jpeg')
        if 'png' in content_type.lower() or photo_url.lower().endswith('.png'):
            mime_type = 'image/png'
        else:
            mime_type = 'image/jpeg'

        # 转换为base64
        image_base64 = base64.b64encode(response.content).decode('utf-8')

        _logger.info(f"[appearance_description_generator] 照片下载成功: {len(response.content)} bytes, 格式: {mime_type}")

        # 返回data URL格式
        return f"data:{mime_type};base64,{image_base64}"

    except requests.Timeout:
        raise ValueError("照片下载超时")
    except requests.RequestException as e:
        raise ValueError(f"照片下载失败: {str(e)}")


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


def generate_appearance_description(photo_url: str, profile_id: int | None = None) -> dict[str, Any]:
    """
    使用系统GPT agent生成口语化的外貌描述，并写入向量库

    Args:
        photo_url: 照片URL（MinIO内部URL）
        profile_id: 用户ID（可选，用于写入向量库）

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

        # 【新增】下载照片并转换为base64
        try:
            image_data_url = _download_photo_as_base64(photo_url)
        except ValueError as e:
            _logger.error(f"[appearance_description_generator] 照片下载失败: {e}")
            return {
                "appearance_summary": "",
                "appearance_keywords": [],
                "appearance_style_type": "neutral",
                "dominant_features": [],
                "error": f"照片下载失败: {str(e)}",
                "success": False,
            }

        # 使用系统的默认模型（qwen-vl-plus，支持视觉）
        from her_env import env_first
        model = env_first(
            "HER_DISCOVERY_AGENT_MODEL",
            "HER_CHAT_AGENT_MODEL",
            default="qwen-vl-plus",  # 改为视觉模型
        )

        # 构造prompt（外貌描述任务）
        prompt = """
你是一个专业的外貌描述助手。请用自然、口语化的语言描述这张照片中人物的整体外貌气质。

描述要求：
1. 50-100字，自然友好，避免过于技术化
2. 突出整体气质（不要只说五官细节）
3. 符合中文口语表达习惯
4. 同时提取3-5个风格标签

示例：
- 描述："整体给人清纯阳光的感觉，带点甜妹气质，笑容很温暖，看起来很亲切"
- 标签：["清纯", "阳光", "甜妹", "温暖"]

请直接返回JSON格式（不要包含其他解释）：
{
  "appearance_summary": "<自然口语描述>",
  "appearance_keywords": ["关键词1", "关键词2", "关键词3"],
  "appearance_style_type": "<youthful/mature/neutral>",
  "dominant_features": ["特征1", "特征2"]
}

外貌风格类型说明：
- youthful: 幼态、年轻、可爱
- mature: 成熟、稳重、知性
- neutral: 中性、无明显风格倾向
"""

        # 【修改】调用GPT agent（使用base64图片数据）
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": image_data_url}},  # 使用base64数据
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
                f"[appearance_description_generator] ✅ 外貌描述完成: summary={appearance_summary[:50]}, keywords={appearance_keywords[:3]}"
            )

            # 【新增】如果提供了profile_id，写入向量库
            if profile_id:
                try:
                    from persona_memory_sync.persona_memory_lib import upsert_vector
                    from match_domain.appearance_search import AppearanceProfileEmbeddingExtractor

                    # 描述转向量（使用系统已有的哈希方法）
                    summary_vector = AppearanceProfileEmbeddingExtractor.extract(
                        appearance_summary=appearance_summary,
                        appearance_tags=appearance_keywords,
                        dims=1024,
                    )

                    # 写入Milvus向量库
                    upsert_vector(
                        profile_id=profile_id,
                        vector_type="appearance_profile",  # 外貌风格向量
                        vector_data=summary_vector,
                        metadata={
                            "appearance_summary": appearance_summary,
                            "appearance_tags": appearance_keywords,
                        }
                    )

                    _logger.info(f"[appearance_description_generator] ✅ 外貌向量入库成功: profile_id={profile_id}")

                except Exception as vector_error:
                    _logger.warning(f"[appearance_description_generator] 向量入库失败（不影响主流程）: {vector_error}")

            return {
                "appearance_summary": appearance_summary,
                "appearance_keywords": appearance_keywords,
                "appearance_style_type": appearance_style_type,
                "dominant_features": dominant_features,
                "model": model,
                "success": True,
            }
        else:
            _logger.error(f"[appearance_description_generator] 无法解析AI返回结果: {result_text}")
            return {
                "appearance_summary": "",
                "appearance_keywords": [],
                "appearance_style_type": "neutral",
                "dominant_features": [],
                "error": "无法解析AI返回结果",
                "success": False,
            }

    except Exception as e:
        _logger.error(f"[appearance_description_generator] 外貌描述生成失败: {e}")
        return {
            "appearance_summary": "",
            "appearance_keywords": [],
            "appearance_style_type": "neutral",
            "dominant_features": [],
            "error": str(e),
            "success": False,
        }


__all__ = ["generate_appearance_description"]