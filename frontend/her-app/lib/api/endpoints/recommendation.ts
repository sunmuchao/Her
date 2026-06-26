import { gatewayJson, queryString } from '@/lib/api/client'
import type { ConversionView } from '@/lib/types/relations'
import { getProfileId } from '@/lib/auth/session'

export const RECOMMENDATION_READ_EVENT = 'her:recommendation-read-state-changed'

export type RecommendationCard = {
  card_id: string
  subscription_id?: string
  recommendation_id?: number
  candidate_id?: number
  card_status?: string
  title?: string
  body?: string
  created_at?: string
  payload?: {
    result_snapshot?: {
      id?: number
      name?: string
      score?: number
      profile?: {
        age?: number
        city?: string
        job?: string
        avatar_url?: string
      }
    }
  }
}

type RecommendationCardsResponse = {
  cards?: RecommendationCard[]
}

export async function fetchRecommendationCards(profileId: number) {
  return gatewayJson<RecommendationCardsResponse>(
    `/v1/recommendation/cards${queryString({ profile_id: profileId })}`,
  )
}

export async function markRecommendationCardsRead(profileId: number, cardIds: string[]) {
  const result = await gatewayJson('/v1/recommendation/cards/read', {
    method: 'POST',
    body: JSON.stringify({
      profile_id: profileId,
      card_ids: cardIds,
    }),
  })
  // 标记成功后触发事件，通知徽章计数刷新
  if (typeof window !== 'undefined' && typeof CustomEvent === 'function') {
    window.dispatchEvent(new CustomEvent(RECOMMENDATION_READ_EVENT, {
      detail: { profileId, cardIds },
    }))
  }
  return result
}

export async function postRecommendationAction(params: {
  subscriptionId: string
  candidateId: number
  actionType: string
  idempotencyKey: string
}) {
  return gatewayJson('/v1/recommendation/actions', {
    method: 'POST',
    headers: { 'Idempotency-Key': params.idempotencyKey },
    body: JSON.stringify({
      subscription_id: params.subscriptionId,
      candidate_id: params.candidateId,
      action_type: params.actionType,
      client_idempotency_key: params.idempotencyKey,
    }),
  })
}

export async function fetchInboxUnreadCount(profileId?: number): Promise<number> {
  const id = profileId ?? getProfileId()
  if (!id) return 0

  const response = await gatewayJson<RecommendationCardsResponse>(
    `/v1/recommendation/cards${queryString({
      profile_id: id,
      unread_only: true,
    })}`,
  )
  return response.cards?.length ?? 0
}

export async function fetchConversionViewsForSubscription(
  subscriptionId: string,
): Promise<ConversionView[]> {
  const response = await gatewayJson<{ conversion_views?: ConversionView[] }>(
    `/v1/recommendation/subscriptions/${encodeURIComponent(subscriptionId)}/conversion-views`,
  )
  return response.conversion_views || []
}

async function createRecommendationSubscription(params: {
  profileId: number
  criteria?: Record<string, unknown>
  title?: string
  source?: string
}) {
  return gatewayJson<{ subscription?: { subscription_id?: string } }>(
    '/v1/recommendation/subscriptions',
    {
      method: 'POST',
      body: JSON.stringify({
        requester_id: params.profileId,
        criteria: params.criteria || {},
        title: params.title || '发现页长期留意',
        source: params.source,
      }),
    },
  )
}

export async function saveDiscoveryAsSubscription(params: {
  profileId: number
  criteria?: Record<string, unknown>
}) {
  const data = await createRecommendationSubscription({
    profileId: params.profileId,
    criteria: params.criteria,
    title: '发现页保存的留意',
  })
  const subscriptionId = data.subscription?.subscription_id
  if (!subscriptionId) {
    throw new Error('创建订阅失败')
  }
  await gatewayJson(
    `/v1/recommendation/subscriptions/${encodeURIComponent(subscriptionId)}/refresh`,
    { method: 'POST', body: JSON.stringify({}) },
  )
  return subscriptionId
}
