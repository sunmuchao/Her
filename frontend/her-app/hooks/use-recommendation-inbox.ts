'use client'

import { useEffect, useState } from 'react'
import {
  fetchConversionViewsForSubscription,
  fetchRecommendationCards,
  type RecommendationCard,
} from '@/lib/api/endpoints/recommendation'
import { fetchRelationsMine, formatConversionStageLabel } from '@/lib/api/endpoints/relations'
import { getProfileId } from '@/lib/auth/session'
import { PLACEHOLDER_AVATAR, resolveProfileImageUrl } from '@/lib/image-url'

export type InboxItem = {
  id: string
  listKey: string
  cardId?: string
  subscriptionId?: string
  recommendationId?: number
  candidateId?: number
  name: string
  age: number
  city: string
  occupation: string
  matchScore: number
  image: string
  type: 'delayed' | 'matched'
  message: string
  time: string
  isRead: boolean
  conversionStage?: string
}

function mapCardToInboxItem(card: RecommendationCard): InboxItem {
  const snapshot = card.payload?.result_snapshot
  const profile = snapshot?.profile
  const candidateId = snapshot?.id || card.candidate_id
  const listKey =
    String(card.card_id || '').trim() ||
    (card.recommendation_id != null ? `rec:${card.recommendation_id}` : '') ||
    (candidateId != null ? `candidate:${candidateId}:${card.subscription_id || 'unknown'}` : '')
  return {
    id: String(candidateId || card.card_id),
    listKey,
    cardId: card.card_id,
    subscriptionId: card.subscription_id,
    recommendationId: card.recommendation_id,
    candidateId,
    name: snapshot?.name || card.title?.replace(/^发现新的合适对象：/, '') || '候选人',
    age: profile?.age || 0,
    city: profile?.city || '未知',
    occupation: profile?.job || '资料待补充',
    matchScore: snapshot?.score || 0,
    image: resolveProfileImageUrl(profile?.avatar_url, PLACEHOLDER_AVATAR),
    type: 'matched',
    message: card.body || card.title || '系统为你推送了一位新候选人',
    time: card.created_at || '刚刚',
    isRead: card.card_status === 'read',
    conversionStage: undefined,
  }
}

export function useRecommendationInbox() {
  const [isLoading, setIsLoading] = useState(true)
  const [backendItems, setBackendItems] = useState<InboxItem[]>([])

  useEffect(() => {
    const profileId = getProfileId()
    if (!profileId) {
      setIsLoading(false)
      return
    }

    let cancelled = false
    async function loadCards() {
      try {
        const response = await fetchRecommendationCards(Number(profileId))
        if (cancelled) return
        const cards = response.cards?.map(mapCardToInboxItem) || []
        const conversionByCandidate = new Map<number, string>()
        try {
          const mine = await fetchRelationsMine()
          for (const relation of mine.relations || []) {
            const targetRef = String(relation.target_profile_ref || '')
            const match = targetRef.match(/^profile:(\d+)$/)
            if (!match) continue
            const candidateId = Number(match[1])
            const phase = String(relation.current_phase || relation.relation_status || '')
            if (phase) {
              conversionByCandidate.set(candidateId, formatConversionStageLabel(phase))
            }
          }
        } catch {
          const subscriptionIds = [...new Set(cards.map((card) => card.subscriptionId).filter(Boolean))] as string[]
          await Promise.all(
            subscriptionIds.map(async (subscriptionId) => {
              try {
                const views = await fetchConversionViewsForSubscription(subscriptionId)
                views.forEach((view) => {
                  if (view.candidate_id && view.conversion_stage) {
                    conversionByCandidate.set(
                      Number(view.candidate_id),
                      formatConversionStageLabel(view.conversion_stage),
                    )
                  }
                })
              } catch {
                // conversion views are optional enrichment
              }
            }),
          )
        }
        const enrichedCards = cards.map((card) => ({
          ...card,
          conversionStage:
            card.candidateId != null
              ? conversionByCandidate.get(Number(card.candidateId))
              : undefined,
        }))
        setBackendItems(enrichedCards)
      } finally {
        if (!cancelled) setIsLoading(false)
      }
    }

    void loadCards()
    return () => {
      cancelled = true
    }
  }, [])

  return { isLoading, backendItems }
}
