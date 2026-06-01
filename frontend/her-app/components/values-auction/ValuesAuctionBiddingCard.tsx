/**
 * 价值观拍卖会竞拍交互卡片
 *
 * 用户在此卡片中分配筹码到各个特质。
 */

import React, { useState, useMemo } from 'react'
import type { ValuesAuctionTraitsCard, ValuesTrait } from '@/lib/api/endpoints/valuesAuction'
import { calculateTotalChips, isValidBidDistribution } from '@/lib/api/endpoints/valuesAuction'

type Props = {
  card: ValuesAuctionTraitsCard
  onSubmit: (bids: Array<{ trait_id: string; chips: number }>) => void
  isDualMode?: boolean
}

export function ValuesAuctionBiddingCard({ card, onSubmit, isDualMode }: Props) {
  const { traits_data, internal_state } = card
  const { traits, total_chips, min_bid, max_bid } = traits_data

  // 筹码分配状态
  const [bids, setBids] = useState<Record<string, number>>(() => {
    // 初始化：所有特质都是0筹码
    const initial: Record<string, number> = {}
    traits.forEach(t => {
      initial[t.trait_id] = 0
    })
    return initial
  })

  // 计算总筹码
  const totalUsed = useMemo(() => calculateTotalChips(bids), [bids])
  const remaining = total_chips - totalUsed
  const isOverBudget = totalUsed > total_chips

  // 调整筹码
  const handleChipsChange = (traitId: string, delta: number) => {
    const newValue = Math.max(min_bid, Math.min(max_bid, bids[traitId] + delta))
    // 检查是否会超预算
    const newTotal = totalUsed - bids[traitId] + newValue
    if (newTotal <= total_chips) {
      setBids(prev => ({ ...prev, [traitId]: newValue }))
    }
  }

  // 直接设置筹码（用于滑块）
  const handleChipsSet = (traitId: string, value: number) => {
    const newValue = Math.max(min_bid, Math.min(max_bid, value))
    // 检查是否会超预算
    const newTotal = totalUsed - bids[traitId] + newValue
    if (newTotal <= total_chips) {
      setBids(prev => ({ ...prev, [traitId]: newValue }))
    }
  }

  // 提交
  const handleSubmit = () => {
    if (isOverBudget) return

    // 转换为数组格式
    const bidsArray = Object.entries(bids)
      .map(([trait_id, chips]) => ({ trait_id, chips }))
      .filter(b => b.chips >= 0)  // 包含0筹码的，用于排序

    onSubmit(bidsArray)
  }

  // 按筹码排序的特质（用于显示）
  const sortedTraits = useMemo(() => {
    return [...traits].sort((a, b) => bids[b.trait_id] - bids[a.trait_id])
  }, [traits, bids])

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

      {/* 特质列表 */}
      <div className="space-y-2 max-h-[400px] overflow-y-auto">
        {traits.map(trait => (
          <TraitBidRow
            key={trait.trait_id}
            trait={trait}
            chips={bids[trait.trait_id]}
            maxChips={max_bid}
            remaining={remaining}
            onChange={delta => handleChipsChange(trait.trait_id, delta)}
            onSet={value => handleChipsSet(trait.trait_id, value)}
          />
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
        {isOverBudget ? '筹码超预算' : remaining > 0 ? `还有 ${remaining} 筹码未分配` : '确认分配'}
      </button>
    </div>
  )
}

// ============================================================
// 特质筹码行组件
// ============================================================

type TraitBidRowProps = {
  trait: ValuesTrait
  chips: number
  maxChips: number
  remaining: number
  onChange: (delta: number) => void
  onSet: (value: number) => void
}

function TraitBidRow({ trait, chips, maxChips, remaining, onChange, onSet }: TraitBidRowProps) {
  const canIncrease = remaining > 0 && chips < maxChips
  const canDecrease = chips > 0

  // 颜色根据筹码量变化
  const chipColor = chips >= 4 ? 'text-orange-600' : chips >= 2 ? 'text-amber-600' : 'text-gray-400'

  return (
    <div className={`bg-white rounded-xl p-3 border transition-all ${chips > 0 ? 'border-amber-200 shadow-sm' : 'border-gray-100'}`}>
      <div className="flex items-center justify-between">
        {/* 左侧：特质信息 */}
        <div className="flex-1 min-w-0">
          <div className="font-medium text-amber-900 truncate">{trait.trait_name}</div>
          <div className="text-xs text-amber-600 truncate">{trait.description}</div>
        </div>

        {/* 右侧：筹码控制 */}
        <div className="flex items-center gap-2 ml-3">
          {/* 减少按钮 */}
          <button
            onClick={() => onChange(-1)}
            disabled={!canDecrease}
            className={`w-8 h-8 rounded-full flex items-center justify-center transition-all ${
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
                  className="w-2 h-4 bg-amber-400 rounded-sm animate-scale-in"
                />
              ))}
              {chips > 5 && (
                <div className="text-xs text-amber-500 ml-1">+{chips - 5}</div>
              )}
            </div>
            {/* 筹码数字 */}
            <span className={`font-bold ${chipColor} w-6 text-right`}>
              {chips}
            </span>
          </div>

          {/* 增加按钮 */}
          <button
            onClick={() => onChange(1)}
            disabled={!canIncrease}
            className={`w-8 h-8 rounded-full flex items-center justify-center transition-all ${
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
          className="h-1 bg-gradient-to-r from-amber-400 to-orange-400 rounded-full mt-2 transition-all duration-300"
          style={{ width: `${(chips / maxChips) * 100}%` }}
        />
      )}
    </div>
  )
}