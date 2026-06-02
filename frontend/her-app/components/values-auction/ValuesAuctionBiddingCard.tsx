/**
 * 价值观拍卖会竞拍交互卡片
 *
 * v3.0 游戏化改进版：
 * - 默认使用逐个展示模式（真实拍卖会体验）
 * - 保留全景展示模式作为备选
 * - 支持紧张感提示和冲突提示
 * - 支持主题色和图标展示
 */

import React, { useState, useMemo } from 'react'
import { Minus, Plus, AlertCircle } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { ValuesAuctionLotsCard, ValuesLot, AuctionDimension } from '@/lib/api/endpoints/valuesAuction'
import { calculateTotalChips, DIMENSION_LABELS } from '@/lib/api/endpoints/valuesAuction'
import { SequentialBiddingCard } from './SequentialBiddingCard'

type Props = {
  card: ValuesAuctionLotsCard
  onSubmit: (bids: Array<{ lot_id: string; chips: number }>) => void
  isDualMode?: boolean
  // 新增：展示模式选择
  displayMode?: 'sequential' | 'panoramic'  // sequential = 逐个展示，panoramic = 全景展示
}

export function ValuesAuctionBiddingCard({ card, onSubmit, isDualMode, displayMode = 'sequential' }: Props) {
  // 默认使用逐个展示模式（真实拍卖会体验）
  if (displayMode === 'sequential') {
    return <SequentialBiddingCard card={card} onSubmit={onSubmit} isDualMode={isDualMode} />
  }

  // 保留全景展示模式作为备选（原逻辑）
  return <PanoramicBiddingCard card={card} onSubmit={onSubmit} isDualMode={isDualMode} />
}

// ============================================================
// 全景展示模式（原逻辑，作为备选）
// ============================================================

