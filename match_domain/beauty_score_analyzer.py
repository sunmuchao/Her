"""AI beauty score analyzer using system GPT agent."""

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
        _logger.info(f"[beauty_score_analyzer] 开始下载照片: {photo_url}")

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

        _logger.info(f"[beauty_score_analyzer] 照片下载成功: {len(response.content)} bytes, 格式: {mime_type}")

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
                _logger.warning("缺少API配置，颜值评分功能将不可用")
                return None

            _openai_client = OpenAI(
                base_url=base_url,
                api_key=api_key,
                timeout=60.0,  # 颜值评分timeout较短
            )

            _logger.info(f"✅ 颜值评分AI客户端已创建: base_url={base_url}")

        except Exception as e:
            _logger.error(f"创建OpenAI客户端失败: {e}")
            return None

    return _openai_client


def analyze_beauty_score(photo_url: str) -> dict[str, Any]:
    """
    使用系统GPT agent分析颜值评分（0-100分）

    Args:
        photo_url: 照片URL（MinIO内部URL）

    Returns:
        dict: 包含beauty_score、reasoning等信息
    """
    try:
        client = _get_openai_client()
        if client is None:
            return {
                "beauty_score": 0,
                "reasoning": "",
                "error": "GPT agent未配置",
                "success": False,
            }

        # 【新增】下载照片并转换为base64
        try:
            image_data_url = _download_photo_as_base64(photo_url)
        except ValueError as e:
            _logger.error(f"[beauty_score_analyzer] 照片下载失败: {e}")
            return {
                "beauty_score": 0,
                "reasoning": "",
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

        # 构造prompt（颜值评分任务）
        prompt = """
你是一个专业的颜值评分助手。请分析这张照片中人物的颜值评分。

评分标准：
1. 颜值评分范围：0-100分
2. 基于以下维度综合评分：
   - 面部对称性（10-25分）
   - 皮肤质量（10-20分）
   - 五官协调度（15-30分）
   - 整体和谐度（15-25分）
3. 给出评分依据（简短说明，50字以内）

请直接返回JSON格式（不要包含其他解释）：
{"beauty_score": <0-100的数字>, "reasoning": "<评分依据>"}
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
            max_tokens=200,
            temperature=0.3,  # 颜值评分需要稳定性
        )

        # 解析JSON结果
        result_text = response.choices[0].message.content.strip()

        # 提取JSON部分
        json_start = result_text.find("{")
        json_end = result_text.rfind("}") + 1

        if json_start >= 0 and json_end > json_start:
            json_str = result_text[json_start:json_end]
            result = json.loads(json_str)

            beauty_score = float(result.get("beauty_score", 0))
            reasoning = str(result.get("reasoning", "")).strip()

            _logger.info(f"[beauty_score_analyzer] ✅ 颜值评分完成: score={beauty_score}, reasoning={reasoning[:50]}")

            return {
                "beauty_score": round(beauty_score, 2),
                "reasoning": reasoning,
                "model": model,
                "success": True,
            }
        else:
            _logger.error(f"[beauty_score_analyzer] 无法解析AI返回结果: {result_text}")
            return {
                "beauty_score": 0,
                "reasoning": "",
                "error": "无法解析AI返回结果",
                "success": False,
            }

    except Exception as e:
        _logger.error(f"[beauty_score_analyzer] 颜值评分失败: {e}")
        return {
            "beauty_score": 0,
            "reasoning": "",
            "error": str(e),
            "success": False,
        }


__all__ = ["analyze_beauty_score"]