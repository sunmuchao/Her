/**
 * 价值观拍卖会匹配分析卡片
 *
 * 双人都完成拍卖后显示的三观契合度分析。
 */

import React from 'react'
import type { ValuesMatchAnalysisCard } from '@/lib/api/endpoints/valuesAuction'

type Props = {
  card: ValuesMatchAnalysisCard
  onContinue?: () => void
  currentUserKey?: string  // 当前用户的key，用于区分"你"和"对方"
}

export function ValuesMatchAnalysisCardComponent({ card, onContinue, currentUserKey }: Props) {
  const { match_data } = card
  const { user1, user2, match_type, top3_common, conflicts, ai_interpretation } = match_data

  // 判断当前用户是 user1 还是 user2
  const isUser1 = currentUserKey === user1.user_key
  const currentUser = isUser1 ? user1 : user2
  const partnerUser = isUser1 ? user2 : user1

  // 匹配类型颜色
  const matchColor = getMatchColor(match_type)

  return (
    <div className="bg-gradient-to-br from-pink-50 to-purple-50 rounded-2xl p-6 shadow-lg border border-pink-200 animate-fade-in">
      {/* 标题 */}
      <div className="text-center mb-6">
        <div className="text-4xl mb-2 animate-scale-in">
          🤝
        </div>
        <h2 className="text-xl font-bold text-pink-900">三观契合度分析</h2>
      </div>

      {/* 匹配类型 */}
      <div className={`text-center mb-6 p-4 rounded-xl ${matchColor.bg} animate-fade-in`}>
        <div className={`text-lg font-bold ${matchColor.text}`}>{match_type}</div>
      </div>

      {/* 双方对比 */}
      <div className="grid grid-cols-2 gap-4 mb-6">
        {/* 当前用户 */}
        <div className="bg-white rounded-xl p-4 shadow-sm animate-slide-in-left">
          <div className="text-center mb-3">
            <div className="text-sm text-gray-500">你</div>
            <div className="font-bold text-pink-700">{currentUser.value_type}</div>
          </div>
          <div className="space-y-2">
            {currentUser.top3.slice(0, 3).map((trait, i) => (
              <div key={i} className="flex items-center justify-between text-xs">
                <span className="text-pink-700">{trait.trait_name}</span>
                <span className="text-pink-500 font-medium">{trait.chips}筹码</span>
              </div>
            ))}
          </div>
        </div>

        {/* 对方 */}
        <div className="bg-white rounded-xl p-4 shadow-sm animate-slide-in-right">
          <div className="text-center mb-3">
            <div className="text-sm text-gray-500">对方</div>
            <div className="font-bold text-purple-700">{partnerUser.value_type}</div>
          </div>
          <div className="space-y-2">
            {partnerUser.top3.slice(0, 3).map((trait, i) => (
              <div key={i} className="flex items-center justify-between text-xs">
                <span className="text-purple-700">{trait.trait_name}</span>
                <span className="text-purple-500 font-medium">{trait.chips}筹码</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* 共鸣点 */}
      {top3_common.length > 0 && (
        <div className="bg-green-50 rounded-xl p-4 mb-4 animate-fade-in">
          <div className="text-green-800 font-medium mb-2">✨ 共鸣点</div>
          <div className="text-green-700 text-sm">
            你们都看重：<strong>{top3_common.join('、')}</strong>
          </div>
        </div>
      )}

      {/* 差异点/冲突 */}
      {conflicts.length > 0 && (
        <div className="bg-orange-50 rounded-xl p-4 mb-4 animate-fade-in">
          <div className="text-orange-800 font-medium mb-2">⚠️ 需要磨合</div>
          <div className="space-y-2">
            {conflicts.map((conflict, i) => (
              <div key={i} className="text-orange-700 text-sm">
                <div className="font-medium">{conflict.description}</div>
                <div className="text-xs text-orange-600 mt-1">💡 {conflict.suggestion}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* AI解读 */}
      <div className="bg-purple-50 rounded-xl p-4 mb-4 animate-fade-in">
        <div className="text-purple-800 font-medium mb-2">🤖 AI 相处建议</div>
        <div className="text-purple-700 text-sm leading-relaxed whitespace-pre-line">
          {ai_interpretation}
        </div>
      </div>

      {/* 继续按钮 */}
      {onContinue && (
        <button
          onClick={onContinue}
          className="w-full py-3 bg-gradient-to-r from-pink-500 to-purple-500 text-white font-medium rounded-xl shadow-md hover:shadow-lg transition-all hover:scale-[1.02] active:scale-[0.98]"
        >
          继续聊天
        </button>
      )}
    </div>
  )
}

// ============================================================
// 辅助函数
// ============================================================

function getMatchColor(matchType: string) {
  if (matchType === '高度契合') {
    return { bg: 'bg-green-50', text: 'text-green-700' }
  } else if (matchType === '中等契合') {
    return { bg: 'bg-blue-50', text: 'text-blue-700' }
  } else if (matchType === '需要磨合') {
    return { bg: 'bg-orange-50', text: 'text-orange-700' }
  } else {
    return { bg: 'bg-gray-50', text: 'text-gray-700' }
  }
}