import { gatewayJson, queryString } from '@/lib/api/client'
import type { ConversionView } from '@/lib/types/relations'
import { getProfileId } from '@/lib/auth/session'

type RecommendationCard = {
  card_id?: string
  card_status?: string
}

type RecommendationCardsResponse = {
  cards?: RecommendationCard[]
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

export async function createRecommendationSubscription(params: {
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
        profile_id: params.profileId,
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
