/**
 * 价值观拍卖会介绍卡片
 */

import React from 'react'
import type { ValuesAuctionIntroCard } from '@/lib/api/endpoints/valuesAuction'

type Props = {
  card: ValuesAuctionIntroCard
  onStart: () => void
}

export function ValuesAuctionIntroCardComponent({ card, onStart }: Props) {
  const { intro_data } = card

  return (
    <div className="bg-gradient-to-br from-amber-50 to-orange-50 rounded-2xl p-6 shadow-lg border border-amber-200 animate-fade-in">
      {/* 标题 */}
      <div className="text-center mb-6">
        <div className="text-4xl mb-2 animate-scale-in">
          💰
        </div>
        <h2 className="text-xl font-bold text-amber-900">{intro_data.title}</h2>
        <p className="text-amber-700 mt-2 text-sm">{intro_data.description}</p>
      </div>

      {/* 信息卡片 */}
      <div className="bg-white/60 rounded-xl p-4 mb-4">
        <div className="grid grid-cols-2 gap-4 text-sm">
          <div className="flex items-center gap-2">
            <span className="text-amber-500">⏱</span>
            <span className="text-amber-800">{intro_data.duration}</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-amber-500">🎯</span>
            <span className="text-amber-800">{intro_data.trait_count}个特质</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-amber-500">💎</span>
            <span className="text-amber-800">{intro_data.total_chips}个筹码</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-amber-500">🎁</span>
            <span className="text-amber-800">{intro_data.reward}</span>
          </div>
        </div>
      </div>

      {/* 规则说明 */}
      <div className="bg-amber-100/50 rounded-lg p-3 mb-4">
        <p className="text-xs text-amber-700 text-center">
          你有10个筹码，用来竞拍你最看重的特质。<br />
          筹码不够，必须取舍——就像真实人生。
        </p>
      </div>

      {/* 开始按钮 */}
      <button
        onClick={onStart}
        className="w-full py-3 bg-gradient-to-r from-amber-500 to-orange-500 text-white font-medium rounded-xl shadow-md hover:shadow-lg transition-all hover:scale-[1.02] active:scale-[0.98]"
      >
        开始拍卖
      </button>
    </div>
  )
}