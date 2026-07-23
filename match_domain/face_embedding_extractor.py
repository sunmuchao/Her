"""Face embedding extractor using DeepFace."""

from __future__ import annotations

from typing import Any
import json
import hashlib
import logging
import os

_logger = logging.getLogger(__name__)

FACE_EMBEDDING_MODEL_NAME = "Facenet512"
DEEPFACE_WEIGHTS_DIR = os.path.expanduser("~/.deepface/weights")
DEEPFACE_FACENET512_WEIGHTS = os.path.join(DEEPFACE_WEIGHTS_DIR, "facenet512_weights.h5")

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


def warmup_face_embedding_model(*, force: bool = False) -> dict[str, Any]:
    """预加载 DeepFace Facenet512 模型，避免首个请求触发同步下载/初始化。"""
    DeepFace, _np = _lazy_import_deepface()
    if DeepFace is None:
        return {
            "success": False,
            "model_name": FACE_EMBEDDING_MODEL_NAME,
            "error": "DeepFace not installed",
        }

    os.makedirs(DEEPFACE_WEIGHTS_DIR, exist_ok=True)
    weights_exist = os.path.exists(DEEPFACE_FACENET512_WEIGHTS)
    _logger.info(
        "【人脸模型预热】stage=model_load_start model=%s weights_path=%s weights_exist=%s force=%s",
        FACE_EMBEDDING_MODEL_NAME,
        DEEPFACE_FACENET512_WEIGHTS,
        weights_exist,
        force,
    )
    try:
        model = DeepFace.build_model(FACE_EMBEDDING_MODEL_NAME)
        _logger.info(
            "【人脸模型预热】stage=model_load_done model=%s weights_path=%s weights_exist=%s model_type=%s",
            FACE_EMBEDDING_MODEL_NAME,
            DEEPFACE_FACENET512_WEIGHTS,
            os.path.exists(DEEPFACE_FACENET512_WEIGHTS),
            type(model).__name__,
        )
        return {
            "success": True,
            "model_name": FACE_EMBEDDING_MODEL_NAME,
            "weights_path": DEEPFACE_FACENET512_WEIGHTS,
            "weights_exist": os.path.exists(DEEPFACE_FACENET512_WEIGHTS),
        }
    except Exception as exc:
        _logger.exception(
            "【人脸模型预热失败】stage=model_load_failed model=%s weights_path=%s",
            FACE_EMBEDDING_MODEL_NAME,
            DEEPFACE_FACENET512_WEIGHTS,
        )
        return {
            "success": False,
            "model_name": FACE_EMBEDDING_MODEL_NAME,
            "weights_path": DEEPFACE_FACENET512_WEIGHTS,
            "weights_exist": os.path.exists(DEEPFACE_FACENET512_WEIGHTS),
            "error": str(exc),
        }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 照片向量缓存类（新增）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class FaceEmbeddingCache:
    """缓存照片向量，避免重复提取

    作用：
    - 第一次搜田曦薇：提取向量 → 缓存
    - 第二次搜田曦薇：直接用缓存 → 快！

    缓存格式：
    - key: photo_url的MD5哈希
    - value: 人脸向量（512维列表）

    缓存策略：
    - 内存缓存（简单高效）
    - 无过期时间（向量是固定的）
    """

    def __init__(self):
        self.cache: dict[str, dict[str, Any]] = {}
        self.hit_count = 0
        self.miss_count = 0

    def _get_cache_key(self, photo_url: str) -> str:
        """生成缓存key（photo_url的MD5哈希）"""
        return hashlib.md5(photo_url.encode('utf-8')).hexdigest()

    def get_cached_embedding(self, photo_url: str) -> dict[str, Any] | None:
        """查询缓存

        Args:
            photo_url: 照片URL

        Returns:
            缓存的向量数据（如果命中），None（如果未命中）
        """
        cache_key = self._get_cache_key(photo_url)
        cached_data = self.cache.get(cache_key)

        if cached_data:
            self.hit_count += 1
            _logger.info(
                f"【照片向量缓存命中】photo_url={photo_url[:100]} "
                f"hit_rate={self.get_cache_stats()['hit_rate']:.1%}"
            )
        else:
            self.miss_count += 1

        return cached_data

    def cache_embedding(self, photo_url: str, embedding_data: dict[str, Any]):
        """缓存向量

        Args:
            photo_url: 照片URL
            embedding_data: 向量数据（包含face_embedding等）
        """
        cache_key = self._get_cache_key(photo_url)
        self.cache[cache_key] = embedding_data

        _logger.info(
            f"【照片向量缓存保存】photo_url={photo_url[:100]} "
            f"cache_size={len(self.cache)}"
        )

    def get_cache_stats(self) -> dict[str, Any]:
        """获取缓存统计信息

        Returns:
            {
                "cache_size": 缓存条目数量,
                "hit_count": 命中次数,
                "miss_count": 未命中次数,
                "hit_rate": 命中率
            }
        """
        total_requests = self.hit_count + self.miss_count
        hit_rate = self.hit_count / total_requests if total_requests > 0 else 0.0

        return {
            "cache_size": len(self.cache),
            "hit_count": self.hit_count,
            "miss_count": self.miss_count,
            "hit_rate": hit_rate,
        }

    def clear_cache(self):
        """清空缓存"""
        self.cache.clear()
        self.hit_count = 0
        self.miss_count = 0
        _logger.info("【照片向量缓存已清空】")


