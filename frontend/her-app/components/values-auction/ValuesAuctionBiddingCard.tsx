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
import type { ValuesAuctionLotsCard, ValuesLot, AuctionDimension } from '@/lib/api/endpoints/valuesAuction'
import { calculateTotalChips, isValidBidDistribution, DIMENSION_LABELS } from '@/lib/api/endpoints/valuesAuction'
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
  const { lots_data, internal_state } = card
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

  // 按筹码排序的拍品（用于显示）
  const sortedLots = useMemo(() => {
    return [...lots].sort((a, b) => bids[b.lot_id] - bids[a.lot_id])
  }, [lots, bids])

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
    <div className="bg-gradient-to-br from-amber-50 to-orange-50 rounded-2xl p-4 shadow-lg border border-amber-200 animate-fade-in">
      {/* 头部 */}
      <div className="mb-4">
        <h3 className="text-lg font-bold text-amber-900 text-center">分配你的筹码</h3>

        {/* 双人模式提示 */}
        {isDualMode && (
          <div className="bg-orange-100 rounded-lg p-2 mt-2">
            <p className="text-xs text-orange-700 text-center">
              ⚠️ 你看不到对方的选择，两人都做完才能看结果
            </p>
          </div>
        )}

        {/* 筹码计数器 */}
        <div className="flex justify-center mt-3">
          <div className={`px-4 py-2 rounded-full ${isOverBudget ? 'bg-red-100 text-red-700' : remaining === 0 ? 'bg-amber-100 text-amber-700' : 'bg-green-50 text-green-700'}`}>
            <span className="font-medium">
              {isOverBudget ? `超预算 ${totalUsed - total_chips} 筹码` : `剩余 ${remaining} 筹码`}
            </span>
          </div>
        </div>
      </div>

      {/* 筹码进度条 */}
      <div className="mb-4">
        <div className="h-2 bg-amber-100 rounded-full overflow-hidden">
          <div
            className={`h-full transition-all duration-300 ${isOverBudget ? 'bg-red-500' : 'bg-gradient-to-r from-amber-400 to-orange-400'}`}
            style={{ width: `${Math.min(100, (totalUsed / total_chips) * 100)}%` }}
          />
        </div>
      </div>

      {/* 筹码池 */}
      <div className="flex justify-center gap-1 mb-4">
        {Array.from({ length: total_chips }).map((_, i) => (
          <div
            key={i}
            className={`w-4 h-6 rounded-sm transition-all duration-200 ${
              i < totalUsed
                ? 'bg-amber-400 transform scale-90'
                : 'bg-amber-100'
            } ${flyingChips && i >= totalUsed - flyingChips.count && i < totalUsed ? 'animate-ping' : ''}`}
          />
        ))}
      </div>

      {/* 按维度分组展示拍品 */}
      <div className="space-y-4 max-h-[400px] overflow-y-auto">
        {Object.entries(lotsGroupedByDimension).map(([dimension, dimensionLots]) => (
          <div key={dimension} className="bg-white rounded-xl p-3 border border-amber-100">
            {/* 维度标题 */}
            <div className="text-sm font-medium text-amber-800 mb-2 border-b border-amber-50 pb-1">
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
        className={`w-full py-3 mt-4 font-medium rounded-xl shadow-md transition-all ${
          isOverBudget
            ? 'bg-gray-200 text-gray-400 cursor-not-allowed'
            : 'bg-gradient-to-r from-amber-500 to-orange-500 text-white hover:shadow-lg hover:scale-[1.02] active:scale-[0.98]'
        }`}
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

  // 颜色根据筹码量变化
  const chipColor = chips >= 4 ? 'text-orange-600' : chips >= 2 ? 'text-amber-600' : 'text-gray-400'

  return (
    <div className={`rounded-lg p-2 transition-all ${chips > 0 ? 'bg-amber-50 border border-amber-200' : 'bg-gray-50 border border-gray-100'}`}>
      <div className="flex items-center justify-between">
        {/* 左侧：拍品信息 */}
        <div className="flex-1 min-w-0">
          <div className="text-sm text-amber-900 truncate">{lot.title}</div>
        </div>

        {/* 右侧：筹码控制 */}
        <div className="flex items-center gap-2 ml-3">
          {/* 减少按钮 */}
          <button
            onClick={() => onChange(-1)}
            disabled={!canDecrease}
            className={`w-6 h-6 rounded-full flex items-center justify-center transition-all ${
              canDecrease ? 'bg-amber-100 text-amber-700 hover:bg-amber-200 active:scale-90' : 'bg-gray-50 text-gray-300'
            }`}
          >
            −
          </button>

          {/* 筹码显示 */}
          <div className="flex items-center gap-1">
            {/* 筹码可视化 */}
            <div className="flex gap-0.5">
              {Array.from({ length: Math.min(chips, 5) }).map((_, i) => (
                <div
                  key={i}
                  className={`w-2 h-3 bg-amber-400 rounded-sm transition-all ${isFlying ? 'animate-bounce' : ''}`}
                />
              ))}
              {chips > 5 && (
                <div className="text-xs text-amber-500 ml-1">+{chips - 5}</div>
              )}
            </div>
            {/* 筹码数字 */}
            <span className={`font-bold ${chipColor} w-5 text-right text-sm`}>
              {chips}
            </span>
          </div>

          {/* 增加按钮 */}
          <button
            onClick={() => onChange(1)}
            disabled={!canIncrease}
            className={`w-6 h-6 rounded-full flex items-center justify-center transition-all ${
              canIncrease ? 'bg-amber-500 text-white hover:bg-amber-600 active:scale-90' : 'bg-gray-50 text-gray-300'
            }`}
          >
            +
          </button>
        </div>
      </div>

      {/* 筹码条（筹码>0时显示） */}
      {chips > 0 && (
        <div
          className="h-1 bg-gradient-to-r from-amber-400 to-orange-400 rounded-full mt-1 transition-all duration-300"
          style={{ width: `${(chips / maxChips) * 100}%` }}
        />
      )}
    </div>
  )
}