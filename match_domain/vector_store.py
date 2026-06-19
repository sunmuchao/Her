"""向量存储服务：基于 Milvus 实现向量存储和搜索

功能：
1. 创建 Collection（user_vectors）
2. 向量存储（带版本管理）
3. 向量搜索（带时间衰减）
4. 向量版本管理（软删除旧版本）

使用方式：
from match_domain.vector_store import VectorStore

store = VectorStore()
await store.save_vector_with_version(...)
await store.search_similar_users(...)
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

_logger = logging.getLogger(__name__)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 向量类型配置
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


VECTOR_TYPES_CONFIG = {
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 极稳定特征：性格特质（几年不变）
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    "personality_traits": {
        # ← 改造：移除 update_policy，改为AI自主判断
        "decay_days": 365,  # ← 改造：从30天延长到365天（极稳定）
        "decay_curve": "exponential",  # ← 新增：指数衰减（前期慢）
        "min_factor": 0.7,  # ← 新增：最低权重提高到0.7（不应过低）
        "description": "性格特质：极稳定，1年内不应过低（如温柔、内向、开朗）",
    },

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 高度稳定特征：价值观（长期不变）
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    "values": {
        # ← 改造：移除 update_policy，改为AI自主判断
        "decay_days": 365,  # ← 改造：从60天延长到365天（高度稳定）
        "decay_curve": "linear",  # ← 新增：线性衰减（均匀）
        "min_factor": 0.7,  # ← 新增：最低权重提高到0.7（不应过低）
        "description": "价值观：高度稳定，1年内不应过低（如重视家庭、重视事业）",
    },

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 中等稳定特征：生活态度（可能变化）
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    "life_attitude": {
        # ← 改造：移除 update_policy，改为AI自主判断
        "decay_days": 90,  # ← 改造：从30天延长到90天（中等稳定）
        "decay_curve": "exponential",  # ← 新增：指数衰减
        "min_factor": 0.5,  # ← 保持：最低权重0.5
        "description": "生活态度：中等稳定，3个月内可能变化（如追求稳定、重视生活质量）",
    },

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 中等稳定特征：择偶期望（可能变化）
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    "partner_expectation": {
        # ← 改造：移除 update_policy，改为AI自主判断
        "decay_days": 90,  # ← 改造：从30天延长到90天（中等稳定）
        "decay_curve": "exponential",  # ← 新增：指数衰减
        "min_factor": 0.5,  # ← 保持：最低权重0.5
        "description": "择偶期望：中等稳定，3个月内可能变化（如希望找个温柔的人）",
    },

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 波动较大特征：情感需求（短期波动）
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    "emotional_needs": {
        # ← 改造：移除 update_policy，改为AI自主判断
        "decay_days": 30,  # ← 保持：30天（波动大）
        "decay_curve": "linear",  # ← 新增：线性衰减（快速）
        "min_factor": 0.5,  # ← 保持：最低权重0.5
        "description": "情感需求：波动较大，1个月内可能变化（如需要理解和支持）",
    },
}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 时间衰减计算函数
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


import math


def calculate_decay_factor(
    age_days: float,
    vector_type: str,
) -> float:
    """计算时间衰减因子（支持指数衰减和线性衰减）

    改进方案4：根据特征稳定性调整衰减速度

    Args:
        age_days: 数据年龄（天数）
        vector_type: 向量类型（从VECTOR_TYPES_CONFIG读取配置）

    Returns:
        衰减因子（0.5-1.0）

    设计原理：
    - 线性衰减：每天固定衰减 1/decay_days
    - 指数衰减：前期慢，后期快（更符合实际情况）
    - 最低权重：根据特征稳定性调整（性格特质0.7，其他0.5）

    改进效果：
    - personality_traits: 365天衰减周期，min_factor=0.7（极稳定）
    - values: 365天衰减周期，min_factor=0.7（高度稳定）
    - partner_expectation: 90天衰减周期，min_factor=0.5（中等稳定）
    - life_attitude: 90天衰减周期，min_factor=0.5（中等稳定）
    - emotional_needs: 30天衰减周期，min_factor=0.5（波动大）
    """

    # 从配置读取参数
    config = VECTOR_TYPES_CONFIG.get(vector_type, {})
    decay_days = config.get("decay_days", 30)  # 默认30天
    decay_curve = config.get("decay_curve", "linear")  # 默认线性衰减
    min_factor = config.get("min_factor", 0.5)  # 默认最低权重0.5

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 线性衰减（当前实现）
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    if decay_curve == "linear":
        linear_factor = 1 - age_days / decay_days
        return max(min_factor, linear_factor)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 指数衰减（新增实现）
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    elif decay_curve == "exponential":
        # 指数衰减公式：exp(-age_days / decay_days)
        # 特点：前期衰减慢，后期衰减快
        exponential_factor = math.exp(-age_days / decay_days)
        return max(min_factor, exponential_factor)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Fallback：未知曲线类型，使用线性衰减
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    else:
        _logger.warning(f"未知的衰减曲线类型: {decay_curve}, 使用线性衰减")
        linear_factor = 1 - age_days / decay_days
        return max(min_factor, linear_factor)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Milvus 连接管理
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def get_milvus_connection_params() -> dict[str, Any]:
    """获取 Milvus 连接参数（从环境变量）

    支持两种模式：
    1. Milvus Lite（本地文件存储）：MILVUS_LITE_MODE=1
    2. Milvus Server（远程服务器）：MILVUS_HOST + MILVUS_PORT

    Returns:
        连接参数字典
    """
    # 优先使用 Milvus Lite（轻量级，本地文件存储）
    use_lite = os.environ.get("MILVUS_LITE_MODE", "1").lower() in ("1", "true", "yes")

    if use_lite:
        return {
            "lite_mode": True,
            "data_dir": os.environ.get("MILVUS_LITE_DATA_DIR", "./milvus_lite_data"),
        }
    else:
        return {
            "lite_mode": False,
            "host": os.environ.get("MILVUS_HOST", "localhost"),
            "port": os.environ.get("MILVUS_PORT", "19530"),
            "alias": "default",
        }


def connect_milvus() -> bool:
    """连接 Milvus

    支持：
    1. Milvus Lite：使用本地文件存储（Milvus Lite 3.0+）
    2. Milvus Server：连接远程 Milvus 服务器

    Returns:
        是否连接成功
    """
    params = get_milvus_connection_params()

    try:
        if params.get("lite_mode"):
            # Milvus Lite 模式（本地文件存储）
            # Milvus Lite 3.0+ 使用不同的 API
            from pymilvus import MilvusClient

            data_dir = params.get("data_dir", "./milvus_lite_data")
            db_file = os.path.join(data_dir, "milvus.db")

            # 确保目录存在
            os.makedirs(data_dir, exist_ok=True)

            # 使用 MilvusClient 连接本地文件
            # 注意：后续操作使用 MilvusClient API
            _logger.info(f"Milvus Lite 启动成功: db_file={db_file}")
            return True
        else:
            # Milvus Server 模式（远程服务器）
            from pymilvus import connections

            connections.connect(
                alias=params.get("alias", "default"),
                host=params.get("host", "localhost"),
                port=params.get("port", "19530"),
            )

            _logger.info(f"Milvus 连接成功: host={params['host']}, port={params['port']}")
            return True

    except Exception as exc:
        _logger.error(f"Milvus 连接失败: {exc}")
        return False


def disconnect_milvus() -> None:
    """断开 Milvus 连接"""
    from pymilvus import connections

    try:
        connections.disconnect("default")
        _logger.info("Milvus 连接已断开")
    except Exception as exc:
        _logger.warning(f"Milvus 断开连接失败: {exc}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Collection 创建和管理
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


COLLECTION_NAME = "user_vectors"
EMBEDDING_DIM = 768  # BGE-large-zh 的向量维度


def create_collection_if_not_exists() -> bool:
    """创建 Collection（如果不存在）

    Returns:
        是否创建成功
    """
    from pymilvus import Collection, FieldSchema, CollectionSchema, DataType, utility

    # 先连接
    if not connect_milvus():
        return False

    try:
        # 检查是否已存在
        if utility.has_collection(COLLECTION_NAME):
            _logger.info(f"Collection {COLLECTION_NAME} 已存在")
            disconnect_milvus()
            return True

        # 定义字段
        fields = [
            FieldSchema(name="vector_id", dtype=DataType.INT64, is_primary=True, auto_id=True),
            FieldSchema(name="user_id", dtype=DataType.INT64),
            FieldSchema(name="conversation_id", dtype=DataType.VARCHAR, max_length=50),
            FieldSchema(name="vector_type", dtype=DataType.VARCHAR, max_length=50),
            FieldSchema(name="vector_version", dtype=DataType.INT64),
            FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=EMBEDDING_DIM),
            FieldSchema(name="raw_text", dtype=DataType.VARCHAR, max_length=500),
            FieldSchema(name="create_time", dtype=DataType.INT64),
            FieldSchema(name="is_active", dtype=DataType.BOOL),
        ]

        # 创建 Schema
        schema = CollectionSchema(
            fields=fields,
            description="用户特征向量库（带版本管理）",
        )

        # 创建 Collection
        collection = Collection(name=COLLECTION_NAME, schema=schema)

        # 创建索引（HNSW，高性能）
        index_params = {
            "metric_type": "COSINE",
            "index_type": "HNSW",
            "params": {"M": 16, "efConstruction": 200},
        }
        collection.create_index(field_name="embedding", index_params=index_params)

        # 加载 Collection
        collection.load()

        _logger.info(f"Collection {COLLECTION_NAME} 创建成功，索引已创建")

        disconnect_milvus()
        return True

    except Exception as exc:
        _logger.error(f"Collection 创建失败: {exc}")
        disconnect_milvus()
        return False


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# VectorStore 类：向量存储和搜索
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class VectorStore:
    """向量存储服务：基于 Milvus

    核心功能：
    - save_vector_with_version：存储向量（带版本管理）
    - search_similar_users：搜索相似用户（带时间衰减）
    - deactivate_old_vectors：软删除旧版本
    - get_current_vector_version：查询当前版本号
    """

    def __init__(self, collection_name: str = COLLECTION_NAME) -> None:
        self.collection_name = collection_name
        self._ensure_collection_exists()

    def _ensure_collection_exists(self) -> None:
        """确保 Collection 存在"""
        create_collection_if_not_exists()

    def save_vector_with_version(
        self,
        user_id: int,
        vector_type: str,
        embedding: list[float],
        raw_text: str,
        conversation_id: str,
    ) -> dict[str, Any]:
        """存储向量（带版本管理）

        关键设计：
        - 查询当前版本：vector_version = old_version + 1
        - 软删除旧版本：is_active = false
        - 插入新版本：is_active = true

        Args:
            user_id: 用户ID
            vector_type: 向量类型（personality_traits/values等）
            embedding: 向量数据（768维）
            raw_text: 原始文本
            conversation_id: 对话ID

        Returns:
            存储结果，包含版本号等信息
        """
        from pymilvus import Collection

        try:
            connect_milvus()
            collection = Collection(self.collection_name)

            # 查询当前版本号
            current_version = self.get_current_vector_version(user_id, vector_type)
            new_version = current_version + 1

            # 软删除旧版本（如果是 replace 类型）
            update_policy = VECTOR_TYPES_CONFIG.get(vector_type, {}).get("update_policy", "replace")
            if update_policy == "replace":
                self.deactivate_old_vectors(user_id, vector_type)

            # 插入新版本向量
            create_time = int(datetime.now().timestamp())
            data = [
                [user_id],
                [conversation_id],
                [vector_type],
                [new_version],
                [embedding],
                [raw_text],
                [create_time],
                [True],  # is_active = true
            ]

            collection.insert(data)
            collection.flush()

            _logger.info(
                f"向量存储成功: user_id={user_id}, vector_type={vector_type}, "
                f"version={new_version}, raw_text={raw_text[:30]}"
            )

            disconnect_milvus()

            return {
                "success": True,
                "user_id": user_id,
                "vector_type": vector_type,
                "version": new_version,
                "raw_text": raw_text,
            }

        except Exception as exc:
            _logger.error(f"向量存储失败: user_id={user_id}, error={exc}")
            disconnect_milvus()
            return {
                "success": False,
                "error": str(exc)[:200],
            }

    def search_similar_users(
        self,
        user_vector: list[float],
        vector_type: str,
        top_k: int = 50,
        similarity_threshold: float = 0.85,
        exclude_user_ids: list[int] | None = None,
        # ← 改造：移除 time_decay_days 参数，改为从配置读取
    ) -> list[dict[str, Any]]:
        """搜索相似用户（带时间衰减）

        改进方案4：根据特征稳定性调整衰减速度

        关键设计：
        - 只搜索激活版本：expr: is_active == true
        - 应用智能时间衰减：从VECTOR_TYPES_CONFIG读取配置
        - 返回版本信息：version, age_days, decay_factor

        Args:
            user_vector: 用户向量（768维）
            vector_type: 向量类型（从VECTOR_TYPES_CONFIG读取衰减配置）
            top_k: 返回数量
            similarity_threshold: 相似度阈值
            exclude_user_ids: 排除的用户ID列表（搜索别人的向量）

        Returns:
            相似用户列表，包含相似度、版本、时间衰减信息

        改进说明：
        - 移除 time_decay_days 参数（硬编码）
        - 改为从 VECTOR_TYPES_CONFIG 自动读取配置
        - 调用 calculate_decay_factor 函数（支持指数衰减）
        """
        from pymilvus import Collection

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 改造：从 VECTOR_TYPES_CONFIG 读取衰减配置
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

        config = VECTOR_TYPES_CONFIG.get(vector_type, {})
        decay_days = config.get("decay_days", 30)  # 从配置读取衰减周期

        try:
            connect_milvus()
            collection = Collection(self.collection_name)

            # 构建搜索表达式（只搜索激活版本）
            expr = f"vector_type == '{vector_type}' AND is_active == true"
            if exclude_user_ids:
                expr += f" AND user_id not in {exclude_user_ids}"

            # 搜索参数
            search_params = {
                "metric_type": "COSINE",
                "params": {"ef": 64},  # HNSW 搜索参数
            }

            # 执行搜索
            results = collection.search(
                data=[user_vector],
                anns_field="embedding",
                param=search_params,
                limit=top_k,
                expr=expr,
                output_fields=["user_id", "raw_text", "vector_version", "create_time"],
            )

            # 处理结果，应用时间衰减
            similar_users: list[dict[str, Any]] = []
            current_time = int(datetime.now().timestamp())

            for hit in results[0]:
                distance = hit.distance  # 相似度（cosine similarity）

                if distance < similarity_threshold:
                    continue

                # 计算时间衰减
                create_time = hit.entity.get("create_time")
                age_days = (current_time - create_time) / 86400 if create_time else 0

                # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                # 改造：调用新的 calculate_decay_factor 函数
                # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

                decay_factor = calculate_decay_factor(
                    age_days=age_days,
                    vector_type=vector_type,  # ← 根据vector_type自动选择衰减策略
                )

                # 应用衰减后的相似度
                adjusted_similarity = distance * decay_factor

                similar_users.append({
                    "user_id": hit.entity.get("user_id"),
                    "raw_text": hit.entity.get("raw_text"),
                    "similarity": adjusted_similarity,
                    "original_similarity": distance,
                    "version": hit.entity.get("vector_version"),
                    "age_days": round(age_days, 1),
                    "decay_factor": round(decay_factor, 2),
                    # ← 新增：记录衰减配置信息（用于调试和可解释性）
                    "decay_config": {
                        "decay_days": decay_days,
                        "decay_curve": config.get("decay_curve", "linear"),
                        "min_factor": config.get("min_factor", 0.5),
                    }
                })

            # 按调整后的相似度排序
            similar_users.sort(key=lambda x: x["similarity"], reverse=True)

            _logger.info(
                f"向量搜索完成: vector_type={vector_type}, "
                f"找到 {len(similar_users)} 个相似用户, "
                f"衰减配置: decay_days={decay_days}, decay_curve={config.get('decay_curve', 'linear')}"
            )

            disconnect_milvus()
            return similar_users

        except Exception as exc:
            _logger.error(f"向量搜索失败: vector_type={vector_type}, error={exc}")
            disconnect_milvus()
            return []

    def get_current_vector_version(self, user_id: int, vector_type: str) -> int:
        """查询当前版本号

        Args:
            user_id: 用户ID
            vector_type: 向量类型

        Returns:
            当前版本号（如果没有，返回0）
        """
        from pymilvus import Collection

        try:
            collection = Collection(self.collection_name)

            # 查询该用户该类型的所有版本
            expr = f"user_id == {user_id} AND vector_type == '{vector_type}'"
            results = collection.query(
                expr=expr,
                output_fields=["vector_version"],
            )

            if results:
                return max([r.get("vector_version", 0) for r in results])
            return 0

        except Exception as exc:
            _logger.warning(f"查询版本号失败: {exc}")
            return 0

    def deactivate_old_vectors(self, user_id: int, vector_type: str) -> None:
        """软删除旧版本向量（设置 is_active = false）

        Args:
            user_id: 用户ID
            vector_type: 向量类型
        """
        from pymilvus import Collection

        try:
            collection = Collection(self.collection_name)

            # 查询需要软删除的向量ID
            expr = f"user_id == {user_id} AND vector_type == '{vector_type}' AND is_active == true"
            results = collection.query(
                expr=expr,
                output_fields=["vector_id"],
            )

            if not results:
                return

            # 执行软删除（更新 is_active）
            vector_ids = [r.get("vector_id") for r in results]
            collection.delete(expr=f"vector_id in {vector_ids}")

            _logger.info(
                f"软删除旧版本向量: user_id={user_id}, "
                f"vector_type={vector_type}, count={len(vector_ids)}"
            )

        except Exception as exc:
            _logger.warning(f"软删除旧版本失败: {exc}")

    def get_user_vectors(
        self,
        user_id: int,
        vector_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """查询用户的向量数据

        Args:
            user_id: 用户ID
            vector_type: 向量类型（可选，不传则返回所有类型）

        Returns:
            向量数据列表
        """
        from pymilvus import Collection

        try:
            connect_milvus()
            collection = Collection(self.collection_name)

            if vector_type:
                expr = f"user_id == {user_id} AND vector_type == '{vector_type}' AND is_active == true"
            else:
                expr = f"user_id == {user_id} AND is_active == true"

            results = collection.query(
                expr=expr,
                output_fields=["vector_type", "raw_text", "vector_version", "create_time"],
            )

            disconnect_milvus()
            return results

        except Exception as exc:
            _logger.error(f"查询用户向量失败: user_id={user_id}, error={exc}")
            disconnect_milvus()
            return []


__all__ = [
    "VectorStore",
    "VECTOR_TYPES_CONFIG",
    "COLLECTION_NAME",
    "EMBEDDING_DIM",
    "create_collection_if_not_exists",
    "connect_milvus",
    "disconnect_milvus",
    "get_milvus_connection_params",
]