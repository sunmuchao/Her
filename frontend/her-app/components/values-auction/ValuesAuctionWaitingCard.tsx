/**
 * 价值观拍卖会等待对方卡片
 *
 * 用户完成拍卖后，等待对方完成时显示。
 */

import React, { useEffect, useState } from 'react'
import type { ValuesAuctionWaitingCard } from '@/lib/api/endpoints/valuesAuction'
import { checkValuesAuctionStatus } from '@/lib/api/endpoints/valuesAuction'

type Props = {
  card: ValuesAuctionWaitingCard
  userKey: string
  onMatchReady: (matchCard: any) => void
  onContinueChat?: () => void
}

export function ValuesAuctionWaitingCard({ card, userKey, onMatchReady, onContinueChat }: Props) {
  const { waiting_data, session_id } = card
  const { message, your_result, partner_status } = waiting_data

  const [isPolling, setIsPolling] = useState(true)
  const [countdown, setCountdown] = useState(3)

  // 轮询检查状态
  useEffect(() => {
    if (!isPolling) return

    const pollInterval = setInterval(async () => {
      try {
        const result = await checkValuesAuctionStatus({
          sessionId: session_id,
          userKey: userKey,
        })

        if (result.status === 'both_done' && result.card_type === 'values_match_analysis') {
          setIsPolling(false)
          onMatchReady(result)
        }
      } catch (error) {
        console.error('Poll error:', error)
      }
    }, 3000) // 每3秒轮询

    return () => clearInterval(pollInterval)
  }, [isPolling, session_id, userKey, onMatchReady])

  // 倒计时动画
  useEffect(() => {
    if (!isPolling) return

    const timer = setInterval(() => {
      setCountdown(prev => prev > 0 ? prev - 1 : 3)
    }, 1000)

    return () => clearInterval(timer)
  }, [isPolling])

  return (
    <div className="bg-gradient-to-br from-blue-50 to-indigo-50 rounded-2xl p-6 shadow-lg border border-blue-200 animate-fade-in">
      {/* 标题 */}
      <div className="text-center mb-6">
        <div className="text-4xl mb-2 animate-spin-slow">
          ⏳
        </div>
        <h2 className="text-xl font-bold text-blue-900">{message}</h2>
        <p className="text-blue-600 mt-2 text-sm">对方正在答题中...</p>
      </div>

      {/* 你的结果（已锁定） */}
      <div className="bg-white rounded-xl p-4 mb-4 shadow-sm animate-fade-in">
        <div className="text-blue-800 font-medium mb-3">✅ 你的结果已锁定</div>
        <div className="text-blue-700 font-bold mb-2">{your_result.value_type}</div>
        <div className="space-y-1">
          {your_result.top3.map((trait, i) => (
            <div key={i} className="flex items-center justify-between text-sm">
              <span className="text-blue-700">{trait.trait_name}</span>
              <span className="text-blue-500 font-medium">{trait.chips}筹码</span>
            </div>
          ))}
        </div>
      </div>

      {/* 等待提示 */}
      <div className="bg-blue-100 rounded-lg p-4 mb-4 animate-fade-in">
        <div className="text-blue-800 font-medium mb-2">对方完成后，你们将看到：</div>
        <div className="space-y-1 text-sm text-blue-700">
          <div>• 对方选择了什么特质</div>
          <div>• 三观契合度分析</div>
          <div>• 共鸣点和差异点</div>
          <div>• AI相处建议</div>
        </div>
      </div>

      {/* 轮询状态 */}
      <div className="text-center mb-4">
        <div className="inline-flex items-center gap-2 px-3 py-2 bg-blue-50 rounded-full">
          <div
            key={countdown}
            className="w-6 h-6 bg-blue-200 rounded-full flex items-center justify-center text-blue-700 font-bold text-xs animate-scale-in"
          >
            {countdown}
          </div>
          <span className="text-blue-600 text-sm">秒后刷新</span>
        </div>
      </div>

      {/* 继续聊天按钮 */}
      {onContinueChat && (
        <button
          onClick={onContinueChat}
          className="w-full py-3 bg-gray-100 text-gray-600 font-medium rounded-xl hover:bg-gray-200 transition-all"
        >
          先聊别的（后台等待）
        </button>
      )}
    </div>
  )
}