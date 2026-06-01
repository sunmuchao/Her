/**
 * 价值观拍卖会 API 类型定义
 *
 * 包含卡片类型定义和 API 调用函数
 */

import { gatewayJson } from '@/lib/api/client'

// ============================================================
// 特质定义
// ============================================================

export type ValuesTrait = {
  trait_id: string
  trait_name: string
  trait_name_en: string
  description: string
  detail?: string
}

// ============================================================
// 卡片类型定义
// ============================================================

/** 介绍卡片 */
export type ValuesAuctionIntroCard = {
  card_type: 'values_auction_intro'
  assessment_id: string
  intro_data: {
    title: string
    description: string
    total_chips: number
    trait_count: number
    duration: string
    reward: string
  }
}

/** 特质列表卡片 */
export type ValuesAuctionTraitsCard = {
  card_type: 'values_auction_traits'
  assessment_id: string
  session_id?: string  // 双人模式时有
  traits_data: {
    traits: ValuesTrait[]
    total_chips: number
    min_bid: number
    max_bid: number
  }
  internal_state?: {   // 双人模式时有
    user_has_done: boolean
    last_result: {
      value_type: string
      top3: Array<{ trait_id: string; trait_name: string; chips: number }>
    } | null
    partner_key: string
  }
  is_dual_mode?: boolean
}

/** 竞拍结果卡片 */
export type ValuesAuctionResultCard = {
  card_type: 'values_auction_result'
  assessment_id: string
  result_data: {
    bids: Array<{
      trait_id: string
      trait_name: string
      chips: number
      rank: number
      percentage: number
    }>
    value_type: string
    value_labels: string[]
    top3: Array<{
      trait_id: string
      trait_name: string
      chips: number
      interpretation: string
    }>
    abandoned: string[]
    reward?: string
  }
}

/** AI解读卡片 */
export type ValuesAuctionInterpretationCard = {
  card_type: 'values_auction_interpretation'
  assessment_id: string
  interpretation_data: {
    summary: string
    love_style: string
    match_suggestions: string[]
    caution_traits?: string[]
    top3_analysis?: Array<{
      trait_name: string
      chips: number
      interpretation: string
    }>
  }
}

/** 等待对方卡片 */
export type ValuesAuctionWaitingCard = {
  card_type: 'values_auction_waiting'
  session_id: string
  waiting_data: {
    message: string
    your_result: {
      value_type: string
      top3: Array<{ trait_name: string; chips: number }>
    }
    partner_status: string
  }
}

/** 匹配分析卡片 */
export type ValuesMatchAnalysisCard = {
  card_type: 'values_match_analysis'
  session_id: string
  match_data: {
    session_id: string
    user1: {
      user_key: string
      value_type: string
      top3: Array<{ trait_id: string; trait_name: string; chips: number }>
    }
    user2: {
      user_key: string
      value_type: string
      top3: Array<{ trait_id: string; trait_name: string; chips: number }>
    }
    match_type: string
    top3_common: string[]
    conflicts: Array<{
      type: string
      description: string
      suggestion: string
    }>
    ai_interpretation: string
  }
}

/** 历史记录卡片 */
export type ValuesAuctionHistoryCard = {
  card_type: 'values_auction_history'
  result_data: {
    value_type: string
    top3: Array<{ trait_id: string; trait_name: string; chips: number; interpretation?: string }>
    assessed_at: string
  } | null
}

/** 错误卡片 */
export type ValuesAuctionErrorCard = {
  card_type: 'error'
  error_data: {
    message: string
  }
}

/** 所有价值观拍卖卡片类型 */
export type ValuesAuctionCard =
  | ValuesAuctionIntroCard
  | ValuesAuctionTraitsCard
  | ValuesAuctionResultCard
  | ValuesAuctionInterpretationCard
  | ValuesAuctionWaitingCard
  | ValuesMatchAnalysisCard
  | ValuesAuctionHistoryCard
  | ValuesAuctionErrorCard

// ============================================================
// API 调用函数
// ============================================================

/**
 * 开始价值观拍卖（单人模式）
 */
export async function startValuesAuction(
  userKey: string
): Promise<ValuesAuctionIntroCard> {
  return gatewayJson<ValuesAuctionIntroCard>('/v1/values-auction/start', {
    method: 'POST',
    includeAuth: true,
    body: JSON.stringify({ user_key: userKey }),
  })
}

/**
 * 获取特质列表
 */
