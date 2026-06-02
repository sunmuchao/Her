/**
 * 价值观拍卖会 API 类型定义
 *
 * 包含卡片类型定义和 API 调用函数
 *
 * v3.0 游戏化改进版：
 * - 从 20 个精简到 9 个拍品（少即是多）
 * - 添加主题色、图标、解读、冲突提示（游戏卡牌感）
 * - 支持逐个展示模式（真实拍卖会体验）
 */

import { gatewayJson } from '@/lib/api/client'

// ============================================================
// 维度定义
// ============================================================

export type AuctionDimension = 'material_achievement' | 'emotion_connection' | 'self_growth' | 'altruism_devotion'

export const DIMENSION_LABELS: Record<AuctionDimension, string> = {
  material_achievement: '物质与成就',
  emotion_connection: '情感与连接',
  self_growth: '自我与成长',
  altruism_devotion: '利他与奉献',
}

// ============================================================
// 拍品定义（v3.0 游戏化改进版）
// ============================================================

export type ValuesLot = {
  lot_id: string
  title: string                  // 精简文案：一句话，不超过10字
  dimension: AuctionDimension
  hidden_values?: Array<{
    key: string
    weight: number
  }>
  // v3.0 新增字段（游戏卡牌感）
  theme_color?: string           // 主题色（如 "#F59E0B" 金色）
  icon?: string                  // 图标（如 "💰"）
  interpretation?: string        // 一句解读（帮助用户理解）
  conflict_hint?: string         // 冲突提示（帮助理解取舍）
}

export type HiddenValue = {
  key: string
  weight: number
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
    lot_count: number
    dimensions?: Record<string, string>
    duration: string
    reward: string
  }
}

/** 拍品列表卡片 */
export type ValuesAuctionLotsCard = {
  card_type: 'values_auction_lots'
  assessment_id: string
  session_id?: string  // 双人模式时有
  lots_data: {
    lots: ValuesLot[]
    lots_by_dimension?: Record<string, ValuesLot[]>
    dimensions?: Record<string, string>
    total_chips: number
    min_bid: number
    max_bid: number
  }
  internal_state?: {   // 双人模式时有
    user_has_done: boolean
    last_result: {
      value_type: string
      top3: Array<{ lot_id: string; title: string; chips: number }>
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
      lot_id: string
      title: string
      chips: number
      rank: number
      percentage: number
    }>
    hidden_values?: Record<string, number>
    top_hidden_values?: HiddenValue[]
    value_type: string
    value_labels: string[]
    top3: Array<{
      lot_id: string
      title: string
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
    top3_analysis?: Array<{
      title: string
      chips: number
      interpretation: string
    }>
    hidden_values_analysis?: HiddenValue[]
    love_style: string
    match_suggestions: string[]
    caution_traits?: string[]
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
      top3: Array<{ title: string; chips: number }>
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
      hidden_values?: Record<string, number>
      top3: Array<{ lot_id: string; title: string; chips: number }>
    }
    user2: {
      user_key: string
      value_type: string
      hidden_values?: Record<string, number>
      top3: Array<{ lot_id: string; title: string; chips: number }>
    }
    match_type: string
    common_lots?: string[]
    common_hidden_values?: Array<{
      key: string
      a_weight: number
      b_weight: number
    }>
    misalignments?: Array<{
      type: string
      lot_id: string
      description: string
    }>
    conflicts: Array<{
      type: string
      lot_id?: string
      description: string
      suggestion: string
    }>
  }
}

/** 历史记录卡片 */
export type ValuesAuctionHistoryCard = {
  card_type: 'values_auction_history'
  result_data: {
    value_type: string
    top3: Array<{ lot_id: string; title: string; chips: number; interpretation?: string }>
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
  | ValuesAuctionLotsCard
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
 * 获取拍品列表
 */
export async function getValuesAuctionLots(
  assessmentId: string
): Promise<ValuesAuctionLotsCard> {
  return gatewayJson<ValuesAuctionLotsCard>('/v1/values-auction/lots', {
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
  bids: Array<{ lot_id: string; chips: number }>
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
}): Promise<ValuesAuctionLotsCard> {
  return gatewayJson<ValuesAuctionLotsCard>('/v1/values-auction/start-together', {
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
  bids: Array<{ lot_id: string; chips: number }>
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
export function bidsToArray(bids: Record<string, number>): Array<{ lot_id: string; chips: number }> {
  return Object.entries(bids)
    .map(([lot_id, chips]) => ({ lot_id, chips }))
    .filter(b => b.chips > 0)  // 只保留有筹码的
}

// ============================================================
// 隐藏价值名称映射
// ============================================================

export const HIDDEN_VALUE_LABELS: Record<string, string> = {
  wealth: '财富',
  status: '地位',
  power: '权力',
  freedom: '自由',
  security: '安全感',
  love: '爱情',
  loyalty: '忠诚',
  family: '家庭',
  friendship: '友情',
  companionship: '陪伴',
  recognition: '认可',
  self_actualization: '自我实现',
  wisdom: '智慧',
  inner_peace: '内心平静',
  independence: '独立',
  altruism: '利他',
  social_responsibility: '社会责任',
  meaning: '意义',
}