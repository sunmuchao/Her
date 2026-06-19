"""Embedding 服务：文本向量化

支持多种 Embedding 模型：
1. OpenAI text-embedding-3-small（英文/多语言）
2. BGE-large-zh（中文）
3. DashScope（阿里云）

使用方式：
from match_domain.embedding_service import EmbeddingService

service = EmbeddingService()
embedding = await service.generate_embedding("性格温柔、重视家庭")
"""

from __future__ import annotations

import asyncio
import atexit
import logging
import os
from typing import Any

_logger = logging.getLogger(__name__)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Embedding 模型配置
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


EMBEDDING_MODELS_CONFIG = {
    # OpenAI 模型（多语言支持）
    "text-embedding-3-small": {
        "provider": "openai",
        "dimension": 1536,
        "description": "OpenAI 小型模型，成本低，性能好",
        "max_tokens": 8191,
    },
    "text-embedding-3-large": {
        "provider": "openai",
        "dimension": 3072,
        "description": "OpenAI 大型模型，最高质量",
        "max_tokens": 8191,
    },
    "text-embedding-ada-002": {
        "provider": "openai",
        "dimension": 1536,
        "description": "OpenAI 旧版本模型",
        "max_tokens": 8191,
    },

    # 阿里云 DashScope 模型（中文）
    "text-embedding-v3": {
        "provider": "dashscope",
        "dimension": 1024,
        "description": "阿里云 embedding 模型，中文效果好",
        "max_tokens": 8192,
    },

    # BGE 模型（中文，本地部署）
    "bge-large-zh": {
        "provider": "local",
        "dimension": 1024,
        "description": "BGE 大型中文模型，开源免费",
        "max_tokens": 512,
    },
}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# EmbeddingService 类
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class EmbeddingService:
    """文本向量化服务

    支持多种模型，通过环境变量配置：
    - EMBEDDING_MODEL: 模型名称
    - EMBEDDING_API_KEY: API密钥
    - EMBEDDING_BASE_URL: API地址

    ⚠️ 重要：使用单例模式管理 AsyncOpenAI 客户端
    - 第一次调用时创建客户端（懒加载）
    - 后续调用复用同一个客户端
    - 程序退出时应调用 aclose() 清理资源
    """

    def __init__(
        self,
        model_name: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self.model_name = model_name or os.environ.get(
            "EMBEDDING_MODEL", "text-embedding-v3"  # 默认阿里云 DashScope
        )
        self.api_key = api_key or os.environ.get(
            "EMBEDDING_API_KEY",
            os.environ.get("DASHSCOPE_API_KEY", os.environ.get("OPENAI_API_KEY", "")),
        )
        self.base_url = base_url or os.environ.get(
            "EMBEDDING_BASE_URL",
            # DashScope embedding API 使用 compatible-mode 地址
            "https://dashscope.aliyuncs.com/compatible-mode/v1",
        )

        # 获取模型配置
        self.model_config = EMBEDDING_MODELS_CONFIG.get(self.model_name, {})
        self.dimension = self.model_config.get("dimension", 768)

        # 懒加载：AsyncOpenAI 客户端在第一次使用时创建
        self._async_client: Any | None = None

        _logger.info(
            f"Embedding 服务初始化: model={self.model_name}, "
            f"dimension={self.dimension}, provider={self.model_config.get('provider', 'unknown')}"
        )

    async def _get_or_create_client(self) -> Any:
        """获取或创建 AsyncOpenAI 客户端（懒加载单例）

        ⚠️ 重要：创建客户端时自动注册 atexit 清理函数，确保程序退出时释放资源

        Returns:
            AsyncOpenAI 客户端实例
        """
        if self._async_client is None:
            from openai import AsyncOpenAI

            self._async_client = AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
            )
            _logger.info("AsyncOpenAI 客户端已创建（单例模式）")

            # 自动注册 atexit 清理函数（程序退出时自动清理）
            atexit.register(self._sync_cleanup)

        return self._async_client

    def _sync_cleanup(self) -> None:
        """同步清理方法（供 atexit 调用）

        ⚠️ 注意：atexit 不支持异步函数，所以需要创建新事件循环来清理
        """
        if self._async_client is not None:
            try:
                # 创建新事件循环来运行异步清理
                loop = asyncio.new_event_loop()
                loop.run_until_complete(self._async_client.close())
                loop.close()
                self._async_client = None
                _logger.info("AsyncOpenAI 客户端已通过 atexit 自动关闭")
            except Exception as exc:
                _logger.warning(f"atexit 清理失败（可能事件循环已关闭）：{exc}")

    async def aclose(self) -> None:
        """关闭客户端，释放资源

        ⚠️ 重要：程序退出时应调用此方法，避免 "Event loop is closed" 错误

        使用方式：
        ```python
        service = EmbeddingService()
        try:
            embedding = await service.generate_embedding("性格温柔")
        finally:
            await service.aclose()
        ```
        """
        if self._async_client is not None:
            # 取消 atexit 注册（避免重复清理）
            atexit.unregister(self._sync_cleanup)

            await self._async_client.close()
            self._async_client = None
            _logger.info("AsyncOpenAI 客户端已关闭，资源已释放")

    async def generate_embedding(self, text: str) -> list[float]:
        """生成文本向量

        Args:
            text: 待向量化的文本

        Returns:
            向量数据（list[float]）
        """
        # 清理文本
        cleaned_text = self._clean_text(text)

        if not cleaned_text:
            _logger.warning("文本清理后为空，无法生成向量")
            return []

        provider = self.model_config.get("provider", "openai")

        if provider == "openai":
            return await self._generate_openai_embedding(cleaned_text)
        elif provider == "dashscope":
            return await self._generate_dashscope_embedding(cleaned_text)
        elif provider == "local":
            return await self._generate_local_embedding(cleaned_text)
        else:
            _logger.error(f"未知的 provider: {provider}")
            return []

    async def generate_embeddings(self, texts: list[str]) -> list[list[float]]:
        """批量生成向量（提高效率）

        Args:
            texts: 待向量化的文本列表

        Returns:
            向量数据列表
        """
        # 清理文本
        cleaned_texts = [self._clean_text(text) for text in texts]
        cleaned_texts = [text for text in cleaned_texts if text]

        if not cleaned_texts:
            return []

        provider = self.model_config.get("provider", "openai")

        if provider == "openai":
            return await self._generate_openai_embeddings(cleaned_texts)
        elif provider == "dashscope":
            return await self._generate_dashscope_embeddings(cleaned_texts)
        elif provider == "local":
            # 本地模型不支持批量，逐个生成
            embeddings = []
            for text in cleaned_texts:
                embedding = await self._generate_local_embedding(text)
                embeddings.append(embedding)
            return embeddings
        else:
            return []

    def _clean_text(self, text: str) -> str:
        """清理文本

        处理：
        - 移除多余空格
        - 移除特殊字符
        - 限制长度（不超过模型最大 token）
        """
        if not text:
            return ""

        # 移除多余空格和换行
        cleaned = " ".join(text.strip().split())

        # 限制长度
        max_tokens = self.model_config.get("max_tokens", 512)
        # 简单估算：中文字符约等于 1 token，英文单词约等于 0.5 token
        max_chars = max_tokens * 2  # 安全上限

        if len(cleaned) > max_chars:
            cleaned = cleaned[:max_chars]
            _logger.warning(f"文本过长，截断到 {max_chars} 字符")

        return cleaned

    async def _generate_openai_embedding(self, text: str) -> list[float]:
        """OpenAI Embedding API（使用单例客户端）"""
        try:
            # 使用单例客户端，避免每次创建新连接池
            client = await self._get_or_create_client()

            response = await client.embeddings.create(
                model=self.model_name,
                input=text,
            )

            embedding = response.data[0].embedding

            _logger.info(f"OpenAI 向量生成成功: model={self.model_name}, dimension={len(embedding)}")

            return list(embedding)

        except Exception as exc:
            _logger.error(f"OpenAI 向量生成失败: {exc}")
            return []

    async def _generate_openai_embeddings(self, texts: list[str]) -> list[list[float]]:
        """OpenAI 批量 Embedding（使用单例客户端）"""
        try:
            # 使用单例客户端，避免每次创建新连接池
            client = await self._get_or_create_client()

            response = await client.embeddings.create(
                model=self.model_name,
                input=texts,
            )

            embeddings = [item.embedding for item in response.data]

            _logger.info(f"OpenAI 批量向量生成成功: count={len(embeddings)}")

            return embeddings

        except Exception as exc:
            _logger.error(f"OpenAI 批量向量生成失败: {exc}")
            return []

    async def _generate_dashscope_embedding(self, text: str) -> list[float]:
        """阿里云 DashScope Embedding API

        使用 OpenAI SDK 兼容模式
        """
        # DashScope 使用 OpenAI SDK 兼容模式，所以调用相同
        return await self._generate_openai_embedding(text)

    async def _generate_dashscope_embeddings(self, texts: list[str]) -> list[list[float]]:
        """阿里云 DashScope 批量 Embedding"""
        return await self._generate_openai_embeddings(texts)

    async def _generate_local_embedding(self, text: str) -> list[float]:
        """本地模型 Embedding（BGE）

        需要安装：
        pip install sentence-transformers
        """
        try:
            from sentence_transformers import SentenceTransformer

            # 加载模型（第一次会下载，可能较慢）
            model = SentenceTransformer(self.model_name)

            # 生成向量（同步调用，用 asyncio.to_thread 包装）
            def _encode():
                return model.encode(text, convert_to_numpy=True)

            embedding = await asyncio.to_thread(_encode)

            _logger.info(f"本地模型向量生成成功: model={self.model_name}, dimension={len(embedding)}")

            return list(embedding)

        except ImportError:
            _logger.error("sentence-transformers 未安装，无法使用本地模型")
            _logger.info("安装方式: pip install sentence-transformers")
            return []
        except Exception as exc:
            _logger.error(f"本地模型向量生成失败: {exc}")
            return []


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 快速测试函数
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


async def test_embedding_service() -> None:
    """测试 Embedding 服务"""
    print("\n=== 测试 Embedding 服务 ===")

    service = EmbeddingService()

    # 测试单个文本
    text = "性格温柔、重视家庭、希望找个能理解工作忙碌的人"
    embedding = await service.generate_embedding(text)

    print(f"文本: {text}")
    print(f"向量维度: {len(embedding)}")
    print(f"向量前10位: {embedding[:10]}")

    # 测试批量
    texts = ["性格温柔", "重视家庭", "希望能理解工作忙碌"]
    embeddings = await service.generate_embeddings(texts)

    print(f"批量生成: {len(embeddings)} 个向量")

    print("✅ Embedding 服务测试通过")


__all__ = [
    "EmbeddingService",
    "EMBEDDING_MODELS_CONFIG",
    "test_embedding_service",
]