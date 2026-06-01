/**
 * 价值观拍卖会AI解读卡片
 */

import React from 'react'
import type { ValuesAuctionInterpretationCard } from '@/lib/api/endpoints/valuesAuction'

type Props = {
  card: ValuesAuctionInterpretationCard
  onContinue?: () => void
}

export function ValuesAuctionInterpretationCardComponent({ card, onContinue }: Props) {
  const { interpretation_data } = card
  const { summary, love_style, match_suggestions, caution_traits, top3_analysis } = interpretation_data

  return (
    <div className="bg-gradient-to-br from-purple-50 to-indigo-50 rounded-2xl p-6 shadow-lg border border-purple-200 animate-fade-in">
      {/* 标题 */}
      <div className="text-center mb-6">
        <div className="text-4xl mb-2 animate-scale-in">
          🤖
        </div>
        <h2 className="text-xl font-bold text-purple-900">AI 价值观解读</h2>
      </div>

      {/* 概述 */}
      <div className="bg-white rounded-xl p-4 mb-4 shadow-sm animate-fade-in">
        <div className="text-purple-800 font-medium mb-2">📋 价值观画像</div>
        <p className="text-purple-700 text-sm leading-relaxed">{summary}</p>
      </div>

      {/* 恋爱风格 */}
      <div className="bg-white rounded-xl p-4 mb-4 shadow-sm animate-fade-in">
        <div className="text-purple-800 font-medium mb-2">💕 恋爱风格</div>
        <p className="text-purple-700 text-sm leading-relaxed">{love_style}</p>
      </div>

      {/* Top3 分析 */}
      {top3_analysis && top3_analysis.length > 0 && (
        <div className="bg-purple-50 rounded-xl p-4 mb-4 animate-fade-in">
          <div className="text-purple-800 font-medium mb-3">📊 你的TOP3特质分析</div>
          <div className="space-y-2">
            {top3_analysis.map((trait, i) => (
              <div key={i} className="bg-white rounded-lg p-3">
                <div className="flex items-center justify-between">
                  <span className="font-medium text-purple-900">{trait.trait_name}</span>
                  <span className="text-purple-500 font-bold">{trait.chips}筹码</span>
                </div>
                <p className="text-purple-600 text-xs mt-1">{trait.interpretation}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 匹配建议 */}
      {match_suggestions && match_suggestions.length > 0 && (
        <div className="bg-green-50 rounded-xl p-4 mb-4 animate-fade-in">
          <div className="text-green-800 font-medium mb-2">💡 匹配建议</div>
          <div className="space-y-2">
            {match_suggestions.map((suggestion, i) => (
              <div key={i} className="text-green-700 text-sm flex items-start gap-2">
                <span className="text-green-500">•</span>
                <span>{suggestion}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 注意事项 */}
      {caution_traits && caution_traits.length > 0 && (
        <div className="bg-orange-50 rounded-xl p-4 mb-4 animate-fade-in">
          <div className="text-orange-800 font-medium mb-2">⚠️ 需要注意</div>
          <div className="space-y-2">
            {caution_traits.map((caution, i) => (
              <div key={i} className="text-orange-700 text-sm flex items-start gap-2">
                <span className="text-orange-500">•</span>
                <span>{caution}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 继续按钮 */}
      {onContinue && (
        <button
          onClick={onContinue}
          className="w-full py-3 bg-gradient-to-r from-purple-500 to-indigo-500 text-white font-medium rounded-xl shadow-md hover:shadow-lg transition-all hover:scale-[1.02] active:scale-[0.98]"
        >
          继续聊天
        </button>
      )}
    </div>
  )
}