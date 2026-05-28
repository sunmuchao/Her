import { fetchCaseConversationTimeline } from '@/lib/api/endpoints/relations'
import { fetchMyProxyIntroCases } from '@/lib/api/endpoints/proxy-intro'
import type { CaseConversationTimelineResponse } from '@/lib/types/relations'
import { getChatParticipantId, getUserId } from '@/lib/auth/session'

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
  const participantId = getChatParticipantId()
  const timelineActorId = getUserId()

  try {
    const proxyCases = await fetchMyProxyIntroCases()
    const cases = proxyCases.cases || []
    const pendingCount = cases.filter((item) => item.can_reply || item.can_open_chat).length

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
