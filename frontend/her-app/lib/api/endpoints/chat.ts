import { fetchCaseConversationTimeline } from '@/lib/api/endpoints/relations'
import { fetchMyProxyIntroCases } from '@/lib/api/endpoints/proxy-intro'
import { gatewayJson, queryString } from '@/lib/api/client'
import type { CaseConversationTimelineResponse } from '@/lib/types/relations'
import { getAccessToken, getChatParticipantId, getUserId } from '@/lib/auth/session'

const RELATIONSHIP_READ_MARKERS_KEY = 'her_relationship_read_markers'
export const RELATIONSHIP_READ_EVENT = 'her:relationships-read-state-changed'

type RelationshipReadMarkers = Record<string, number>

function readRelationshipReadMarkers(): RelationshipReadMarkers {
  if (typeof window === 'undefined') return {}
  const raw = window.localStorage.getItem(RELATIONSHIP_READ_MARKERS_KEY)
  if (!raw) return {}
  try {
    return JSON.parse(raw) as RelationshipReadMarkers
  } catch {
    return {}
  }
}

function writeRelationshipReadMarkers(markers: RelationshipReadMarkers) {
  if (typeof window === 'undefined') return
  window.localStorage.setItem(RELATIONSHIP_READ_MARKERS_KEY, JSON.stringify(markers))
}

export function getConversationReadMarker(conversationId: string): number {
  const normalizedConversationId = String(conversationId || '').trim()
  if (!normalizedConversationId) return 0
  return Number(readRelationshipReadMarkers()[normalizedConversationId] || 0)
}

export function markConversationRead(conversationId: string, lastSeenMessageId: number) {
  const normalizedConversationId = String(conversationId || '').trim()
  const normalizedMessageId = Number(lastSeenMessageId || 0)
  if (!normalizedConversationId || !Number.isFinite(normalizedMessageId) || normalizedMessageId <= 0) return
  const markers = readRelationshipReadMarkers()
  const previous = Number(markers[normalizedConversationId] || 0)
  if (normalizedMessageId <= previous) return
  markers[normalizedConversationId] = normalizedMessageId
  writeRelationshipReadMarkers(markers)
  if (typeof CustomEvent === 'function') {
    window.dispatchEvent(new CustomEvent(RELATIONSHIP_READ_EVENT, {
      detail: { conversationId: normalizedConversationId, lastSeenMessageId: normalizedMessageId },
    }))
  }
}

export function countUnreadMessagesFromTimeline(
  data: CaseConversationTimelineResponse | null | undefined,
  participantId: string,
): number {
  const normalizedParticipantId = String(participantId || '').trim()
  if (!data || !normalizedParticipantId) return 0
  return (data.conversations || [])
    .filter((item) => item.conversation.channel_key === 'main_group')
    .reduce((sum, item) => {
      const last = item.messages[item.messages.length - 1]
      const conversationId = String(item.conversation.conversation_id || '').trim()
      const readMarker = getConversationReadMarker(conversationId)
      if (
        last &&
        last.author_id !== normalizedParticipantId &&
        Number(last.message_id || 0) > readMarker
      ) {
        return sum + 1
      }
      return sum
    }, 0)
}

export async function fetchRelationshipsUnreadSummary(): Promise<{
  total: number
  chatUnread: number
  pendingCount: number
  byCaseId: Record<string, number>
}> {
  if (!getAccessToken()) {
    return {
      total: 0,
      chatUnread: 0,
      pendingCount: 0,
      byCaseId: {},
    }
  }

  const participantId = getChatParticipantId()
  const timelineActorId = getUserId()

  try {
    const proxyCases = await fetchMyProxyIntroCases()
    const cases = proxyCases.cases || []

    // 日志1：打印所有case的详细信息
    console.log('[Badge Debug] 所有cases:', cases.map((item) => ({
      case_id: item.case_id,
      role: item.role,
      case_status: item.case_status,
      can_reply: item.can_reply,
      can_open_chat: item.can_open_chat,
      main_conversation_id: item.main_conversation_id,
      counterpart_name: item.counterpart_name,
    })))

    // 统一口径：pendingCount计算逻辑与buildPendingIntroItems完全一致
    // 避免badge数字与页面显示不一致
    const pendingCases = cases.filter((item) => {
      // 排除已关闭的case（closed、declined、timed_out）
      const status = item.case_status || ''
      if (status === 'closed' || status === 'declined' || status === 'timed_out') {
        return false
      }

      // 发起方（requester/matcher）：显示所有未开聊的case（包括等待对方决定的）
      // 但排除已查看的case（viewed状态，用户已看到但未决定）
      if (item.role !== 'candidate') {
        return !item.main_conversation_id && status !== 'viewed'
      }
      // 被推荐方（candidate）：只显示已接受或已开聊的case（已建立关系）
      // 被动推荐（awaiting_reply、viewed）不显示在关系页，显示在Discover页inbox
      return item.case_status === 'accepted' || item.main_conversation_id
    })

    const pendingCount = pendingCases.length

    // 日志2：打印pendingCount计算的详细信息
    console.log('[Badge Debug] Pending cases:', pendingCases.map((item) => ({
      case_id: item.case_id,
      role: item.role,
      case_status: item.case_status,
      counterpart_name: item.counterpart_name,
      reason: item.role !== 'candidate' ? '发起方未开聊' : '被推荐方已接受',
    })))
    console.log('[Badge Debug] pendingCount:', pendingCount)

    if (!timelineActorId || !participantId) {
      return {
        total: pendingCount,
        chatUnread: 0,
        pendingCount,
        byCaseId: {},
      }
    }

    const activeCaseIds = [...new Set(
      cases
        .filter((item) => {
          // 只统计未关闭的case（排除closed、declined、timed_out）
          const status = item.case_status || ''
          if (status === 'closed' || status === 'declined' || status === 'timed_out') {
            return false
          }
          // 必须有main_conversation_id（已开聊）
          return item.main_conversation_id && item.case_id
        })
        .map((item) => String(item.case_id)),
    )]

    const timelines = await Promise.all(
      activeCaseIds.map(async (caseId) => ({
        caseId,
        data: await fetchCaseConversationTimeline(caseId, timelineActorId).catch(() => null),
      })),
    )

    const byCaseId = timelines.reduce<Record<string, number>>((acc, item) => {
      const unread = countUnreadMessagesFromTimeline(item.data, participantId)
      acc[item.caseId] = unread

      // 日志3：打印每个case的chat unread详细信息
      if (unread > 0) {
        console.log('[Badge Debug] Chat unread case:', {
          case_id: item.caseId,
          unread_count: unread,
          has_timeline: !!item.data,
        })
      }

      return acc
    }, {})
    const chatUnread = Object.values(byCaseId).reduce((sum, value) => sum + value, 0)

    // 日志4：打印chatUnread总数
    console.log('[Badge Debug] chatUnread:', chatUnread)
    console.log('[Badge Debug] total badge:', chatUnread + pendingCount)

    return {
      total: chatUnread + pendingCount,
      chatUnread,
      pendingCount,
      byCaseId,
    }
  } catch {
    return {
      total: 0,
      chatUnread: 0,
      pendingCount: 0,
      byCaseId: {},
    }
  }
}

