/**
 * 价值观拍卖会卡片渲染器
 *
 * 根据 card_type 分发到对应的卡片组件。
 *
 * v2.0 更新：
 * - 使用 lot_id 而非 trait_id
 * - 支持 values_auction_lots 卡片类型
 */

import React from 'react'
import type { ValuesAuctionCard } from '@/lib/api/endpoints/valuesAuction'
import { ValuesAuctionIntroCardComponent } from './ValuesAuctionIntroCard'
import { ValuesAuctionBiddingCard } from './ValuesAuctionBiddingCard'
import { ValuesAuctionResultCardComponent } from './ValuesAuctionResultCard'
import { ValuesAuctionInterpretationCardComponent } from './ValuesAuctionInterpretationCard'
import { ValuesAuctionWaitingCard } from './ValuesAuctionWaitingCard'
import { ValuesMatchAnalysisCardComponent } from './ValuesMatchAnalysisCard'
import { DualValuesAuctionCard } from './DualValuesAuctionCard'

type Props = {
  card: ValuesAuctionCard
  userKey?: string
  onStart?: () => void
  onSubmitBids?: (bids: Array<{ lot_id: string; chips: number }>) => void
  onViewInterpretation?: () => void
  onShare?: () => void
  onContinue?: () => void
  onMatchReady?: (matchCard: any) => void
}

export function ValuesAuctionCardRenderer({
  card,
  userKey,
  onStart,
  onSubmitBids,
  onViewInterpretation,
  onShare,
  onContinue,
  onMatchReady,
}: Props) {
  // Type guards
  if (isIntroCard(card)) {
    return <ValuesAuctionIntroCardComponent card={card} onStart={onStart || (() => {})} />
  }

  if (isLotsCard(card)) {
    // 双人模式
    if (card.is_dual_mode && userKey) {
      return <DualValuesAuctionCard card={card} userKey={userKey} onComplete={onContinue} />
    }
    // 单人模式
    return <ValuesAuctionBiddingCard card={card} onSubmit={onSubmitBids || (() => {})} />
  }

  // 兼容旧的 traits 卡片类型
  if (isTraitsCard(card)) {
    // 双人模式
    if (card.is_dual_mode && userKey) {
      return <DualValuesAuctionCard card={card} userKey={userKey} onComplete={onContinue} />
    }
    // 单人模式
    return <ValuesAuctionBiddingCard card={card as any} onSubmit={onSubmitBids || (() => {})} />
  }

  if (isResultCard(card)) {
    return (
      <ValuesAuctionResultCardComponent
        card={card}
        onViewInterpretation={onViewInterpretation}
        onShare={onShare}
        onContinue={onContinue}
      />
    )
  }

  if (isInterpretationCard(card)) {
    return <ValuesAuctionInterpretationCardComponent card={card} onContinue={onContinue} />
  }

  if (isWaitingCard(card)) {
    if (!userKey || !onMatchReady) {
      return <div className="text-red-500">缺少必要参数</div>
    }
    return (
      <ValuesAuctionWaitingCard
        card={card}
        userKey={userKey}
        onMatchReady={onMatchReady}
        onContinueChat={onContinue}
      />
    )
  }

  if (isMatchAnalysisCard(card)) {
    return (
      <ValuesMatchAnalysisCardComponent
        card={card}
        currentUserKey={userKey}
        onContinue={onContinue}
      />
    )
  }

  if (isErrorCard(card)) {
    return (
      <div className="bg-red-50 rounded-xl p-4 text-red-700">
        ❌ {card.error_data.message}
      </div>
    )
  }

  // 默认：未知卡片类型
  return (
    <div className="bg-gray-50 rounded-xl p-4 text-gray-500">
      未知卡片类型: {(card as any).card_type}
    </div>
  )
}

// ============================================================
// Type Guards
// ============================================================

function isIntroCard(card: ValuesAuctionCard): card is ValuesAuctionCard & { card_type: 'values_auction_intro' } {
  return card.card_type === 'values_auction_intro'
}

function isLotsCard(card: ValuesAuctionCard): card is ValuesAuctionCard & { card_type: 'values_auction_lots' } {
  return card.card_type === 'values_auction_lots'
}

// 兼容旧的 traits 卡片类型
function isTraitsCard(card: ValuesAuctionCard): card is ValuesAuctionCard & { card_type: 'values_auction_traits' } {
  return card.card_type === 'values_auction_traits'
}

function isResultCard(card: ValuesAuctionCard): card is ValuesAuctionCard & { card_type: 'values_auction_result' } {
  return card.card_type === 'values_auction_result'
}

function isInterpretationCard(card: ValuesAuctionCard): card is ValuesAuctionCard & { card_type: 'values_auction_interpretation' } {
  return card.card_type === 'values_auction_interpretation'
}

function isWaitingCard(card: ValuesAuctionCard): card is ValuesAuctionCard & { card_type: 'values_auction_waiting' } {
  return card.card_type === 'values_auction_waiting'
}

function isMatchAnalysisCard(card: ValuesAuctionCard): card is ValuesAuctionCard & { card_type: 'values_match_analysis' } {
  return card.card_type === 'values_match_analysis'
}

function isErrorCard(card: ValuesAuctionCard): card is ValuesAuctionCard & { card_type: 'error' } {
  return card.card_type === 'error'
}

// ============================================================
// 导出组件索引
// ============================================================

export {
  ValuesAuctionIntroCardComponent,
  ValuesAuctionBiddingCard,
  ValuesAuctionResultCardComponent,
  ValuesAuctionInterpretationCardComponent,
  ValuesAuctionWaitingCard,
  ValuesMatchAnalysisCardComponent,
  ValuesAuctionChoiceCard,
  DualValuesAuctionCard,
} from './index'