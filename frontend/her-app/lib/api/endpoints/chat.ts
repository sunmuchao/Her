import { fetchCaseConversationTimeline } from '@/lib/api/endpoints/relations'
import { fetchMyProxyIntroCases } from '@/lib/api/endpoints/proxy-intro'
import type { CaseConversationTimelineResponse } from '@/lib/types/relations'
import { getChatParticipantId, getUserId } from '@/lib/auth/session'

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
      if (last && last.author_id !== normalizedParticipantId) {
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
