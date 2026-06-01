/**
 * 价值观拍卖会结果卡片
 *
 * 显示用户的价值观排序、类型标签和Top3特质解读。
 */

import React from 'react'
import type { ValuesAuctionResultCard } from '@/lib/api/endpoints/valuesAuction'

type Props = {
  card: ValuesAuctionResultCard
  onViewInterpretation?: () => void
  onShare?: () => void
  onContinue?: () => void
}

export function ValuesAuctionResultCardComponent({ card, onViewInterpretation, onShare, onContinue }: Props) {
  const { result_data } = card
  const { bids, value_type, value_labels, top3, abandoned, reward } = result_data

  // 根据价值观类型选择颜色
  const typeColor = getTypeColor(value_type)

  return (
    <div className="bg-gradient-to-br from-amber-50 to-orange-50 rounded-2xl p-6 shadow-lg border border-amber-200 animate-fade-in">
      {/* 标题 */}
      <div className="text-center mb-6">
        <div className="text-4xl mb-2 animate-scale-in">
          🎉
        </div>
        <h2 className="text-xl font-bold text-amber-900">拍卖完成！</h2>
      </div>

      {/* 价值观类型标签 */}
      <div className={`text-center mb-6 p-4 rounded-xl ${typeColor.bg} animate-fade-in`}>
        <div className={`text-lg font-bold ${typeColor.text}`}>{value_type}</div>
        <div className="flex justify-center gap-2 mt-2">
          {value_labels.map((label, i) => (
            <span key={i} className={`px-2 py-1 rounded-full text-xs ${typeColor.tagBg} ${typeColor.tagText}`}>
              {label}
            </span>
          ))}
        </div>
      </div>

      {/* Top3 特质 */}
      <div className="mb-6">
        <h3 className="text-sm font-medium text-amber-700 mb-3">你最看重的特质</h3>
        <div className="space-y-3">
          {top3.map((trait, i) => (
            <div
              key={trait.trait_id}
              className="bg-white rounded-xl p-3 border border-amber-100 shadow-sm animate-slide-in"
              style={{ animationDelay: `${i * 100}ms` }}
            >
              <div className="flex items-center gap-3">
                {/* 排名 */}
                <div className={`w-8 h-8 rounded-full flex items-center justify-center font-bold ${
                  i === 0 ? 'bg-amber-400 text-white' : i === 1 ? 'bg-amber-200 text-amber-700' : 'bg-amber-100 text-amber-600'
                }`}>
                  {i + 1}
                </div>
                {/* 特质信息 */}
                <div className="flex-1">
                  <div className="font-medium text-amber-900">{trait.trait_name}</div>
                  <div className="text-xs text-amber-600 mt-1">{trait.interpretation}</div>
                </div>
                {/* 筹码数 */}
                <div className="text-2xl font-bold text-orange-500">
                  {trait.chips}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* 放弃的特质 */}
      {abandoned.length > 0 && (
        <div className="mb-6 bg-gray-50 rounded-lg p-3 animate-fade-in">
          <h4 className="text-xs text-gray-500 mb-2">你放弃的特质</h4>
          <div className="text-xs text-gray-400">
            {abandoned.join('、')}
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
  if (valueType === '忠诚至上型') {
    return { bg: 'bg-red-50', text: 'text-red-700', tagBg: 'bg-red-100', tagText: 'text-red-600' }
  } else if (valueType === '务实型') {
    return { bg: 'bg-blue-50', text: 'text-blue-700', tagBg: 'bg-blue-100', tagText: 'text-blue-600' }
  } else if (valueType === '颜值优先型') {
    return { bg: 'bg-pink-50', text: 'text-pink-700', tagBg: 'bg-pink-100', tagText: 'text-pink-600' }
  } else if (valueType === '情绪价值型') {
    return { bg: 'bg-yellow-50', text: 'text-yellow-700', tagBg: 'bg-yellow-100', tagText: 'text-yellow-600' }
  } else if (valueType === '成长型') {
    return { bg: 'bg-green-50', text: 'text-green-700', tagBg: 'bg-green-100', tagText: 'text-green-600' }
  } else if (valueType === '陪伴型') {
    return { bg: 'bg-purple-50', text: 'text-purple-700', tagBg: 'bg-purple-100', tagText: 'text-purple-600' }
  } else {
    return { bg: 'bg-amber-50', text: 'text-amber-700', tagBg: 'bg-amber-100', tagText: 'text-amber-600' }
  }
}