# 全局缓存实例（单例模式）
_face_embedding_cache = FaceEmbeddingCache()


def extract_face_embedding(photo_url: str) -> dict[str, Any] | None:
    """
    从照片中提取人脸向量（512维）（带缓存优化）

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

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Step 0: 查询缓存（新增）
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    cached_result = _face_embedding_cache.get_cached_embedding(photo_url)
    if cached_result:
        # 缓存命中，直接返回
        return cached_result

    _logger.info(
        "【参考图人脸向量】stage=request_received photo_url=%s",
        photo_url[:200],
    )

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Step 1: 照片质量检查（新增）
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    try:
        import urllib.request
        from PIL import Image
        import io

        # 检查照片是否能正常加载
        if photo_url.startswith("http://") or photo_url.startswith("https://"):
            # 远程照片：下载并检查
            try:
                _logger.info(
                    "【参考图人脸向量】stage=reference_fetch_start photo_url=%s",
                    photo_url[:200],
                )
                with urllib.request.urlopen(photo_url, timeout=10) as response:
                    image_data = response.read()
                _logger.info(
                    "【参考图人脸向量】stage=reference_fetch_done photo_url=%s bytes=%s",
                    photo_url[:200],
                    len(image_data),
                )

                # 检查照片大小（太小可能质量差）
                if len(image_data) < 1024:  # 小于1KB
                    error_result = {
                        "face_embedding": None,
                        "error": "照片文件太小，可能质量不佳。请换张照片试试",
                        "success": False
                    }
                    # 不缓存错误结果
                    return error_result

                # 尝试用PIL打开照片
                try:
                    image = Image.open(io.BytesIO(image_data))
                    width, height = image.size

                    # 检查照片分辨率（太小可能质量差）
                    if width < 100 or height < 100:
                        error_result = {
                            "face_embedding": None,
                            "error": "照片分辨率太低，可能看不清楚。请换张高清照片试试",
                            "success": False
                        }
                        return error_result

                except Exception:
                    error_result = {
                        "face_embedding": None,
                        "error": "照片格式不支持或已损坏。请换张照片试试",
                        "success": False
                    }
                    return error_result

            except urllib.error.URLError:
                error_result = {
                    "face_embedding": None,
                    "error": "照片链接无法访问。请确认照片链接正确",
                    "success": False
                }
                return error_result
            except Exception as e:
                error_result = {
                    "face_embedding": None,
                    "error": f"照片加载失败：{str(e)[:100]}。请换张照片试试",
                    "success": False
                }
                return error_result

    except ImportError:
        # PIL或urllib不可用，跳过质量检查
        pass

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Step 2: 提取人脸向量
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    try:
        warmup_face_embedding_model()

        _logger.info(
            "【参考图人脸向量】stage=embedding_compute_start model=%s photo_url=%s",
            FACE_EMBEDDING_MODEL_NAME,
            photo_url[:200],
        )
        # 使用DeepFace提取人脸向量
        result = DeepFace.represent(
            img_path=photo_url,
            model_name=FACE_EMBEDDING_MODEL_NAME,
            enforce_detection=True,  # 强制要求检测到人脸
            align=True,              # 人脸对齐（提高准确度）
            detector_backend="opencv"  # 人脸检测器（opencv速度快）
        )

        if not result or len(result) == 0:
            error_result = {
                "face_embedding": None,
                "error": "照片中未检测到人脸。请上传包含清晰人脸的照片",
                "success": False
            }
            return error_result

        # 提取第一个检测到的人脸（通常一张照片只有一个人）
        face_data = result[0]

        # 人脸向量（512维）
        embedding = face_data["embedding"]
        embedding_list = [float(x) for x in embedding]  # 转换为Python列表

        # 人脸检测置信度
        confidence = float(face_data.get("confidence", 0.0))

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # Step 3: 检查人脸检测置信度（新增）
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        if confidence < 0.5:
            error_result = {
                "face_embedding": None,
                "error": "人脸检测置信度过低，可能人脸不清晰或被遮挡。请换张更清晰的照片试试",
                "success": False
            }
            return error_result

        # 人脸位置边界框
        facial_area = face_data.get("facial_area", {})
        face_bbox = {
            "x": int(facial_area.get("x", 0)),
            "y": int(facial_area.get("y", 0)),
            "w": int(facial_area.get("w", 0)),
            "h": int(facial_area.get("h", 0))
        }

        success_result = {
            "face_embedding": embedding_list,  # 512维向量
            "face_embedding_model": FACE_EMBEDDING_MODEL_NAME,
            "face_embedding_dimension": 512,
            "face_detection_confidence": confidence,
            "face_bbox": face_bbox,
            "success": True
        }

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # Step 4: 缓存成功结果（新增）
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        _face_embedding_cache.cache_embedding(photo_url, success_result)
        _logger.info(
            "【参考图人脸向量】stage=embedding_compute_done model=%s photo_url=%s dimension=%s confidence=%.4f",
            FACE_EMBEDDING_MODEL_NAME,
            photo_url[:200],
            len(embedding_list),
            confidence,
        )

        return success_result

    except ValueError as e:
        # 检测失败（没有找到人脸）
        error_message = str(e)

        # 友好的错误信息
        if "Face could not be detected" in error_message or "No face detected" in error_message:
            error_result = {
                "face_embedding": None,
                "error": "照片中未检测到人脸。请上传包含清晰人脸的照片",
                "success": False
            }
        else:
            error_result = {
                "face_embedding": None,
                "error": "人脸检测失败，可能照片质量不佳。请换张清晰的照片试试",
                "success": False
            }
        return error_result
    except Exception as e:
        # 其他错误
        error_result = {
            "face_embedding": None,
            "error": f"照片处理失败：{str(e)[:100]}。请换张照片试试",
            "success": False
        }
        return error_result


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


def extract_and_store_face_embedding(photo_url: str, profile_id: int, source_dsn: str | None = None) -> dict[str, Any]:
    """
    从照片中提取人脸向量（512维），并存入MySQL和Milvus向量库

    Args:
        photo_url: 照片URL（可以是本地路径或远程URL）
        profile_id: 用户ID
        source_dsn: 数据源DSN（可选，用于写入MySQL）

    Returns:
        dict: 包含人脸向量、检测置信度等信息
        None: 如果没有检测到人脸
    """
    # 1. 提取人脸向量（原有逻辑）
    result = extract_face_embedding(photo_url)

    if not result or not result.get("success"):
        return result

    # 2. 存入MySQL（原有逻辑，如果提供了source_dsn）
    if source_dsn:
        try:
            from profile_service import upsert_profile_face_embedding

            upsert_profile_face_embedding(
                source_dsn=source_dsn,
                profile_id=profile_id,
                face_embedding_json=json.dumps(result["face_embedding"]),
                face_embedding_model="Facenet512",
                face_embedding_dimension=512,
                face_detection_confidence=result.get("face_detection_confidence"),
                face_bbox_json=json.dumps(result.get("face_bbox")) if result.get("face_bbox") else None,
                is_primary_face=True,
                cache_status="computed",
            )

        except Exception as mysql_error:
            # MySQL写入失败不影响主流程
            pass

    # 3. 【新增】写入Milvus向量库
    try:
        from persona_memory_sync.persona_memory_lib import upsert_vector

        upsert_vector(
            profile_id=profile_id,
            vector_type="face_embedding",  # 新增向量类型
            vector_data=result["face_embedding"],
            vector_model="Facenet512",
            metadata={
                "photo_url": photo_url,
                "face_detection_confidence": result.get("face_detection_confidence"),
                "face_bbox": result.get("face_bbox"),
            }
        )

        result["milvus_saved"] = True
        return result

    except Exception as milvus_error:
        # Milvus写入失败不影响主流程，但记录状态
        result["milvus_saved"] = False
        result["milvus_error"] = str(milvus_error)
        return result


__all__ = [
    "extract_face_embedding",
    "extract_and_store_face_embedding",  # 新增
    "compute_face_similarity",
    "DEEPFACE_AVAILABLE",
    "DEEPFACE_FACENET512_WEIGHTS",
    "FACE_EMBEDDING_MODEL_NAME",
    "warmup_face_embedding_model",
]
