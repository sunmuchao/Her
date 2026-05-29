import { gatewayJson, queryString } from '@/lib/api/client'

/**
 * 获取案例timeline（包含AI红娘主动提示）
 * 用于chat-page展示完整的对话历史（用户对话 + AI红娘提示）
 */
export async function fetchCaseTimeline(
  caseId: string,
  requesterId: string,
  messageLimit = 50,
): Promise<CaseTimelineResponse> {
  return gatewayJson<CaseTimelineResponse>(
    `/v2/chat/cases/${caseId}/timeline${queryString({
      requester_id: requesterId,
      message_limit: messageLimit,
    })}`,
  )
}

/**
 * 获取案例下的所有会话列表（用于判断会话布局）
 */
export async function fetchCaseConversationsList(
  caseId: string,
  requesterId: string,
): Promise<CaseConversationsListResponse> {
  return gatewayJson<CaseConversationsListResponse>(
    `/v2/chat/cases/${caseId}/conversations${queryString({ requester_id: requesterId })}`,
  )
}

/**
 * 在会话中发送消息（支持用户消息和agent消息）
 */
export async function sendConversationMessage(
  conversationId: string,
  authorId: string,
  body: string,
  source = 'user',
): Promise<SendMessageResponse> {
  return gatewayJson<SendMessageResponse>(
    `/v2/chat/conversations/${conversationId}/messages`,
    {
      method: 'POST',
      body: JSON.stringify({
        author_id: authorId,
        source,
        body,
      }),
    },
  )
}

// Type definitions

export type CaseTimelineResponse = {
  case_id: string
  requester_id: string
  conversation_count: number
  conversations: Array<{
    conversation: {
      conversation_id: string
      channel_key: string
      conversation_kind: string
      members?: Array<{
        participant_id: string
        member_role: string
      }>
    }
    messages: Array<ConversationMessage>
  }>
  source_mode?: 'ledger_primary' | 'legacy_fallback'
  ledger_summary?: Record<string, unknown>
  unified_timeline?: Array<UnifiedTimelineEvent>
}

export type CaseConversationsListResponse = {
  case_id: string
  requester_id: string
  conversation_count: number
  conversations: Array<{
    conversation_id: string
    channel_key: string
    conversation_kind: string
    members?: Array<{
      participant_id: string
      member_role: string
    }>
  }>
}

export type ConversationMessage = {
  message_id: number
  author_id: string
  source: string
  body: string
  created_at: string
}

export type SendMessageResponse = {
  message: ConversationMessage
}

export type UnifiedTimelineEvent = {
  source?: string
  occurred_at?: string
  event_type?: string
  source_service?: string
  case_id?: string | null
  case_type?: string | null
  aggregate_type?: string
  aggregate_id?: string
  actor_type?: string
  actor_id?: string
}

/**
 * 消息类型映射
 */
export type ChatMessageType = 'sent' | 'received' | 'assistant'

/**
 * 将原始消息转换为前端消息格式
 */
export function mapConversationMessage(
  msg: ConversationMessage,
  requesterId: string,
): ChatMessageDisplay {
  const isAgent = msg.source === 'agent'
  const isMe = msg.author_id === requesterId

  return {
    id: String(msg.message_id),
    type: isAgent ? 'assistant' : isMe ? 'sent' : 'received',
    content: msg.body,
    timestamp: msg.created_at,
    authorId: msg.author_id,
    source: msg.source,
  }
}

export type ChatMessageDisplay = {
  id: string
  type: ChatMessageType
  content: string
  timestamp: string
  authorId?: string
  source?: string
  // 媒体消息字段
  mediaType?: 'image' | 'video' | 'audio'
  mediaUrl?: string
  mediaMetadata?: {
    width?: number
    height?: number
    size?: number
    mimeType?: string
  }
}

/**
 * 从timeline中提取main_group会话的消息
 */
export function extractMainGroupMessages(
  timeline: CaseTimelineResponse,
  requesterId: string,
): ChatMessageDisplay[] {
  const mainGroup = timeline.conversations.find(
    (c) => c.conversation.channel_key === 'main_group',
  )

  if (!mainGroup) {
    return []
  }

  return mainGroup.messages.map((msg) => mapConversationMessage(msg, requesterId))
}

/**
 * 判断是否有AI红娘的新消息（用于未读提示）
 */
export function hasNewAssistantMessages(
  timeline: CaseTimelineResponse,
  lastSeenMessageId: number,
): boolean {
  const mainGroup = timeline.conversations.find(
    (c) => c.conversation.channel_key === 'main_group',
  )

  if (!mainGroup) {
    return false
  }

  return mainGroup.messages.some(
    (msg) => msg.source === 'agent' && msg.message_id > lastSeenMessageId,
  )
}