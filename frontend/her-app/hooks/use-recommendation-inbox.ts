'use client'

import { useEffect, useState } from 'react'
import {
  fetchConversionViewsForSubscription,
  fetchRecommendationCards,
  type RecommendationCard,
} from '@/lib/api/endpoints/recommendation'
import { fetchRelationsMine, formatConversionStageLabel } from '@/lib/api/endpoints/relations'
import { fetchMyProxyIntroCases, type ProxyIntroCase } from '@/lib/api/endpoints/proxy-intro'
import { getProfileId } from '@/lib/auth/session'
import { PLACEHOLDER_AVATAR, resolveProfileImageUrl } from '@/lib/image-url'

export type InboxItem = {
  id: string
  listKey: string
  cardId?: string
  subscriptionId?: string
  recommendationId?: number
  candidateId?: number
  caseId?: string  // 新增：用于 ProxyIntroCase
  name: string
  age: number
  city: string
  occupation: string
  matchScore: number
  image: string
  type: 'delayed' | 'matched' | 'interest'  // 新增：interest 类型
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

function mapProxyIntroCaseToInboxItem(caseItem: ProxyIntroCase): InboxItem {
  // 获取发起方信息（对于被动推荐，counterpart 就是发起方）
  // 优先使用 outreach_payload.requester_summary（新格式）
  // 否则使用 counterpart_profile 或 requester_profile_snapshot（旧格式兼容）
  const requesterSummary = caseItem.outreach_payload?.requester_summary || {}
  const counterpartProfile = caseItem.counterpart_profile || {}
  const requesterProfile = caseItem.requester_profile_snapshot?.self_profile || {}

  // 提取名字：优先 requester_summary，然后 counterpart，最后 requester_profile
  const name = requesterSummary.requester_name
    || String(counterpartProfile.display_name || counterpartProfile.name || '')
    || String(requesterProfile.display_name || requesterProfile.name || '')
    || '有人'

  // 提取年龄
  let age = 0
  if (requesterSummary.age_bracket) {
    const bracketMatch = requesterSummary.age_bracket.match(/(\d+)-(\d+)/)
    if (bracketMatch) age = parseInt(bracketMatch[1])
  } else {
    age = parseInt(String(counterpartProfile.age || requesterProfile.age || '0')) || 0
  }

  // 提取城市
  const city = requesterSummary.city
    || String(counterpartProfile.city || '')
    || String(requesterProfile.city || '')
    || '未知'

  // 提取职业
  const occupation = requesterSummary.occupation
    || String(counterpartProfile.job || counterpartProfile.occupation || '')
    || String(requesterProfile.job || requesterProfile.occupation || '')
    || '资料待补充'

  // 提取头像
  const image = resolveProfileImageUrl(
    requesterSummary.avatar_url
    || String(counterpartProfile.avatar_url || counterpartProfile.photo_url || '')
    || String(requesterProfile.avatar_url || requesterProfile.photo_url || ''),
    PLACEHOLDER_AVATAR
  )

  return {
    id: String(caseItem.counterpart_profile_id || caseItem.case_id),
    listKey: `case:${caseItem.case_id}`,
    cardId: undefined,
    subscriptionId: undefined,
    recommendationId: undefined,
    candidateId: caseItem.counterpart_profile_id ?? undefined,
    caseId: String(caseItem.case_id),
    name,
    age,
    city,
    occupation,
    matchScore: 0,
    image,
    type: 'interest',
    message: requesterSummary.summary_text || `${name}想通过平台进一步认识你`,
    time: caseItem.created_at || '刚刚',
    isRead: caseItem.case_status !== 'awaiting_reply',
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
        // 加载推荐卡片
        const response = await fetchRecommendationCards(Number(profileId))
        if (cancelled) return
        const cards = response.cards?.map(mapCardToInboxItem) || []

        // 加载被动推荐 case（有人想认识你）
        let interestCards: InboxItem[] = []
        try {
          const casesResponse = await fetchMyProxyIntroCases()
          if (cancelled) return
          console.log('[推荐来信] 加载 ProxyIntroCase:', casesResponse)
          // 过滤出当前用户作为被请求方且等待回复的 case
          const interestCases = (casesResponse.cases || []).filter(
            (c) => c.role === 'candidate' && c.case_status === 'awaiting_reply'
          )
          console.log('[推荐来信] 过滤后的被动推荐 case:', interestCases)
          interestCards = interestCases.map(mapProxyIntroCaseToInboxItem)
        } catch (err) {
          // 加载失败时忽略
          console.error('[推荐来信] 加载 ProxyIntroCase 失败:', err)
        }

        // 合并推荐卡片和被动推荐
        const allItems = [...cards, ...interestCards]
        console.log('[推荐来信] 合并后的总列表:', allItems.length, '其中被动推荐:', interestCards.length)

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
        const enrichedCards = allItems.map((card) => ({
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
