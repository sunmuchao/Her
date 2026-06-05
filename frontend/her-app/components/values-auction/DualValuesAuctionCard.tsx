/**
 * 价值观拍卖会双人拍卖主组件
 *
 * 整合双人拍卖的完整流程：
 * 1. 复用/重做选择（如果用户做过）
 * 2. 竞拍交互
 * 3. 等待对方
 * 4. 匹配分析
 */

import React, { useState } from 'react'
import type { ValuesAuctionLotsCard } from '@/lib/api/endpoints/valuesAuction'
import {
  submitValuesAuctionBidsTogether,
  reuseValuesAuctionTogether,
  checkValuesAuctionStatus,
} from '@/lib/api/endpoints/valuesAuction'
import { ValuesAuctionChoiceCard } from './ValuesAuctionChoiceCard'
import { ValuesAuctionBiddingCard } from './ValuesAuctionBiddingCard'
import { ValuesAuctionWaitingCard } from './ValuesAuctionWaitingCard'
import { ValuesMatchAnalysisCardComponent } from './ValuesMatchAnalysisCard'

type Props = {
  card: ValuesAuctionLotsCard
  userKey: string
  onComplete?: () => void
}

type AppPhase = 'choice' | 'bidding' | 'waiting' | 'match'

export function DualValuesAuctionCard({ card, userKey, onComplete }: Props) {
  const { session_id, internal_state } = card

  // 状态
  const [phase, setPhase] = useState<AppPhase>(() => {
    // 如果用户做过，先显示选择
    if (internal_state?.user_has_done) {
      return 'choice'
    }
    return 'bidding'
  })

  const [matchCard, setMatchCard] = useState<any>(null)
  const [waitingCard, setWaitingCard] = useState<any>(null)

  // 复用上次结果
  const handleReuse = async () => {
    if (!session_id) return

    try {
      const result = await reuseValuesAuctionTogether({
        sessionId: session_id,
        userKey: userKey,
      })

      if (result.card_type === 'values_match_analysis') {
        setMatchCard(result)
        setPhase('match')
      } else if (result.card_type === 'values_auction_waiting') {
        setWaitingCard(result)
        setPhase('waiting')
      }
    } catch (error) {
      console.error('Reuse error:', error)
    }
  }

  // 重新做
  const handleRedo = () => {
    setPhase('bidding')
  }

  // 提交竞拍结果
  const handleSubmitBids = async (bids: Array<{ lot_id: string; chips: number }>) => {
    if (!session_id) return

    try {
      const result = await submitValuesAuctionBidsTogether({
        sessionId: session_id,
        userKey: userKey,
        bids: bids,
      })

      if (result.card_type === 'values_match_analysis') {
        setMatchCard(result)
        setPhase('match')
      } else if (result.card_type === 'values_auction_waiting') {
        setWaitingCard(result)
        setPhase('waiting')
      }
    } catch (error) {
      console.error('Submit error:', error)
    }
  }

  // 匹配分析准备好
  const handleMatchReady = (matchPayload: any) => {
    const resolvedMatchData = matchPayload?.match_data ?? matchPayload
    setMatchCard({
      card_type: 'values_match_analysis',
      session_id: session_id,
      match_data: resolvedMatchData,
    })
    setPhase('match')
  }

  // 渲染不同阶段
  if (phase === 'choice' && internal_state?.last_result) {
    return (
      <ValuesAuctionChoiceCard
        lastResult={internal_state.last_result}
        onReuse={handleReuse}
        onRedo={handleRedo}
      />
    )
  }

  if (phase === 'bidding') {
    return (
      <ValuesAuctionBiddingCard
        card={card}
        onSubmit={handleSubmitBids}
        isDualMode={true}
      />
    )
  }

  if (phase === 'waiting' && waitingCard) {
    return (
      <ValuesAuctionWaitingCard
        card={waitingCard}
        userKey={userKey}
        onMatchReady={handleMatchReady}
        onContinueChat={onComplete}
        lots={card.lots_data?.lots || []}
      />
    )
  }

  if (phase === 'match' && matchCard) {
    return (
      <ValuesMatchAnalysisCardComponent
        card={matchCard}
        currentUserKey={userKey}
        lots={card.lots_data?.lots || []}
        onContinue={onComplete}
      />
    )
  }

  return null
}
