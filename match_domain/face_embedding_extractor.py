"""Face embedding extractor using DeepFace."""

from __future__ import annotations

from typing import Any
import json

# Lazy import DeepFace to avoid startup issues
_deepface = None
_numpy = None


def _lazy_import_deepface():
    """延迟导入DeepFace，避免启动时失败"""
    global _deepface, _numpy
    if _deepface is None:
        try:
            from deepface import DeepFace
            import numpy as np
            _deepface = DeepFace
            _numpy = np
        except ImportError:
            pass
    return _deepface, _numpy


DEEPFACE_AVAILABLE = _lazy_import_deepface()[0] is not None


def extract_face_embedding(photo_url: str) -> dict[str, Any] | None:
    """
    从照片中提取人脸向量（512维）

    Args:
        photo_url: 照片URL（可以是本地路径或远程URL）

    Returns:
        dict: 包含人脸向量、检测置信度等信息
        None: 如果没有检测到人脸
    """
    DeepFace, np = _lazy_import_deepface()

    if DeepFace is None:
        return {
            "face_embedding": None,
            "error": "DeepFace not installed. Install with: pip install deepface tf-keras",
            "success": False
        }

    try:
        # 使用DeepFace提取人脸向量
        result = DeepFace.represent(
            img_path=photo_url,
            model_name="Facenet512",
            enforce_detection=True,  # 强制要求检测到人脸
            align=True,              # 人脸对齐（提高准确度）
            detector_backend="opencv"  # 人脸检测器（opencv速度快）
        )

        if not result or len(result) == 0:
            return None

        # 提取第一个检测到的人脸（通常一张照片只有一个人）
        face_data = result[0]

        # 人脸向量（512维）
        embedding = face_data["embedding"]
        embedding_list = [float(x) for x in embedding]  # 转换为Python列表

        # 人脸检测置信度
        confidence = float(face_data.get("confidence", 0.0))

        # 人脸位置边界框
        facial_area = face_data.get("facial_area", {})
        face_bbox = {
            "x": int(facial_area.get("x", 0)),
            "y": int(facial_area.get("y", 0)),
            "w": int(facial_area.get("w", 0)),
            "h": int(facial_area.get("h", 0))
        }

        return {
            "face_embedding": embedding_list,  # 512维向量
            "face_embedding_model": "Facenet512",
            "face_embedding_dimension": 512,
            "face_detection_confidence": confidence,
            "face_bbox": face_bbox,
            "success": True
        }

    except ValueError as e:
        # 检测失败（没有找到人脸）
        return {
            "face_embedding": None,
            "error": f"Face detection failed: {str(e)}",
            "success": False
        }
    except Exception as e:
        # 其他错误
        return {
            "face_embedding": None,
            "error": str(e),
            "success": False
        }


def compute_face_similarity(embedding1: list[float], embedding2: list[float]) -> float:
    """
    计算两个人脸向量的相似度（余弦相似度）

    Args:
        embedding1: 第一个人脸向量（512维）
        embedding2: 第二个人脸向量（512维）

    Returns:
        float: 相似度评分（0-1，越接近1越相似）
    """
    DeepFace, np = _lazy_import_deepface()

    if np is None:
        return 0.0

    # 转换为numpy数组
    vec1 = np.array(embedding1)
    vec2 = np.array(embedding2)

    # 计算余弦相似度
    dot_product = np.dot(vec1, vec2)
    norm1 = np.linalg.norm(vec1)
    norm2 = np.linalg.norm(vec2)

    if norm1 == 0 or norm2 == 0:
        return 0.0

    similarity = dot_product / (norm1 * norm2)

    # 限制在[0, 1]范围内
    similarity = max(0.0, min(1.0, similarity))

    return similarity


__all__ = [
    "extract_face_embedding",
    "compute_face_similarity",
    "DEEPFACE_AVAILABLE",
]