function PanoramicBiddingCard({ card, onSubmit, isDualMode }: Props) {
  const { lots_data } = card
  const { lots, lots_by_dimension, dimensions, total_chips, min_bid, max_bid } = lots_data

  // 筹码分配状态
  const [bids, setBids] = useState<Record<string, number>>(() => {
    // 初始化：所有拍品都是0筹码
    const initial: Record<string, number> = {}
    lots.forEach(l => {
      initial[l.lot_id] = 0
    })
    return initial
  })

  // 飞入动效状态
  const [flyingChips, setFlyingChips] = useState<{ lotId: string; count: number } | null>(null)

  // 计算总筹码
  const totalUsed = useMemo(() => calculateTotalChips(bids), [bids])
  const remaining = total_chips - totalUsed
  const isOverBudget = totalUsed > total_chips

  // 调整筹码
  const handleChipsChange = (lotId: string, delta: number) => {
    const newValue = Math.max(min_bid, Math.min(max_bid, bids[lotId] + delta))
    // 检查是否会超预算
    const newTotal = totalUsed - bids[lotId] + newValue
    if (newTotal <= total_chips) {
      setBids(prev => ({ ...prev, [lotId]: newValue }))

      // 触发飞入动效
      if (delta > 0) {
        setFlyingChips({ lotId, count: delta })
        setTimeout(() => setFlyingChips(null), 300)
      }
    }
  }

  // 直接设置筹码（用于滑块）
  const handleChipsSet = (lotId: string, value: number) => {
    const newValue = Math.max(min_bid, Math.min(max_bid, value))
    // 检查是否会超预算
    const newTotal = totalUsed - bids[lotId] + newValue
    if (newTotal <= total_chips) {
      setBids(prev => ({ ...prev, [lotId]: newValue }))
    }
  }

  // 提交
  const handleSubmit = () => {
    if (isOverBudget) return

    // 转换为数组格式
    const bidsArray = Object.entries(bids)
      .map(([lot_id, chips]) => ({ lot_id, chips }))
      .filter(b => b.chips >= 0)  // 包含0筹码的，用于排序

    onSubmit(bidsArray)
  }

  // 按维度分组的拍品
  const lotsGroupedByDimension = useMemo(() => {
    if (lots_by_dimension) {
      return lots_by_dimension
    }
    // 如果没有预分组，手动分组
    const grouped: Record<string, ValuesLot[]> = {}
    lots.forEach(lot => {
      const dim = lot.dimension || 'other'
      if (!grouped[dim]) {
        grouped[dim] = []
      }
      grouped[dim].push(lot)
    })
    return grouped
  }, [lots, lots_by_dimension])

  return (
    <div className="rounded-3xl border border-border bg-card p-5 shadow-sm animate-fade-in-up">
      {/* 头部 */}
      <div className="mb-4">
        <h3 className="text-lg font-semibold text-center">{"分配你的筹码"}</h3>

        {/* 双人模式提示 */}
        {isDualMode && (
          <div className={cn(
            'rounded-xl px-3 py-2 mt-3 border',
            'bg-amber-soft/50 border-amber/20'
          )}>
            <p className="text-xs text-muted-foreground text-center">
              {"你看不到对方的选择，两人都做完才能看结果"}
            </p>
          </div>
        )}

        {/* 筹码计数器 */}
        <div className="flex justify-center mt-3">
          <div className={cn(
            'px-4 py-2 rounded-full text-sm font-medium',
            isOverBudget && 'bg-destructive/10 text-destructive',
            !isOverBudget && remaining === 0 && 'bg-amber-soft text-amber',
            !isOverBudget && remaining > 0 && 'bg-secondary text-muted-foreground'
          )}>
            {isOverBudget ? (
              <span className="flex items-center gap-1.5">
                <AlertCircle className="w-4 h-4" />
                {"超预算 "}{totalUsed - total_chips}{" 筹码"}
              </span>
            ) : (
              <span>{"剩余 "}{remaining}{" 筹码"}</span>
            )}
          </div>
        </div>
      </div>

      {/* 筹码进度条 */}
      <div className="mb-4">
        <div className="h-2 bg-secondary rounded-full overflow-hidden">
          <div
            className={cn(
              'h-full transition-all duration-300 rounded-full',
              isOverBudget ? 'bg-destructive' : 'bg-amber'
            )}
            style={{ width: `${Math.min(100, (totalUsed / total_chips) * 100)}%` }}
          />
        </div>
      </div>

      {/* 筹码池 - 移动端使用数字+环形进度条 */}
      <div className="hidden sm:flex justify-center gap-1 mb-4">
        {Array.from({ length: total_chips }).map((_, i) => (
          <div
            key={i}
            className={cn(
              'w-4 h-6 rounded-sm transition-all duration-200',
              i < totalUsed
                ? 'bg-amber transform scale-90'
                : 'bg-secondary',
              flyingChips && i >= totalUsed - flyingChips.count && i < totalUsed && 'animate-ping'
            )}
          />
        ))}
      </div>
      
      {/* 移动端筹码显示 */}
      <div className="sm:hidden flex items-center justify-center gap-3 mb-4">
        <div className="relative w-16 h-16">
          <svg className="w-full h-full -rotate-90" viewBox="0 0 36 36">
            <circle
              cx="18"
              cy="18"
              r="15.9"
              fill="none"
              className="stroke-secondary"
              strokeWidth="3"
            />
            <circle
              cx="18"
              cy="18"
              r="15.9"
              fill="none"
              className={cn(
                'transition-all duration-300',
                isOverBudget ? 'stroke-destructive' : 'stroke-amber'
              )}
              strokeWidth="3"
              strokeDasharray={`${(totalUsed / total_chips) * 100} 100`}
              strokeLinecap="round"
            />
          </svg>
          <div className="absolute inset-0 flex items-center justify-center">
            <span className="text-lg font-semibold tabular-nums">{remaining}</span>
          </div>
        </div>
        <div className="text-sm text-muted-foreground">
          {"筹码剩余"}
        </div>
      </div>

      {/* 按维度分组展示拍品 */}
      <div className="space-y-4 max-h-[400px] overflow-y-auto scroll-fade-bottom">
        {Object.entries(lotsGroupedByDimension).map(([dimension, dimensionLots]) => (
          <div key={dimension} className="rounded-2xl bg-secondary/40 p-3 border border-border">
            {/* 维度标题 */}
            <div className="text-sm font-medium text-foreground mb-2 pb-1 border-b border-border/50">
              {DIMENSION_LABELS[dimension as AuctionDimension] || dimensions?.[dimension] || dimension}
            </div>

            {/* 该维度下的拍品 */}
            <div className="space-y-2">
              {dimensionLots.map(lot => (
                <LotBidRow
                  key={lot.lot_id}
                  lot={lot}
                  chips={bids[lot.lot_id]}
                  maxChips={max_bid}
                  remaining={remaining}
                  isFlying={flyingChips?.lotId === lot.lot_id}
                  onChange={delta => handleChipsChange(lot.lot_id, delta)}
                  onSet={value => handleChipsSet(lot.lot_id, value)}
                />
              ))}
            </div>
          </div>
        ))}
      </div>

      {/* 提交按钮 */}
      <button
        onClick={handleSubmit}
        disabled={isOverBudget}
        className={cn(
          'w-full h-12 mt-4 rounded-xl text-base font-medium',
          'transition-all touch-target active:scale-[0.98]',
          isOverBudget
            ? 'bg-secondary text-muted-foreground cursor-not-allowed'
            : 'bg-amber hover:bg-amber/90 text-white'
        )}
      >
        {isOverBudget ? '筹码超预算' : remaining > 0 ? `还有 ${remaining} 筹码未分配` : '封盘揭晓'}
      </button>
    </div>
  )
}

