import { gatewayJson, queryString } from '@/lib/api/client'
import { getRequesterId } from '@/lib/auth/session'

type RecommendationCard = {
  card_id?: string
  card_status?: string
}

type RecommendationCardsResponse = {
  cards?: RecommendationCard[]
}

export async function fetchInboxUnreadCount(requesterId?: number): Promise<number> {
  const id = requesterId ?? getRequesterId()
  if (!id) return 0

  const response = await gatewayJson<RecommendationCardsResponse>(
    `/v1/recommendation/cards${queryString({
      requester_id: id,
      unread_only: true,
    })}`,
  )
  return response.cards?.length ?? 0
}