export async function getValuesAuctionTraits(
  assessmentId: string
): Promise<ValuesAuctionTraitsCard> {
  return gatewayJson<ValuesAuctionTraitsCard>('/v1/values-auction/traits', {
    method: 'POST',
    includeAuth: true,
    body: JSON.stringify({ assessment_id: assessmentId }),
  })
}

/**
 * 提交竞拍结果（单人模式）
 */
export async function submitValuesAuctionBids(params: {
  assessmentId: string
  userKey: string
  bids: Array<{ trait_id: string; chips: number }>
}): Promise<ValuesAuctionResultCard> {
  return gatewayJson<ValuesAuctionResultCard>('/v1/values-auction/submit', {
    method: 'POST',
    includeAuth: true,
    body: JSON.stringify({
      assessment_id: params.assessmentId,
      user_key: params.userKey,
      bids: params.bids,
    }),
  })
}

/**
 * 获取AI解读
 */
export async function getValuesAuctionInterpretation(params: {
  assessmentId: string
  userKey: string
}): Promise<ValuesAuctionInterpretationCard> {
  return gatewayJson<ValuesAuctionInterpretationCard>('/v1/values-auction/interpretation', {
    method: 'POST',
    includeAuth: true,
    body: JSON.stringify({
      assessment_id: params.assessmentId,
      user_key: params.userKey,
    }),
  })
}

/**
 * 获取历史记录（复用机制）
 */
export async function getValuesAuctionHistory(
  userKey: string
): Promise<ValuesAuctionHistoryCard> {
  return gatewayJson<ValuesAuctionHistoryCard>(`/v1/values-auction/history?user_key=${userKey}`, {
    method: 'GET',
    includeAuth: true,
  })
}

// ============================================================
// 双人拍卖 API
// ============================================================

/**
 * 开始双人价值观拍卖
 */
export async function startValuesAuctionTogether(params: {
  userKey: string
  partnerKey: string
}): Promise<ValuesAuctionTraitsCard> {
  return gatewayJson<ValuesAuctionTraitsCard>('/v1/values-auction/start-together', {
    method: 'POST',
    includeAuth: true,
    body: JSON.stringify({
      user_key: params.userKey,
      partner_key: params.partnerKey,
    }),
  })
}

/**
 * 提交双人拍卖结果
 */
export async function submitValuesAuctionBidsTogether(params: {
  sessionId: string
  userKey: string
  bids: Array<{ trait_id: string; chips: number }>
}): Promise<ValuesAuctionWaitingCard | ValuesMatchAnalysisCard> {
  return gatewayJson<ValuesAuctionWaitingCard | ValuesMatchAnalysisCard>('/v1/values-auction/submit-together', {
    method: 'POST',
    includeAuth: true,
    body: JSON.stringify({
      session_id: params.sessionId,
      user_key: params.userKey,
      bids: params.bids,
    }),
  })
}

/**
 * 检查双人拍卖状态（轮询）
 */
export async function checkValuesAuctionStatus(params: {
  sessionId: string
  userKey: string
}): Promise<{ status: string; card_type?: string; match_data?: any; partner_status?: string }> {
  return gatewayJson<any>('/v1/values-auction/check-status', {
    method: 'POST',
    includeAuth: true,
    body: JSON.stringify({
      session_id: params.sessionId,
      user_key: params.userKey,
    }),
  })
}

/**
 * 复用上次结果（双人模式）
 */
export async function reuseValuesAuctionTogether(params: {
  sessionId: string
  userKey: string
}): Promise<ValuesAuctionWaitingCard | ValuesMatchAnalysisCard> {
  return gatewayJson<ValuesAuctionWaitingCard | ValuesMatchAnalysisCard>('/v1/values-auction/reuse-together', {
    method: 'POST',
    includeAuth: true,
    body: JSON.stringify({
      session_id: params.sessionId,
      user_key: params.userKey,
    }),
  })
}

// ============================================================
// 筹码分配辅助函数
// ============================================================

/**
 * 计算总筹码
 */
export function calculateTotalChips(bids: Record<string, number>): number {
  return Object.values(bids).reduce((sum, chips) => sum + chips, 0)
}

/**
 * 检查筹码是否有效
 */
export function isValidBidDistribution(bids: Record<string, number>, maxTotal: number = 10): boolean {
  const total = calculateTotalChips(bids)
  return total <= maxTotal && total >= 0
}

/**
 * 将 bids 对象转换为数组格式
 */
export function bidsToArray(bids: Record<string, number>): Array<{ trait_id: string; chips: number }> {
  return Object.entries(bids)
    .map(([trait_id, chips]) => ({ trait_id, chips }))
    .filter(b => b.chips > 0)  // 只保留有筹码的
}