// ============================================================
// 拍品筹码行组件
// ============================================================

type LotBidRowProps = {
  lot: ValuesLot
  chips: number
  maxChips: number
  remaining: number
  isFlying: boolean
  onChange: (delta: number) => void
  onSet: (value: number) => void
}

function LotBidRow({ lot, chips, maxChips, remaining, isFlying, onChange }: LotBidRowProps) {
  const canIncrease = remaining > 0 && chips < maxChips
  const canDecrease = chips > 0

  return (
    <div className={cn(
      'rounded-xl p-3 transition-all',
      chips > 0 ? 'bg-amber-soft/60 border border-amber/30' : 'bg-background border border-border'
    )}>
      <div className="flex items-center justify-between">
        {/* 左侧：拍品信息 */}
        <div className="flex-1 min-w-0">
          <div className="text-sm text-foreground truncate">{lot.title}</div>
        </div>

        {/* 右侧：筹码控制 */}
        <div className="flex items-center gap-2 ml-3">
          {/* 减少按钮 */}
          <button
            onClick={() => onChange(-1)}
            disabled={!canDecrease}
            className={cn(
              'w-7 h-7 rounded-full flex items-center justify-center transition-all touch-target',
              canDecrease 
                ? 'bg-secondary text-foreground hover:bg-secondary/80 active:scale-90' 
                : 'bg-secondary/50 text-muted-foreground/50 cursor-not-allowed'
            )}
          >
            <Minus className="w-4 h-4" />
          </button>

          {/* 筹码显示 */}
          <div className="flex items-center gap-1.5 min-w-[60px] justify-center">
            {/* 筹码可视化 */}
            <div className="flex gap-0.5">
              {Array.from({ length: Math.min(chips, 5) }).map((_, i) => (
                <div
                  key={i}
                  className={cn(
                    'w-2 h-3 bg-amber rounded-sm transition-all',
                    isFlying && 'animate-bounce'
                  )}
                />
              ))}
              {chips > 5 && (
                <span className="text-xs text-amber ml-0.5">+{chips - 5}</span>
              )}
            </div>
            {/* 筹码数字 */}
            <span className={cn(
              'font-semibold text-sm tabular-nums',
              chips >= 4 ? 'text-amber' : chips >= 2 ? 'text-foreground' : 'text-muted-foreground'
            )}>
              {chips}
            </span>
          </div>

          {/* 增加按钮 */}
          <button
            onClick={() => onChange(1)}
            disabled={!canIncrease}
            className={cn(
              'w-7 h-7 rounded-full flex items-center justify-center transition-all touch-target',
              canIncrease 
                ? 'bg-amber text-white hover:bg-amber/90 active:scale-90' 
                : 'bg-secondary/50 text-muted-foreground/50 cursor-not-allowed'
            )}
          >
            <Plus className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* 筹码条（筹码>0时显示） */}
      {chips > 0 && (
        <div
          className="h-1 bg-amber rounded-full mt-2 transition-all duration-300"
          style={{ width: `${(chips / maxChips) * 100}%` }}
        />
      )}
    </div>
  )
}
