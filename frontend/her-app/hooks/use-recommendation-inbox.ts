'use client'

import { useEffect, useState, useCallback } from 'react'
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
  // 新增字段：供卡片详细显示（后端已处理好）
  ageDisplay?: string  // 实际年龄显示（如"28岁")
  education?: string  // 学历
  relationshipGoal?: string  // 关系目标（中文）
  matchedOn?: string[]  // 匹配点列表
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

  // 提取年龄：后端已处理为实际年龄（如"28岁")
  let age = 0
  const ageDisplay = requesterSummary.age  // 后端已格式化为"28岁"
  if (ageDisplay) {
    const ageMatch = ageDisplay.match(/(\d+)岁/)
    if (ageMatch) age = parseInt(ageMatch[1])
  } else {
    // 兜底：从 profile 中提取实际年龄
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

  // 提取学历
  const education = requesterSummary.education
    || String(counterpartProfile.education || '')
    || String(requesterProfile.education || '')
    || ''

  // 提取关系目标（后端已映射为中文）
  const relationshipGoal = requesterSummary.relationship_goal
    || String(counterpartProfile.relationship_goal || '')
    || String(requesterProfile.relationship_goal || '')
    || ''

  // 提取匹配点
  const matchedOn = requesterSummary.matched_on || []

  // 提取头像
  const image = resolveProfileImageUrl(
    requesterSummary.avatar_url
    || String(counterpartProfile.avatar_url || counterpartProfile.photo_url || '')
    || String(requesterProfile.avatar_url || requesterProfile.photo_url || ''),
    PLACEHOLDER_AVATAR
  )

  // 构建 message：后端已处理好完整信息
  const message = requesterSummary.summary_text || `${name}想通过平台进一步认识你`

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
    message,  // 后端已处理好
    time: caseItem.created_at || '刚刚',
    isRead: caseItem.case_status !== 'awaiting_reply',
    conversionStage: undefined,
    // 新增字段：供卡片详细显示
    ageDisplay,  // 实际年龄显示（如"28岁")
    education,
    relationshipGoal,  // 中文关系目标
    matchedOn,  // 匹配点列表
  }
}

export function useRecommendationInbox() {
  const [isLoading, setIsLoading] = useState(true)
  const [backendItems, setBackendItems] = useState<InboxItem[]>([])
  const [readListKeys, setReadListKeys] = useState<Set<string>>(new Set())

  // 新增：标记已读函数（立即更新本地状态并持久化）
  const markItemRead = useCallback((item: InboxItem) => {
    // 立即更新前端状态
    setBackendItems((prevItems) =>
      prevItems.map((prevItem) =>
        prevItem.listKey === item.listKey
          ? { ...prevItem, isRead: true }
          : prevItem
      )
    )

    // 持久化到 sessionStorage（防止组件卸载后状态丢失）
    const readKeys = JSON.parse(sessionStorage.getItem('recommendation-read-keys') || '[]')
    if (!readKeys.includes(item.listKey)) {
      readKeys.push(item.listKey)
      sessionStorage.setItem('recommendation-read-keys', JSON.stringify(readKeys))
    }
  }, [])

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
          // 过滤出当前用户作为被请求方的 case（包括 awaiting_reply 和 viewed 状态）
          // viewed 状态的 case 也应该显示，用户可以主动左滑删除
          const interestCases = (casesResponse.cases || []).filter(
            (c) => c.role === 'candidate' && (c.case_status === 'awaiting_reply' || c.case_status === 'viewed')
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

        // 恢复 sessionStorage 中的已读状态（防止组件卸载后状态丢失）
        const readKeys = JSON.parse(sessionStorage.getItem('recommendation-read-keys') || '[]')

        // 恢复 sessionStorage 中的删除状态（防止组件卸载后状态丢失）
        const dismissedKeys = JSON.parse(sessionStorage.getItem('recommendation-dismissed-ids') || '[]')

        const restoredCards = enrichedCards.map((card) =>
          readKeys.includes(card.listKey)
            ? { ...card, isRead: true }
            : card
        )

        // 过滤掉已删除的卡片
        const finalCards = restoredCards.filter((card) => !dismissedKeys.includes(card.listKey))

        setBackendItems(finalCards)
      } finally {
        if (!cancelled) setIsLoading(false)
      }
    }

    void loadCards()
    return () => {
      cancelled = true
    }
  }, [])

  return { isLoading, backendItems, markItemRead }
}
