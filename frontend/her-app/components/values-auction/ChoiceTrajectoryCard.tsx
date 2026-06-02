/**
 * 取舍轨迹回顾卡片
 *
 * v3.0 游戏化改进版：
 * - 展示用户的取舍轨迹（每一步的选择）
 * - 先展示"放弃"（强化取舍感）
 * - 再展示"保留"（强化获得感）
 * - 最后归纳价值观类型（强化洞察感）
 */

import React, { useMemo } from 'react'
import type { ValuesAuctionResultCard, ValuesLot } from '@/lib/api/endpoints/valuesAuction'

type Props = {
  card: ValuesAuctionResultCard
  lots: ValuesLot[]  // 所有拍品列表（用于获取详细信息）
  onContinue?: () => void
}

export function ChoiceTrajectoryCard({ card, lots, onContinue }: Props) {
  const { result_data } = card
  const { bids, value_type, top3, abandoned } = result_data

  // 构建取舍轨迹（按出价排序）
  const choiceTrajectory = useMemo(() => {
    // 按筹码排序：保留的（有筹码）> 放弃的（无筹码）
    const sortedBids = [...bids].sort((a, b) => b.chips - a.chips)

    return sortedBids.map((bid, index) => {
      const lot = lots.find(l => l.lot_id === bid.lot_id)
      const isKept = bid.chips > 0

      return {
        index: index + 1,
        lot_id: bid.lot_id,
        title: lot?.title || bid.title,
        icon: lot?.icon || '💰',
        theme_color: lot?.theme_color || '#F59E0B',
        interpretation: lot?.interpretation || '',
        conflict_hint: lot?.conflict_hint || '',
        choice: isKept ? 'keep' : 'discard',
        chips: bid.chips,
        rank: bid.rank,
      }
    })
  }, [bids, lots])

  // 分离保留的和放弃的
  const keptChoices = useMemo(() =>
    choiceTrajectory.filter(c => c.choice === 'keep'),
    [choiceTrajectory]
  )

  const discardedChoices = useMemo(() =>
    choiceTrajectory.filter(c => c.choice === 'discard'),
    [choiceTrajectory]
  )

  return (
    <div className="bg-gradient-to-br from-amber-50 to-orange-50 rounded-2xl p-6 shadow-lg border border-amber-200">
      {/* 标题 */}
      <div className="text-center mb-6">
        <h3 className="text-xl font-bold text-amber-900 mb-2">你的取舍回顾</h3>
        <p className="text-sm text-amber-600">看看你每一步的选择</p>
      </div>

      {/* 第一幕：你放弃了什么 */}
      <div className="mb-6">
        <div className="bg-gray-50 rounded-xl p-4 border border-gray-200">
          <div className="text-sm font-medium text-gray-700 mb-3">
            你放弃了 {discardedChoices.length} 个拍品：
          </div>

          <div className="space-y-2">
            {discardedChoices.map((choice, i) => (
              <div
                key={choice.lot_id}
                className="flex items-center gap-3 bg-white rounded-lg p-2 border border-gray-100 opacity-60"
              >
                <div className="text-2xl">{choice.icon}</div>
                <div className="flex-1">
                  <div className="text-sm text-gray-700">{choice.title}</div>
                  {choice.interpretation && (
                    <div className="text-xs text-gray-500 italic">{choice.interpretation}</div>
                  )}
                </div>
                <div className="text-lg text-gray-400">⚫</div>
              </div>
            ))}
          </div>

          {/* 放弃的含义 */}
          <div className="mt-3 pt-3 border-t border-gray-200">
            <p className="text-xs text-gray-600 text-center">
              这意味着你不在乎这些人生选项
            </p>
          </div>
        </div>
      </div>

      {/* 第二幕：你保留了什么 */}
      <div className="mb-6">
        <div className="bg-amber-50 rounded-xl p-4 border border-amber-200">
          <div className="text-sm font-medium text-amber-700 mb-3">
            你保留了 {keptChoices.length} 个拍品：
          </div>

          <div className="space-y-3">
            {keptChoices.map((choice, i) => (
              <div
                key={choice.lot_id}
                className="flex items-center gap-3 bg-white rounded-lg p-3 border-2 transition-all hover:shadow-md"
                style={{ borderColor: choice.theme_color }}
              >
                <div className="text-3xl">{choice.icon}</div>
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-1">
                    <div className="text-sm font-bold text-amber-900">
                      第 {choice.rank} 名：{choice.title}
                    </div>
                    <div className="px-2 py-0.5 bg-amber-100 rounded text-xs text-amber-700">
                      {choice.chips} 筹码
                    </div>
                  </div>
                  {choice.interpretation && (
                    <div className="text-xs text-amber-600 italic">{choice.interpretation}</div>
                  )}
                </div>
                <div className="text-lg text-amber-500">✓</div>
              </div>
            ))}
          </div>

          {/* 保留的含义 */}
          <div className="mt-3 pt-3 border-t border-amber-200">
            <p className="text-xs text-amber-700 text-center font-medium">
              这些是你真正想要的人生
            </p>
          </div>
        </div>
      </div>

      {/* 第三幕：价值观总结 */}
      <div className="mb-6">
        <div className="bg-gradient-to-r from-amber-100 to-orange-100 rounded-xl p-4 border border-amber-300 shadow-md">
          <div className="text-center mb-3">
            <div className="text-lg font-bold text-amber-900 mb-1">
              你的价值观类型：{value_type}
            </div>
          </div>

          {/* Top3 归纳 */}
          <div className="mb-3">
            <div className="text-sm text-amber-800 mb-2">你最看重的是：</div>
            {top3.map((item, i) => (
              <div key={item.lot_id} className="text-sm text-amber-700 mb-1">
                {i + 1}. {item.title} — {item.interpretation}
              </div>
            ))}
          </div>

          {/* 底层价值 */}
          {result_data.hidden_values && (
            <div className="mt-3 pt-3 border-t border-amber-200">
              <div className="text-xs text-amber-700 mb-2">你底层真正想要的是：</div>
              <div className="flex flex-wrap gap-2 justify-center">
                {Object.entries(result_data.hidden_values)
                  .sort(([, a], [, b]) => (b as number) - (a as number))
                  .slice(0, 3)
                  .map(([key, weight]) => (
                    <div
                      key={key}
                      className="px-3 py-1 bg-white rounded-lg text-xs text-amber-700 border border-amber-200"
                    >
                      {key}: {Math.round((weight as number) * 100)}%
                    </div>
                  ))}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* 继续按钮 */}
      {onContinue && (
        <button
          onClick={onContinue}
          className="w-full py-3 bg-gradient-to-r from-amber-500 to-orange-500 text-white font-medium rounded-xl shadow-md hover:shadow-lg hover:scale-[1.02] active:scale-[0.98] transition-all"
        >
          查看详细解读
        </button>
      )}
    </div>
  )
}