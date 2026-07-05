"""向量存储服务：基于 Milvus Lite 实现（轻量级本地存储）

Milvus Lite 3.0+ 使用 MilvusClient API：
- 本地文件存储（无需 Docker）
- 支持向量存储和搜索
- 支持版本管理

使用方式：
from match_domain.vector_store import VectorStoreLite

store = VectorStoreLite()
store.save_vector_with_version(...)
store.search_similar_users(...)
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

_logger = logging.getLogger(__name__)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 配置
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


COLLECTION_NAME = "user_vectors"
EMBEDDING_DIM = 1024  # DashScope text-embedding-v3 的向量维度
MILVUS_LITE_DB = os.environ.get("MILVUS_LITE_DB", "./milvus_lite_data/user_vectors.db")


VECTOR_TYPES_CONFIG = {
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 极稳定特征：性格特质（几年不变）
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    "personality_traits": {
        # ← 改造：移除 update_policy，改为AI自主判断
        "decay_days": 365,  # ← 改造：从30天延长到365天（极稳定）
        "decay_curve": "exponential",  # ← 新增：指数衰减（前期慢）
        "min_factor": 0.7,  # ← 新增：最低权重提高到0.7（不应过低）
        "max_version_count": 5,  # ← 新增：保留最近5个版本
        "cleanup_days": 90,  # ← 新增：超过90天的旧版本清理
        "description": "性格特质：极稳定，保留最近5个版本，清理超过90天的旧版本（如温柔、内向、开朗）",
    },

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 高度稳定特征：价值观（长期不变）
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    "values": {
        # ← 改造：移除 update_policy，改为AI自主判断
        "decay_days": 365,  # ← 改造：从60天延长到365天（高度稳定）
        "decay_curve": "linear",  # ← 新增：线性衰减（均匀）
        "min_factor": 0.7,  # ← 新增：最低权重提高到0.7（不应过低）
        "max_version_count": 5,  # ← 新增：保留最近5个版本
        "cleanup_days": 90,  # ← 新增：超过90天的旧版本清理
        "description": "价值观：高度稳定，保留最近5个版本，清理超过90天的旧版本（如重视家庭、重视事业）",
    },

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 中等稳定特征：生活态度（可能变化）
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    "life_attitude": {
        # ← 改造：移除 update_policy，改为AI自主判断
        "decay_days": 90,  # ← 改造：从30天延长到90天（中等稳定）
        "decay_curve": "exponential",  # ← 新增：指数衰减
        "min_factor": 0.5,  # ← 保持：最低权重0.5
        "max_version_count": 10,  # ← 新增：保留最近10个版本（中等稳定）
        "cleanup_days": 30,  # ← 新增：超过30天的旧版本清理
        "description": "生活态度：中等稳定，保留最近10个版本，清理超过30天的旧版本（如追求稳定、重视生活质量）",
    },

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 中等稳定特征：择偶期望（可能变化）
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    "partner_expectation": {
        # ← 改造：移除 update_policy，改为AI自主判断
        "decay_days": 90,  # ← 改造：从30天延长到90天（中等稳定）
        "decay_curve": "exponential",  # ← 新增：指数衰减
        "min_factor": 0.5,  # ← 保持：最低权重0.5
        "max_version_count": 10,  # ← 新增：保留最近10个版本（中等稳定）
        "cleanup_days": 30,  # ← 新增：超过30天的旧版本清理
        "description": "择偶期望：中等稳定，保留最近10个版本，清理超过30天的旧版本（如希望找个温柔的人）",
    },
    "partner_personality_preference": {
        "decay_days": 90,
        "decay_curve": "exponential",
        "min_factor": 0.5,
        "max_version_count": 10,
        "cleanup_days": 30,
        "description": "择偶中的性格偏好：如温和、细腻、有耐心、善沟通。",
    },
    "partner_relationship_pacing": {
        "decay_days": 90,
        "decay_curve": "exponential",
        "min_factor": 0.5,
        "max_version_count": 10,
        "cleanup_days": 30,
        "description": "择偶中的关系推进节奏：如慢热、不暧昧、节奏明确。",
    },
    "partner_lifestyle_preference": {
        "decay_days": 90,
        "decay_curve": "exponential",
        "min_factor": 0.5,
        "max_version_count": 10,
        "cleanup_days": 30,
        "description": "择偶中的生活方式偏好：如作息规律、工作稳定、排斥高压内卷。",
    },

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 波动较大特征：情感需求（短期波动）
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    "emotional_needs": {
        # ← 改造：移除 update_policy，改为AI自主判断
        "decay_days": 30,  # ← 保持：30天（波动大）
        "decay_curve": "linear",  # ← 新增：线性衰减（快速）
        "min_factor": 0.5,  # ← 保持：最低权重0.5
        "max_version_count": 15,  # ← 新增：保留最近15个版本（波动大）
        "cleanup_days": 7,  # ← 新增：超过7天的旧版本清理（波动大）
        "description": "情感需求：波动较大，保留最近15个版本，清理超过7天的旧版本（如需要理解和支持）",
    },
    "appearance_profile": {
        "decay_days": 180,
        "decay_curve": "linear",
        "min_factor": 0.8,
        "max_version_count": 5,
        "cleanup_days": 60,
        "description": "候选人照片风格语义：用于成熟、清爽、温柔、阳光等外观语义检索。",
    },
    "appearance_preference": {
        "decay_days": 120,
        "decay_curve": "exponential",
        "min_factor": 0.6,
        "max_version_count": 8,
        "cleanup_days": 45,
        "description": "用户照片审美偏好：由历史正负反馈聚合而成。",
    },
    "face_embedding": {
        "decay_days": 240,
        "decay_curve": "linear",
        "min_factor": 0.85,
        "max_version_count": 4,
        "cleanup_days": 90,
        "description": "人脸相似检索索引：由资料照主脸 embedding 扩展生成。",
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
# VectorStoreLite 类
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class VectorStoreLite:
    """向量存储服务：基于 Milvus Lite（轻量级）

    使用 MilvusClient API，本地文件存储
    """

    def __init__(self, db_file: str = MILVUS_LITE_DB) -> None:
        self.db_file = db_file
        self._ensure_db_dir()
        self._client = self._get_client()
        self._ensure_collection()

    def close(self) -> None:
        """关闭 MilvusClient 连接，释放资源

        ⚠️ 重要：程序退出时应调用此方法，避免 "Task exception was never retrieved" 错误

        使用方式：
        ```python
        vector_store = VectorStoreLite()
        try:
            vector_store.save_vector_with_version(...)
        finally:
            vector_store.close()
        ```

        根因分析（五问法）：
        - 问题现象：Task exception was never retrieved - RuntimeError('Event loop is closed')
        - 为什么1：httpx 异步连接池在事件循环关闭后尝试清理连接
        - 为什么2：程序退出时，事件循环先关闭，然后 httpx 清理任务才执行
        - 为什么3：MilvusClient 没有在事件循环关闭前被正确清理
        - 为什么4：之前的实现只设置 self._client = None，没有调用 MilvusClient.close()
        - 为什么5（根本原因）：VectorStoreLite.close() 缺少对 MilvusClient.close() 的调用

        修复方案：
        - 正确调用 MilvusClient.close() 来清理内部 httpx 异步连接池
        - 避免事件循环关闭后 httpx 尝试清理连接的错误
        """
        if self._client is not None:
            try:
                # 【修复】正确调用 MilvusClient.close() 来清理 httpx 异步连接池
                # MilvusClient.close() 会清理内部的 gRPC 和 httpx 异步连接
                self._client.close()
                self._client = None
                _logger.info("MilvusClient 连接已正确关闭，httpx 异步连接池已清理")
            except Exception as exc:
                _logger.warning(f"关闭 MilvusClient 连接失败: {exc}")
                # 即使关闭失败，也要设置为 None，避免重复关闭
                self._client = None

    def _ensure_db_dir(self) -> None:
        """确保数据库目录存在"""
        db_dir = os.path.dirname(self.db_file)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)

    def _get_client(self) -> Any:
        """获取 MilvusClient（配置 gRPC keepalive 参数）

        根因分析（五问法）：
        - 问题现象：gRPC 连接报错 "too_many_pings" (GOAWAY 错误码 11)
        - 为什么1：客户端发送 ping 帧过于频繁（默认每 10 秒一次）
        - 为什么2：pymilvus 默认 keepalive_time_ms=10000 太激进
        - 为什么3：缺少 grpc.http2.max_pings_without_data 参数限制
        - 为什么4：Milvus Lite 服务器期望更长的 ping 间隔
        - 为什么5（根本原因）：缺少 gRPC keepalive 参数的优化配置

        修复方案：
        - 调整 keepalive_time_ms 从 10s → 60s（降低 ping 频率）
        - 添加 grpc.http2.max_pings_without_data=0（无限制）
        - 保持 keepalive_permit_without_calls=True（允许无调用时 ping）

        参考：https://github.com/grpc/grpc/blob/master/doc/keepalive.md
        """
        from pymilvus import MilvusClient

        # 配置 gRPC keepalive 参数，避免 too_many_pings 错误
        grpc_options = {
            "grpc.keepalive_time_ms": 60000,  # 每 60 秒发送一次 ping（默认 10 秒太频繁）
            "grpc.keepalive_timeout_ms": 20000,  # 20 秒超时（默认 5 秒）
            "grpc.keepalive_permit_without_calls": True,  # 允许无调用时发送 ping
            "grpc.http2.max_pings_without_data": 0,  # 无限制（关键参数！避免服务器拒绝）
        }

        return MilvusClient(
            uri=self.db_file,
            grpc_options=grpc_options,
        )

    def _ensure_collection(self) -> None:
        """确保 Collection 存在且已加载到内存

        根因分析（五问法）：
        - 问题现象：查询时报错 Collection 'user_vectors' is in state 'released'
        - 为什么1：集合处于 'released' 状态，未加载到内存
        - 为什么2：程序启动时只检查集合是否存在，不检查是否已加载
        - 为什么3：_ensure_collection() 只在集合不存在时才调用 load_collection()
        - 为什么4：设计假设"集合创建后永远保持加载状态"，忽略了 Milvus 运行时行为
        - 为什么5（根本原因）：缺少"确保集合可查询"的健壮性设计

        修复方案：
        - 无论集合是否存在，都确保已加载到内存
        - 容错处理：Milvus 服务重启、内存压力、长时间运行后集合可能被自动释放

        参考：https://milvus.io/docs/load_collection.md
        """
        if not self._client.has_collection(COLLECTION_NAME):
            self._create_collection()  # 创建集合（内部会 load）
        else:
            # 【修复】集合已存在，但仍需确保已加载到内存
            # Milvus 集合在服务重启、内存压力后可能被自动释放（released状态）
            self._client.load_collection(collection_name=COLLECTION_NAME)
            _logger.info(f"Collection {COLLECTION_NAME} 已存在，重新加载到内存")

    def _create_collection(self) -> None:
        """创建 Collection"""
        from pymilvus import DataType

        schema = self._client.create_schema(
            auto_id=True,
            enable_dynamic_field=True,
        )

        schema.add_field("vector_id", DataType.INT64, is_primary=True)
        schema.add_field("user_id", DataType.INT64)
        schema.add_field("conversation_id", DataType.VARCHAR, max_length=50)
        schema.add_field("vector_type", DataType.VARCHAR, max_length=50)
        schema.add_field("vector_version", DataType.INT64)
        schema.add_field("embedding", DataType.FLOAT_VECTOR, dim=EMBEDDING_DIM)
        schema.add_field("raw_text", DataType.VARCHAR, max_length=500)
        schema.add_field("create_time", DataType.INT64)
        schema.add_field("is_active", DataType.BOOL)

        index_params = self._client.prepare_index_params()
        index_params.add_index(
            field_name="embedding",
            metric_type="COSINE",
            index_type="AUTOINDEX",
        )

        self._client.create_collection(
            collection_name=COLLECTION_NAME,
            schema=schema,
            index_params=index_params,
        )

        # 加载 Collection（重要：必须 load 才能搜索）
        self._client.load_collection(collection_name=COLLECTION_NAME)

        _logger.info(f"Collection {COLLECTION_NAME} 创建成功并已加载")

    def save_vector_with_version(
        self,
        user_id: int,
        vector_type: str,
        embedding: list[float],
        raw_text: str,
        conversation_id: str,
    ) -> dict[str, Any]:
        """存储向量（带版本管理）"""
        try:
            # 查询当前版本号
            current_version = self.get_current_vector_version(user_id, vector_type)
            new_version = current_version + 1

            # 软删除旧版本
            update_policy = VECTOR_TYPES_CONFIG.get(vector_type, {}).get(
                "update_policy", "replace"
            )
            if update_policy == "replace":
                self.deactivate_old_vectors(user_id, vector_type)

            # 插入新版本
            create_time = int(datetime.now().timestamp())
            data = {
                "user_id": user_id,
                "conversation_id": conversation_id,
                "vector_type": vector_type,
                "vector_version": new_version,
                "embedding": embedding,
                "raw_text": raw_text,
                "create_time": create_time,
                "is_active": True,
            }

            self._client.insert(
                collection_name=COLLECTION_NAME,
                data=[data],
            )

            _logger.info(
                f"向量存储成功: user_id={user_id}, vector_type={vector_type}, "
                f"version={new_version}"
            )

            return {
                "success": True,
                "user_id": user_id,
                "vector_type": vector_type,
                "version": new_version,
                "raw_text": raw_text,
            }

        except Exception as exc:
            _logger.error(f"向量存储失败: {exc}")
            return {"success": False, "error": str(exc)[:200]}

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

        改进说明：
        - 移除 time_decay_days 参数（硬编码）
        - 改为从 VECTOR_TYPES_CONFIG 自动读取配置
        - 调用 calculate_decay_factor 函数（支持指数衰减）
        """

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 改造：从 VECTOR_TYPES_CONFIG 读取衰减配置
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

        config = VECTOR_TYPES_CONFIG.get(vector_type, {})
        decay_days = config.get("decay_days", 30)  # 从配置读取衰减周期

        try:
            # 构建过滤表达式
            filter_expr = f"vector_type == '{vector_type}' and is_active == true"
            if exclude_user_ids:
                filter_expr += f" and user_id not in {exclude_user_ids}"

            # 搜索
            results = self._client.search(
                collection_name=COLLECTION_NAME,
                data=[user_vector],
                filter=filter_expr,
                limit=top_k,
                output_fields=[
                    "user_id",
                    "raw_text",
                    "vector_version",
                    "create_time",
                ],
            )

            # 处理结果，应用时间衰减
            similar_users: list[dict[str, Any]] = []
            current_time = int(datetime.now().timestamp())

            for result in results[0]:
                distance = result.get("distance", 0)

                if distance < similarity_threshold:
                    continue

                entity = result.get("entity", {})
                create_time = entity.get("create_time", 0)
                age_days = (current_time - create_time) / 86400 if create_time else 0

                # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                # 改造：调用新的 calculate_decay_factor 函数
                # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

                decay_factor = calculate_decay_factor(
                    age_days=age_days,
                    vector_type=vector_type,  # ← 根据vector_type自动选择衰减策略
                )

                adjusted_similarity = distance * decay_factor

                similar_users.append({
                    "user_id": entity.get("user_id"),
                    "raw_text": entity.get("raw_text"),
                    "similarity": adjusted_similarity,
                    "original_similarity": distance,
                    "version": entity.get("vector_version"),
                    "age_days": round(age_days, 1),
                    "decay_factor": round(decay_factor, 2),
                    # ← 新增：记录衰减配置信息（用于调试和可解释性）
                    "decay_config": {
                        "decay_days": decay_days,
                        "decay_curve": config.get("decay_curve", "linear"),
                        "min_factor": config.get("min_factor", 0.5),
                    }
                })

            similar_users.sort(key=lambda x: x["similarity"], reverse=True)

            _logger.info(
                f"向量搜索完成: 找到 {len(similar_users)} 个相似用户, "
                f"衰减配置: decay_days={decay_days}, decay_curve={config.get('decay_curve', 'linear')}"
            )

            return similar_users

        except Exception as exc:
            _logger.error(f"向量搜索失败: {exc}")
            return []

    def get_current_vector_version(self, user_id: int, vector_type: str) -> int:
        """查询当前版本号"""
        try:
            results = self._client.query(
                collection_name=COLLECTION_NAME,
                filter=f"user_id == {user_id} and vector_type == '{vector_type}'",
                output_fields=["vector_version"],
            )

            if results:
                return max([r.get("vector_version", 0) for r in results])
            return 0

        except Exception as exc:
            _logger.warning(f"查询版本号失败: {exc}")
            return 0

    def deactivate_old_vectors(self, user_id: int, vector_type: str) -> None:
        """软删除旧版本"""
        try:
            # 查询需要删除的向量
            results = self._client.query(
                collection_name=COLLECTION_NAME,
                filter=f"user_id == {user_id} and vector_type == '{vector_type}' and is_active == true",
                output_fields=["vector_id"],
            )

            if not results:
                return

            # 执行软删除
            for result in results:
                self._client.delete(
                    collection_name=COLLECTION_NAME,
                    ids=[result.get("vector_id")],
                )

            _logger.info(
                f"软删除旧版本向量: user_id={user_id}, "
                f"vector_type={vector_type}, count={len(results)}"
            )

        except Exception as exc:
            _logger.warning(f"软删除旧版本失败: {exc}")

    def get_user_vectors(
        self, user_id: int, vector_type: str | None = None
    ) -> list[dict[str, Any]]:
        """查询用户向量"""
        try:
            if vector_type:
                filter_expr = f"user_id == {user_id} and vector_type == '{vector_type}' and is_active == true"
            else:
                filter_expr = f"user_id == {user_id} and is_active == true"

            results = self._client.query(
                collection_name=COLLECTION_NAME,
                filter=filter_expr,
                output_fields=[
                    "vector_type",
                    "raw_text",
                    "vector_version",
                    "create_time",
                ],
            )

            return results

        except Exception as exc:
            _logger.error(f"查询用户向量失败: {exc}")
            return []

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 新增：版本清理方法
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def cleanup_old_versions(
        self,
        user_id: int,
        vector_type: str,
        *,
        max_version_count: int | None = None,
        cleanup_days: int | None = None,
    ) -> dict[str, Any]:
        """清理旧版本向量（物理删除）

        功能说明：
        - 保留最近的 max_version_count 个版本
        - 保留 cleanup_days 天内的版本
        - 其他版本物理删除（节省存储空间）

        Args:
            user_id: 用户ID
            vector_type: 向量类型
            max_version_count: 最大保留版本数（从配置读取）
            cleanup_days: 清理超过N天的旧版本（从配置读取）

        Returns:
            {
                "deleted_count": 删除的版本数量,
                "kept_count": 保留的版本数量,
            }
        """
        try:
            # 从配置读取参数
            config = VECTOR_TYPES_CONFIG.get(vector_type, {})
            max_count = max_version_count or config.get("max_version_count", 5)
            cleanup_age = cleanup_days or config.get("cleanup_days", 90)

            # 查询所有版本（包括 is_active=false）
            all_versions = self._client.query(
                collection_name=COLLECTION_NAME,
                filter=f"user_id == {user_id} and vector_type == '{vector_type}'",
                output_fields=["vector_id", "vector_version", "create_time", "is_active"],
            )

            if not all_versions:
                return {"deleted_count": 0, "kept_count": 0}

            # 按版本号降序排序
            sorted_versions = sorted(
                all_versions,
                key=lambda v: v.get("vector_version", 0),
                reverse=True,
            )

            current_time = int(datetime.now().timestamp())
            to_delete_ids: list[int] = []

            # 保留策略：
            # 1. 保留最近的 max_count 个版本
            # 2. 保留 cleanup_age 天内的版本
            # 3. 其他版本物理删除

            for idx, version in enumerate(sorted_versions):
                version_num = version.get("vector_version", 0)
                create_time = version.get("create_time", 0)
                age_days = (current_time - create_time) / 86400

                # 保留最近的 max_count 个版本
                if idx < max_count:
                    continue

                # 保留 cleanup_age 天内的版本
                if age_days < cleanup_age:
                    continue

                # 其他版本物理删除
                to_delete_ids.append(version.get("vector_id"))

            if to_delete_ids:
                self._client.delete(
                    collection_name=COLLECTION_NAME,
                    ids=to_delete_ids,
                )

                _logger.info(
                    f"清理旧版本向量: user_id={user_id}, "
                    f"vector_type={vector_type}, "
                    f"deleted={len(to_delete_ids)}, "
                    f"kept={len(sorted_versions) - len(to_delete_ids)}"
                )

            return {
                "deleted_count": len(to_delete_ids),
                "kept_count": len(sorted_versions) - len(to_delete_ids),
            }

        except Exception as exc:
            _logger.error(f"清理旧版本失败: {exc}")
            return {"deleted_count": 0, "kept_count": 0, "error": str(exc)[:200]}

    def cleanup_all_users_old_versions(
        self,
        vector_type: str,
        *,
        batch_size: int = 100,
    ) -> dict[str, Any]:
        """批量清理所有用户的旧版本

        功能说明：
        - 清理所有用户指定向量类型的旧版本
        - 分批处理，避免一次性清理太多影响性能

        Args:
            vector_type: 向量类型
            batch_size: 批次大小（默认100）

        Returns:
            {
                "total_users": 处理的用户总数,
                "total_deleted": 删除的版本总数,
                "errors": 错误列表,
            }
        """
        try:
            # 查询所有用户
            all_users = self._client.query(
                collection_name=COLLECTION_NAME,
                filter=f"vector_type == '{vector_type}'",
                output_fields=["user_id"],
            )

            # 提取唯一用户ID
            user_ids = set(u.get("user_id") for u in all_users)

            total_deleted = 0
            errors: list[str] = []

            for user_id in user_ids:
                try:
                    result = self.cleanup_old_versions(user_id, vector_type)
                    total_deleted += result.get("deleted_count", 0)
                except Exception as exc:
                    errors.append(f"user_id={user_id}, error={str(exc)[:100]}")

            _logger.info(
                f"批量清理完成: vector_type={vector_type}, "
                f"users={len(user_ids)}, deleted={total_deleted}"
            )

            return {
                "total_users": len(user_ids),
                "total_deleted": total_deleted,
                "errors": errors[:10],  # 只保留前10个错误
            }

        except Exception as exc:
            _logger.error(f"批量清理失败: {exc}")
            return {"total_users": 0, "total_deleted": 0, "error": str(exc)[:200]}


__all__ = [
    "VectorStoreLite",
    "VECTOR_TYPES_CONFIG",
    "calculate_decay_factor",
    "cleanup_old_versions",
    "cleanup_all_users_old_versions",
]
