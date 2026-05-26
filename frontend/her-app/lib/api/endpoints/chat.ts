import { fetchCaseConversationTimeline } from '@/lib/api/endpoints/relations'
import { getCaseId, getChatParticipantId, getUserId } from '@/lib/auth/session'

export async function fetchRelationshipsUnreadCount(): Promise<number> {
  const caseId = getCaseId()
  const participantId = getChatParticipantId()
  const timelineActorId = getUserId()
  if (!caseId || !timelineActorId || !participantId) return 0

  try {
    const data = await fetchCaseConversationTimeline(caseId, timelineActorId)
    return data.conversations
      .filter((item) => item.conversation.channel_key === 'main_group')
      .reduce((sum, item) => {
        const last = item.messages[item.messages.length - 1]
        if (last && last.author_id !== participantId) {
          return sum + 1
        }
        return sum
      }, 0)
  } catch {
    return 0
  }
}
