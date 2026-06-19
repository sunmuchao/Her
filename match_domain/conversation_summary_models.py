"""Conversation summary models for storing LLM-generated user summaries.

This module provides ORM-style models for conversation summaries:
- ConversationSummaryDataclass: dataclass model (consistent with existing storage.py)
- ConversationSummary: Pydantic model (modern ORM style)

Conversation summaries can come from multiple sources:
- Discovery sessions (用户和红娘聊天)
- Chat threads (用户和候选人聊天)
- Assessment sessions (用户和测评师聊天)
- Other conversation types
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# Conversation types
CONVERSATION_TYPE_DISCOVERY = "discovery"
CONVERSATION_TYPE_CHAT = "chat"
CONVERSATION_TYPE_ASSESSMENT = "assessment"
CONVERSATION_TYPE_ONBOARDING = "onboarding"
CONVERSATION_TYPE_SUPPORT = "support"


@dataclass
class ConversationSummaryDataclass:
    """对话摘要数据类（dataclass 模式）

    用于存储 LLM 生成的用户特质、情感状态、择偶期望等主观描述。

    Attributes:
        summary_id: 摘要ID（自增主键）
        conversation_id: 对话ID（可以是 discovery session、chat thread 等）
        conversation_type: 对话类型（discovery/chat/assessment 等）
        requester_id: 用户ID
        profile_id: 画像ID
        summary: 摘要内容（100-200字）
        created_at: 创建时间
        updated_at: 更新时间
    """

    summary_id: int
    conversation_id: str
    conversation_type: str
    requester_id: int
    profile_id: int
    summary: str  # 摘要内容（100-200字）
    created_at: datetime
    updated_at: datetime


class ConversationSummary(BaseModel):
    """对话摘要 ORM 模型（Pydantic 模式）

    用于存储 LLM 生成的用户特质、情感状态、择偶期望等主观描述。

    Attributes:
        summary_id: 摘要ID（自增主键）
        conversation_id: 对话ID（可以是 discovery session、chat thread 等）
        conversation_type: 对话类型（discovery/chat/assessment 等）
        requester_id: 用户ID
        profile_id: 画像ID
        summary: 摘要内容（100-200字）
        created_at: 创建时间
        updated_at: 更新时间

    Example:
        ```python
        # Discovery 会话摘要
        summary = ConversationSummary(
            summary_id=1,
            conversation_id="discovery-session-001",
            conversation_type="discovery",
            requester_id=123,
            profile_id=456,
            summary="用户最近工作压力大，每天加班，父母催婚压力大。性格温柔，重视家庭。希望找一个能理解工作忙碌、重视家庭的伴侣。",
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )

        # Chat 会话摘要
        summary = ConversationSummary(
            summary_id=2,
            conversation_id="chat-thread-abc123",
            conversation_type="chat",
            requester_id=123,
            profile_id=456,
            summary="用户在聊天中提到不喜欢对方抽烟，希望对方周末能陪家人。",
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        ```
    """

    summary_id: int = Field(description="摘要ID（自增主键）")
    conversation_id: str = Field(description="对话ID（可以是 discovery session、chat thread 等）")
    conversation_type: str = Field(description="对话类型（discovery/chat/assessment 等）")
    requester_id: int = Field(description="用户ID")
    profile_id: int = Field(description="画像ID")
    summary: str = Field(description="摘要内容（100-200字）", min_length=10, max_length=500)
    created_at: datetime = Field(description="创建时间")
    updated_at: datetime = Field(description="更新时间")

    class Config:
        """Pydantic 配置"""

        json_schema_extra = {
            "example": {
                "summary_id": 1,
                "conversation_id": "discovery-session-001",
                "conversation_type": "discovery",
                "requester_id": 123,
                "profile_id": 456,
                "summary": "用户最近工作压力大，每天加班，父母催婚压力大。性格温柔，重视家庭。希望找一个能理解工作忙碌、重视家庭的伴侣。",
                "created_at": "2026-06-14T10:30:00",
                "updated_at": "2026-06-14T10:30:00",
            }
        }


class ConversationSummaryCreate(BaseModel):
    """创建对话摘要请求模型

    用于创建新的对话摘要时使用（不需要 summary_id，由数据库自动生成）。

    Attributes:
        conversation_id: 对话ID
        conversation_type: 对话类型
        requester_id: 用户ID
        profile_id: 画像ID
        summary: 摘要内容（100-200字）
    """

    conversation_id: str = Field(description="对话ID")
    conversation_type: str = Field(description="对话类型（discovery/chat/assessment 等）")
    requester_id: int = Field(description="用户ID")
    profile_id: int = Field(description="画像ID")
    summary: str = Field(description="摘要内容（100-200字）", min_length=10, max_length=500)


__all__ = [
    "ConversationSummaryDataclass",
    "ConversationSummary",
    "ConversationSummaryCreate",
    "CONVERSATION_TYPE_DISCOVERY",
    "CONVERSATION_TYPE_CHAT",
    "CONVERSATION_TYPE_ASSESSMENT",
    "CONVERSATION_TYPE_ONBOARDING",
    "CONVERSATION_TYPE_SUPPORT",
]