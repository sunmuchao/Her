import { fetchCaseConversationTimeline } from '@/lib/api/endpoints/relations'
import { fetchMyProxyIntroCases } from '@/lib/api/endpoints/proxy-intro'
import { getCaseId, getChatParticipantId, getUserId } from '@/lib/auth/session'

export async function fetchRelationshipsUnreadCount(): Promise<number> {
  const caseId = getCaseId()
  const participantId = getChatParticipantId()
  const timelineActorId = getUserId()
  if (!caseId || !timelineActorId || !participantId) return 0

  try {
    const [data, proxyCases] = await Promise.all([
      fetchCaseConversationTimeline(caseId, timelineActorId).catch(() => null),
      fetchMyProxyIntroCases().catch(() => null),
    ])
    const chatUnread = (data?.conversations || [])
      .filter((item) => item.conversation.channel_key === 'main_group')
      .reduce((sum, item) => {
        const last = item.messages[item.messages.length - 1]
        if (last && last.author_id !== participantId) {
          return sum + 1
        }
        return sum
      }, 0)
    const pendingCount =
      proxyCases?.cases?.filter((item) => item.can_reply || item.can_open_chat).length || 0
    return chatUnread + pendingCount
  } catch {
    try {
      const proxyCases = await fetchMyProxyIntroCases()
      return proxyCases.cases?.filter((item) => item.can_reply || item.can_open_chat).length || 0
    } catch {
      return 0
    }
  }
}