export async function fetchRelationshipsUnreadCount(): Promise<number> {
  const summary = await fetchRelationshipsUnreadSummary()
  return summary.total
}

/**
 * 获取案例下所有会话（群聊 + 私信）
 */
export type CaseConversation = {
  conversationId: string
  channelKey: string
  conversationKind: string
  members: Array<{
    participantId: string
    memberRole: string
  }>
}

export async function fetchCaseConversations(
  caseId: string,
  requesterId: string,
): Promise<CaseConversation[]> {
  const data = await fetchCaseConversationTimeline(caseId, requesterId, 1)
  return (data.conversations || []).map((item) => ({
    conversationId: item.conversation.conversation_id,
    channelKey: item.conversation.channel_key,
    conversationKind: item.conversation.conversation_kind,
    members: (item.conversation.members || []).map((m) => ({
      participantId: m.participant_id,
      memberRole: m.member_role,
    })),
  }))
}

/**
 * 获取私信会话ID（assistant_dm_xxx）
 * 根据会话成员列表判断哪个 assistant_dm 属于当前用户
 */
export async function fetchPrivateChatConversationId(
  caseId: string,
  requesterId: string,
): Promise<string | null> {
  const conversations = await fetchCaseConversations(caseId, requesterId)
  // 私信会话的 channel_key 为 assistant_dm_a 或 assistant_dm_b
  // 需要检查会话成员列表来确定属于当前用户的会话
  const dmConversation = conversations.find(
    (c) =>
      c.channelKey.startsWith('assistant_dm_') &&
      c.members.some((m) => m.participantId === requesterId && m.memberRole === 'human'),
  )
  return dmConversation?.conversationId || null
}

/**
 * 获取私信消息列表
 */
export type PrivateMessage = {
  id: string
  authorId: string
  body: string
  createdAt: string
  isFromMe: boolean
  mediaType?: string  // 消息类型（text/image/audio）
  mediaUrl?: string   // 媒体文件URL
  mediaMetadata?: {   // 媒体元数据
    duration_ms?: number
    format?: string
    size?: number
    tts_engine?: string
    voice?: string
  }
  isNewMessage?: boolean  // 是否为新消息（用于自动播放语音）
}

export async function fetchPrivateMessages(
  conversationId: string,
  requesterId: string,
): Promise<PrivateMessage[]> {
  const data = await gatewayJson<{
    messages: Array<{
      message_id: number
      author_id: string
      body: string
      created_at: string
      metadata_json?: {
        media_type?: string
        media_url?: string
        media_metadata?: {
          duration_ms?: number
          format?: string
          size?: number
          tts_engine?: string
          voice?: string
        }
      }
    }>
  }>(`/v2/chat/conversations/${conversationId}/messages${queryString({ requester_id: requesterId })}`)

  return (data.messages || []).map((m) => ({
    id: String(m.message_id),
    authorId: m.author_id,
    body: m.body,
    createdAt: m.created_at,
    isFromMe: m.author_id === requesterId,
    mediaType: m.metadata_json?.media_type,
    mediaUrl: m.metadata_json?.media_url,
    mediaMetadata: m.metadata_json?.media_metadata,
  }))
}

/**
 * 发送私信
 */
export async function sendPrivateMessage(
  conversationId: string,
  authorId: string,
  body: string,
): Promise<void> {
  await gatewayJson(`/v2/chat/conversations/${conversationId}/messages`, {
    method: 'POST',
    body: JSON.stringify({ author_id: authorId, body }),
  })
}
