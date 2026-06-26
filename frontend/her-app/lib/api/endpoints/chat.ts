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
    // 只统计发起方（requester/matcher）的pending case
    // 排除被动推荐case（role === 'candidate'），这些显示在Discover页的inbox badge
    const pendingCount = cases.filter((item) =>
      (item.can_reply || item.can_open_chat) && item.role !== 'candidate'
    ).length

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
        .filter((item) => item.main_conversation_id && item.case_id)
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
      return acc
    }, {})
    const chatUnread = Object.values(byCaseId).reduce((sum, value) => sum + value, 0)

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
    }>
  }>(`/v2/chat/conversations/${conversationId}/messages${queryString({ requester_id: requesterId })}`)
  
  return (data.messages || []).map((m) => ({
    id: String(m.message_id),
    authorId: m.author_id,
    body: m.body,
    createdAt: m.created_at,
    isFromMe: m.author_id === requesterId,
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
