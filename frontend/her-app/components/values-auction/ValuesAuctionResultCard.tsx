/**
 * 价值观拍卖会结果卡片
 *
 * v2.0 更新：
 * - 先展示"你拍下了什么人生"
 * - 再展示隐藏价值分析
 * - 最后展示价值倾向标签
 * - Top3 翻牌揭晓动效
 */

import React, { useState, useEffect } from 'react'
import type { ValuesAuctionResultCard } from '@/lib/api/endpoints/valuesAuction'
import { HIDDEN_VALUE_LABELS } from '@/lib/api/endpoints/valuesAuction'

type Props = {
  card: ValuesAuctionResultCard
  onViewInterpretation?: () => void
  onShare?: () => void
  onContinue?: () => void
}

export function ValuesAuctionResultCardComponent({ card, onViewInterpretation, onShare, onContinue }: Props) {
  const { result_data } = card
  const { bids, hidden_values, top_hidden_values, value_type, value_labels, top3, abandoned, reward } = result_data

  // 翻牌动效状态
  const [revealedCount, setRevealedCount] = useState(0)

  // 自动翻牌
  useEffect(() => {
    if (revealedCount < 3) {
      const timer = setTimeout(() => {
        setRevealedCount(prev => prev + 1)
      }, 400)
      return () => clearTimeout(timer)
    }
  }, [revealedCount])

  // 根据价值观类型选择颜色
  const typeColor = getTypeColor(value_type)

  // 构建隐藏价值解读
  const hiddenValueSummary = top_hidden_values && top_hidden_values.length > 0
    ? `底层真正强势的是：${top_hidden_values.map(hv => HIDDEN_VALUE_LABELS[hv.key] || hv.key).join('、')}`
    : ''

  return (
    <div className="bg-gradient-to-br from-amber-50 to-orange-50 rounded-2xl p-6 shadow-lg border border-amber-200 animate-fade-in">
      {/* 标题 */}
      <div className="text-center mb-6">
        <div className="text-4xl mb-2 animate-scale-in">
          🎉
        </div>
        <h2 className="text-xl font-bold text-amber-900">拍卖完成！</h2>
      </div>

      {/* 你拍下了什么人生 */}
      <div className="mb-6 bg-white rounded-xl p-4 border border-amber-100 shadow-sm">
        <h3 className="text-sm font-medium text-amber-700 mb-3">你拍下了这些人生</h3>
        <div className="space-y-3">
          {top3.slice(0, revealedCount).map((lot, i) => (
            <div
              key={lot.lot_id}
              className="bg-amber-50 rounded-xl p-3 border border-amber-200 animate-slide-in"
              style={{ animationDelay: `${i * 100}ms` }}
            >
              <div className="flex items-center gap-3">
                {/* 排名 */}
                <div className={`w-8 h-8 rounded-full flex items-center justify-center font-bold ${
                  i === 0 ? 'bg-amber-400 text-white' : i === 1 ? 'bg-amber-200 text-amber-700' : 'bg-amber-100 text-amber-600'
                }`}>
                  {i + 1}
                </div>
                {/* 拍品信息 */}
                <div className="flex-1">
                  <div className="font-medium text-amber-900 text-sm">{lot.title}</div>
                  {lot.interpretation && (
                    <div className="text-xs text-amber-600 mt-1">{lot.interpretation}</div>
                  )}
                </div>
                {/* 筹码数 */}
                <div className="text-2xl font-bold text-orange-500">
                  {lot.chips}
                </div>
              </div>
            </div>
          ))}
          {/* 正在揭晓的拍品 */}
          {revealedCount < 3 && top3[revealedCount] && (
            <div className="bg-gray-100 rounded-xl p-3 border border-gray-200 animate-pulse">
              <div className="flex items-center gap-3">
                <div className="w-8 h-8 rounded-full flex items-center justify-center font-bold bg-gray-300 text-gray-500">
                  {revealedCount + 1}
                </div>
                <div className="flex-1 text-gray-400">
                  正在揭晓...
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* 隐藏价值分析 */}
      {hidden_values && top_hidden_values && top_hidden_values.length > 0 && (
        <div className="mb-6 bg-purple-50 rounded-xl p-4 border border-purple-100 animate-fade-in">
          <h4 className="text-sm font-medium text-purple-700 mb-2">底层价值分析</h4>
          <div className="space-y-2">
            {top_hidden_values.slice(0, 3).map(hv => (
              <div key={hv.key} className="flex items-center gap-2">
                <div className="text-sm text-purple-900">
                  {HIDDEN_VALUE_LABELS[hv.key] || hv.key}
                </div>
                <div className="flex-1">
                  <div className="h-2 bg-purple-100 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-gradient-to-r from-purple-400 to-purple-500 rounded-full"
                      style={{ width: `${hv.weight * 100}%` }}
                    />
                  </div>
                </div>
                <div className="text-sm text-purple-600 font-medium">
                  {Math.round(hv.weight * 100)}%
                </div>
              </div>
            ))}
          </div>
          <p className="text-xs text-purple-600 mt-2">
            {hiddenValueSummary}
          </p>
        </div>
      )}

      {/* 价值观类型标签 */}
      <div className={`text-center mb-4 p-3 rounded-xl ${typeColor.bg} animate-fade-in`}>
        <div className={`text-sm font-bold ${typeColor.text}`}>{value_type}</div>
        <div className="flex justify-center gap-1 mt-1">
          {value_labels.map((label, i) => (
            <span key={i} className={`px-2 py-0.5 rounded-full text-xs ${typeColor.tagBg} ${typeColor.tagText}`}>
              {label}
            </span>
          ))}
        </div>
      </div>

      {/* 放弃的拍品 */}
      {abandoned.length > 0 && (
        <div className="mb-4 bg-gray-50 rounded-lg p-3 animate-fade-in">
          <h4 className="text-xs text-gray-500 mb-2">你主动放弃了</h4>
          <div className="text-xs text-gray-400">
            {abandoned.slice(0, 5).join('、')}
            {abandoned.length > 5 && ` 等${abandoned.length}项`}
          </div>
        </div>
      )}

      {/* 奖励提示 */}
      {reward && (
        <div className="bg-green-50 rounded-lg p-3 mb-4 text-center animate-fade-in">
          <span className="text-green-600 text-sm">✨ {reward}</span>
        </div>
      )}

      {/* 操作按钮 */}
      <div className="flex gap-3">
        {onViewInterpretation && (
          <button
            onClick={onViewInterpretation}
            className="flex-1 py-3 bg-gradient-to-r from-amber-500 to-orange-500 text-white font-medium rounded-xl shadow-md hover:shadow-lg transition-all hover:scale-[1.02] active:scale-[0.98]"
          >
            查看AI解读
          </button>
        )}
        {onShare && (
          <button
            onClick={onShare}
            className="px-4 py-3 bg-white border border-amber-200 text-amber-700 font-medium rounded-xl hover:bg-amber-50 transition-all"
          >
            分享
          </button>
        )}
        {onContinue && (
          <button
            onClick={onContinue}
            className="px-4 py-3 bg-gray-100 text-gray-600 font-medium rounded-xl hover:bg-gray-200 transition-all"
          >
            继续
          </button>
        )}
      </div>
    </div>
  )
}

// ============================================================
// 辅助函数
// ============================================================

function getTypeColor(valueType: string) {
  if (valueType.includes('安全感') || valueType.includes('安全')) {
    return { bg: 'bg-blue-50', text: 'text-blue-700', tagBg: 'bg-blue-100', tagText: 'text-blue-600' }
  } else if (valueType.includes('自由')) {
    return { bg: 'bg-green-50', text: 'text-green-700', tagBg: 'bg-green-100', tagText: 'text-green-600' }
  } else if (valueType.includes('情感') || valueType.includes('连接')) {
    return { bg: 'bg-pink-50', text: 'text-pink-700', tagBg: 'bg-pink-100', tagText: 'text-pink-600' }
  } else if (valueType.includes('成就') || valueType.includes('物质')) {
    return { bg: 'bg-yellow-50', text: 'text-yellow-700', tagBg: 'bg-yellow-100', tagText: 'text-yellow-600' }
  } else if (valueType.includes('利他') || valueType.includes('奉献')) {
    return { bg: 'bg-purple-50', text: 'text-purple-700', tagBg: 'bg-purple-100', tagText: 'text-purple-600' }
  } else if (valueType.includes('意义') || valueType.includes('平静')) {
    return { bg: 'bg-indigo-50', text: 'text-indigo-700', tagBg: 'bg-indigo-100', tagText: 'text-indigo-600' }
  } else {
    return { bg: 'bg-amber-50', text: 'text-amber-700', tagBg: 'bg-amber-100', tagText: 'text-amber-600' }
  }
}